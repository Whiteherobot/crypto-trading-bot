"""
strategy/ema_rsi_strategy.py
============================
Estrategia: cruce de EMAs (9/21) + filtro RSI + filtro de tendencia (EMA200)
+ filtro de volumen + filtro de régimen (pendiente de la EMA de tendencia)
+ filtro de volatilidad relativa (ATR).

REGLAS (long-only, pensado para spot):
  ENTRADA (comprar) cuando se cumplen TODAS:
    1. La EMA rápida cruza hacia ARRIBA a la EMA lenta (señal alcista).
    2. RSI > rsi_lower  -> confirma que hay momentum (no entrar en caída).
    3. RSI < rsi_upper  -> evita comprar en zona de sobrecompra.
    4. Precio de cierre > EMA de tendencia (ema_trend, p.ej. 200) -> solo se
       opera a favor del régimen de fondo; evita comprar cruces alcistas
       dentro de un mercado lateral o en tendencia bajista más amplia.
    5. Volumen de la vela de señal >= vol_mult x el volumen promedio de las
       vol_window velas ANTERIORES -> exige que el cruce venga acompañado de
       participación real, no de un movimiento de baja liquidez.
    6. Pendiente de la EMA de tendencia > regime_slope_threshold -> exige un
       régimen ALCISTA confirmado (no solo "precio por encima de EMA200",
       sino que esa EMA200 esté subiendo). El diagnóstico de régimen (ver
       README) mostró que el mercado "lateral" (pendiente casi plana)
       concentra la mayor parte de las pérdidas.
    7. ATR actual <= mediana(ATR de las atr_lookback velas ANTERIORES) x
       atr_max_mult -> exige volatilidad "normal o baja", no un pico. El
       diagnóstico (ver README) mostró que las operaciones ganadoras entran
       con ATR más bajo que las perdedoras, y que casi todas las pérdidas
       salen por el trailing stop (ruido violento), no por cruce EMA.

  SALIDA (vender) cuando ocurre CUALQUIERA:
    1. La EMA rápida cruza hacia ABAJO a la EMA lenta (señal bajista), o
    2. El régimen deja de ser alcista (pendiente <= regime_slope_threshold)
       -> cierre inmediato aunque no haya cruce bajista ni se toque el stop, o
    3. Se toca el STOP-LOSS o el TRAILING STOP (lo gestiona el backtest/live,
       porque dependen del precio de entrada, no solo de los indicadores).

La misma clase la usan el backtest (toda la serie) y el live (última vela),
así garantizamos que se opera EXACTAMENTE con la misma lógica.
"""

from __future__ import annotations

import pandas as pd

from config.config import StrategyConfig
from utils.indicators import atr, ema, rsi


class EmaRsiStrategy:
    # El backtester/paper_trade usan esto para saber qué lógica de gestión
    # de posición aplicar (stop fijo/ATR con trailing-desde-peak).
    EXIT_STYLE = "trailing"

    def __init__(self, cfg: StrategyConfig):
        self.cfg = cfg

    # ------------------------------------------------------------------
    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Añade columnas ema_fast, ema_slow, rsi (y ema_trend/vol_avg si aplica) al DataFrame de velas."""
        out = df.copy()
        out["ema_fast"] = ema(out["close"], self.cfg.ema_fast)
        out["ema_slow"] = ema(out["close"], self.cfg.ema_slow)
        out["rsi"] = rsi(out["close"], self.cfg.rsi_period)
        if self.cfg.ema_trend:
            out["ema_trend"] = ema(out["close"], self.cfg.ema_trend)
            if self.cfg.regime_lookback:
                prev = out["ema_trend"].shift(self.cfg.regime_lookback)
                out["regime_slope"] = (out["ema_trend"] - prev) / prev
        if self.cfg.vol_mult:
            # promedio de las N velas ANTERIORES (shift 1) para no mirar la propia vela de señal
            out["vol_avg"] = out["volume"].rolling(self.cfg.vol_window).mean().shift(1)
        out["atr"] = atr(out, self.cfg.atr_period)
        if self.cfg.atr_lookback:
            # mediana de las N velas ANTERIORES (shift 1), igual que vol_avg
            out["atr_median"] = out["atr"].rolling(self.cfg.atr_lookback).median().shift(1)
        return out

    # ------------------------------------------------------------------
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Devuelve el DataFrame con una columna 'signal':
            +1 = señal de ENTRADA (cruce alcista + filtro RSI ok)
            -1 = señal de SALIDA por indicador (cruce bajista)
             0 = no hacer nada
        """
        out = self.compute_indicators(df)

        # ¿La rápida está por encima de la lenta? (estado en cada vela)
        above = out["ema_fast"] > out["ema_slow"]

        # Un "cruce" ocurre cuando el estado cambia respecto a la vela anterior
        cross_up = above & ~above.shift(1, fill_value=False)     # pasó a estar arriba
        cross_down = ~above & above.shift(1, fill_value=False)   # pasó a estar abajo

        rsi_ok = (out["rsi"] > self.cfg.rsi_lower) & (out["rsi"] < self.cfg.rsi_upper)

        if self.cfg.ema_trend:
            trend_ok = out["close"] > out["ema_trend"]
        else:
            trend_ok = True

        if self.cfg.vol_mult:
            vol_ok = out["volume"] >= out["vol_avg"] * self.cfg.vol_mult
        else:
            vol_ok = True

        if self.cfg.ema_trend and self.cfg.regime_lookback:
            out["regime_ok"] = out["regime_slope"] > self.cfg.regime_slope_threshold
        else:
            out["regime_ok"] = True

        if self.cfg.atr_lookback:
            out["atr_ok"] = out["atr"] <= out["atr_median"] * self.cfg.atr_max_mult
        else:
            out["atr_ok"] = True

        raw_entry = cross_up & rsi_ok & trend_ok & vol_ok & out["regime_ok"] & out["atr_ok"]
        if self.cfg.confirm_candle:
            # el cruce (con todos sus filtros) ocurrió en la vela ANTERIOR, y en
            # ESTA vela el cierre sigue por encima de la EMA rápida -> confirmado
            entry_ok = raw_entry.shift(1, fill_value=False) & (out["close"] > out["ema_fast"])
        else:
            entry_ok = raw_entry

        out["signal"] = 0
        out.loc[entry_ok, "signal"] = 1
        out.loc[cross_down, "signal"] = -1
        return out

    # ------------------------------------------------------------------
    def latest_signal(self, df: pd.DataFrame) -> tuple[int, dict]:
        """
        Para el modo LIVE: calcula la señal de la ÚLTIMA vela cerrada y
        devuelve (signal, contexto) donde contexto explica el porqué.
        """
        signed = self.generate_signals(df)
        last = signed.iloc[-1]
        context = {
            "price": float(last["close"]),
            "ema_fast": round(float(last["ema_fast"]), 2),
            "ema_slow": round(float(last["ema_slow"]), 2),
            "rsi": round(float(last["rsi"]), 2),
            "time": signed.index[-1],
        }
        if self.cfg.ema_trend:
            context["ema_trend"] = round(float(last["ema_trend"]), 2)
        if self.cfg.vol_mult:
            context["volume"] = round(float(last["volume"]), 4)
            context["vol_avg"] = round(float(last["vol_avg"]), 4) if pd.notna(last["vol_avg"]) else None
        if self.cfg.ema_trend and self.cfg.regime_lookback:
            context["regime_slope"] = round(float(last["regime_slope"]), 5) if pd.notna(last["regime_slope"]) else None
            context["regime_ok"] = bool(last["regime_ok"])
        context["atr"] = round(float(last["atr"]), 2) if pd.notna(last["atr"]) else None
        if self.cfg.atr_lookback:
            context["atr_median"] = round(float(last["atr_median"]), 2) if pd.notna(last["atr_median"]) else None
            context["atr_ok"] = bool(last["atr_ok"])
        return int(last["signal"]), context
