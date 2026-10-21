"""
strategy/regime_switch_strategy.py
====================================
Estrategia combinada: usa el filtro de régimen (pendiente de EMA200, ya
construido para ema_rsi) para DECIDIR cuál de las dos estrategias existentes
aplicar en cada momento, en vez de tratarlas como alternativas competidoras:

  - Régimen ALCISTA (pendiente EMA200 > regime_slope_threshold):
    entra con la lógica de ema_rsi (cruce EMA + RSI + volumen).
  - Régimen LATERAL (pendiente entre -threshold y +threshold):
    entra con la lógica de bb_rsi (Bollinger + RSI, reversión a la media).
  - Régimen BAJISTA (pendiente < -threshold): NO opera. Las rondas 1-4 (ver
    README) ya mostraron que el filtro de régimen evita casi el 100% de las
    entradas ahí, y que ese régimen concentra las peores caídas de precio.

Motivación (ver README, diagnóstico de régimen): en 90 días reales, el
régimen "lateral" concentraba la mayor parte de las pérdidas de ema_rsi
(-$26 de -$33 totales), y bb_rsi (probado sin filtrar por régimen) tampoco
mostró edge — pero nunca se probó bb_rsi restringida específicamente al
régimen para el que la reversión a la media tiene sentido económico. Esta
estrategia es esa prueba.

Cada posición "recuerda" con qué sub-estrategia entró (columna
`entry_style`: "trend" o "reversion") para que backtester.py/paper_trade.py
apliquen la gestión de salida correspondiente (trailing/ATR para "trend",
objetivo en banda media + stop fijo + time-stop para "reversion") durante
toda la vida de esa posición, aunque el régimen cambie mientras está abierta.
"""

from __future__ import annotations

import pandas as pd

from config.config import BBRsiConfig, StrategyConfig
from utils.indicators import atr, bollinger, ema, rsi


class RegimeSwitchStrategy:
    # El backtester/paper_trade usan esto para saber que la gestión de
    # posición depende de `entry_style` (decidido por posición, no fijo).
    EXIT_STYLE = "regime_switch"

    def __init__(self, ema_cfg: StrategyConfig, bb_cfg: BBRsiConfig):
        self.ema_cfg = ema_cfg
        self.bb_cfg = bb_cfg
        self.cfg = ema_cfg   # compat: algunos parámetros compartidos (atr_period) se leen de aquí

    # ------------------------------------------------------------------
    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        # --- lado "trend" (ema_rsi) ---
        out["ema_fast"] = ema(out["close"], self.ema_cfg.ema_fast)
        out["ema_slow"] = ema(out["close"], self.ema_cfg.ema_slow)
        out["rsi"] = rsi(out["close"], self.ema_cfg.rsi_period)
        out["ema_trend"] = ema(out["close"], self.ema_cfg.ema_trend)
        prev = out["ema_trend"].shift(self.ema_cfg.regime_lookback)
        out["regime_slope"] = (out["ema_trend"] - prev) / prev
        out["vol_avg"] = out["volume"].rolling(self.ema_cfg.vol_window).mean().shift(1)
        out["atr"] = atr(out, self.ema_cfg.atr_period)

        # --- lado "reversion" (bb_rsi) ---
        out["bb_lower"], out["bb_mid"], out["bb_upper"] = bollinger(
            out["close"], self.bb_cfg.bb_period, self.bb_cfg.bb_std
        )
        return out

    # ------------------------------------------------------------------
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        out = self.compute_indicators(df)

        # ---- régimen ----
        thresh = self.ema_cfg.regime_slope_threshold
        regime_alcista = out["regime_slope"] > thresh
        regime_lateral = out["regime_slope"].abs() <= thresh
        # régimen bajista = ni alcista ni lateral -> ninguna de las dos entra

        # ---- señal "trend" (idéntica a EmaRsiStrategy), solo en alcista ----
        above = out["ema_fast"] > out["ema_slow"]
        cross_up = above & ~above.shift(1, fill_value=False)
        cross_down = ~above & above.shift(1, fill_value=False)
        rsi_ok = (out["rsi"] > self.ema_cfg.rsi_lower) & (out["rsi"] < self.ema_cfg.rsi_upper)
        trend_ok = out["close"] > out["ema_trend"]
        if self.ema_cfg.vol_mult:
            vol_ok = out["volume"] >= out["vol_avg"] * self.ema_cfg.vol_mult
        else:
            vol_ok = True
        entry_trend = cross_up & rsi_ok & trend_ok & vol_ok & regime_alcista

        # ---- señal "reversion" (idéntica a BBRsiStrategy), solo en lateral ----
        touches_lower = out["close"] <= out["bb_lower"]
        oversold = out["rsi"] < self.bb_cfg.rsi_oversold
        bullish_candle = out["close"] > out["open"]
        entry_reversion = touches_lower & oversold & bullish_candle & regime_lateral

        # ---- salidas de cada lado (se aplica la que corresponda según entry_style) ----
        out["trend_exit_ok"] = cross_down | ~regime_alcista   # cruce bajista o el régimen dejó de ser alcista
        out["reversion_exit_ok"] = out["close"] >= out["bb_mid"]

        # 'signal': +1 = entrada (por cualquiera de las dos sub-estrategias). No hay
        # -1 genérico aquí -> las salidas se leen de trend_exit_ok/reversion_exit_ok
        # según con qué entry_style se abrió la posición (ver backtester/paper_trade).
        #
        # IMPORTANTE: "entry_style" se inicializa con "" (string vacío), NUNCA con
        # None/NaN. El backtester hace `generate_signals(df).dropna()` de forma
        # genérica para todas las estrategias (para recortar el warm-up de los
        # indicadores) — si esta columna tuviera None en las velas sin señal (la
        # inmensa mayoría), ese .dropna() borraría casi TODO el DataFrame en vez de
        # solo el warm-up inicial, rompiendo el índice de velas que usa el time-stop.
        out["signal"] = 0
        out["entry_style"] = ""
        out.loc[entry_trend, "signal"] = 1
        out.loc[entry_trend, "entry_style"] = "trend"
        out.loc[entry_reversion, "signal"] = 1
        out.loc[entry_reversion, "entry_style"] = "reversion"
        return out

    # ------------------------------------------------------------------
    def latest_signal(self, df: pd.DataFrame) -> tuple[int, dict]:
        signed = self.generate_signals(df)
        last = signed.iloc[-1]
        regime = ("ALCISTA" if last["regime_slope"] > self.ema_cfg.regime_slope_threshold
                  else "BAJISTA" if last["regime_slope"] < -self.ema_cfg.regime_slope_threshold
                  else "LATERAL")
        context = {
            "price": float(last["close"]),
            "time": signed.index[-1],
            "regime": regime,
            "regime_slope": round(float(last["regime_slope"]), 5) if pd.notna(last["regime_slope"]) else None,
            "ema_fast": round(float(last["ema_fast"]), 2),
            "ema_slow": round(float(last["ema_slow"]), 2),
            "ema_trend": round(float(last["ema_trend"]), 2),
            "bb_lower": round(float(last["bb_lower"]), 2) if pd.notna(last["bb_lower"]) else None,
            "bb_mid": round(float(last["bb_mid"]), 2) if pd.notna(last["bb_mid"]) else None,
            "bb_upper": round(float(last["bb_upper"]), 2) if pd.notna(last["bb_upper"]) else None,
            "rsi": round(float(last["rsi"]), 2),
            "atr": round(float(last["atr"]), 2) if pd.notna(last["atr"]) else None,
            "entry_style": last["entry_style"],
            "trend_exit_ok": bool(last["trend_exit_ok"]),
            "reversion_exit_ok": bool(last["reversion_exit_ok"]),
        }
        return int(last["signal"]), context
