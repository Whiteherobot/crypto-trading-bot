"""
strategy/bb_rsi_strategy.py
============================
Estrategia alternativa: REVERSIÓN A LA MEDIA con Bandas de Bollinger + RSI.

Contexto (ver README, rondas 1-4): el cruce de EMAs (ema_rsi_strategy.py) no
mostró edge demostrable en BTC/15m con los datos disponibles — el 95-100% de
sus salidas eran por trailing stop (no por reversión de tendencia detectada)
y la duración típica de una operación era de 2-7 velas, señal de que el
precio se mueve en saltos cortos que revierten, no en tendencias sostenidas.
Esta estrategia intenta capturar justo ese comportamiento de reversión en
lugar de perseguir una tendencia que no se sostiene.

REGLAS (long-only, pensado para spot):
  ENTRADA (comprar) cuando se cumplen TODAS:
    1. El cierre toca o cruza por debajo de la banda INFERIOR de Bollinger
       -> el precio está estadísticamente "barato" respecto a su media reciente.
    2. RSI < rsi_oversold -> confirma sobreventa real, no solo ruido.
    3. La vela es alcista (close > open) -> el rebote ya empezó; no se
       compra en plena caída libre.

  SALIDA (vender) cuando ocurre CUALQUIERA (prioridad de arriba hacia abajo,
  la gestiona el backtest/live porque dependen del precio/tiempo de entrada):
    1. El precio toca o cruza la banda MEDIA (objetivo natural de la reversión).
    2. Stop-loss fijo desde la entrada (protección si la reversión no ocurre).
    3. Time-stop: si pasan time_stop_candles velas sin llegar a la banda
       media, se cierra igual (evita quedar atrapado en un lateral profundo).

SIN trailing stop a propósito: la banda media ya es un objetivo dinámico;
un trailing interferiría con esa lógica (dejaría correr hacia la banda
superior, que no es la tesis de esta estrategia).

Misma interfaz que EmaRsiStrategy (compute_indicators, generate_signals,
latest_signal) para que backtester.py y live/paper_trade.py puedan usar
cualquiera de las dos sin reescribirse.
"""

from __future__ import annotations

import pandas as pd

from config.config import BBRsiConfig
from utils.indicators import bollinger, rsi


class BBRsiStrategy:
    # El backtester/paper_trade usan esto para saber qué lógica de
    # gestión de posición aplicar (stop fijo + objetivo + time-stop, no
    # trailing-desde-peak como en EmaRsiStrategy).
    EXIT_STYLE = "target_time_stop"

    def __init__(self, cfg: BBRsiConfig):
        self.cfg = cfg

    # ------------------------------------------------------------------
    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Añade columnas bb_lower, bb_mid, bb_upper y rsi al DataFrame de velas."""
        out = df.copy()
        out["bb_lower"], out["bb_mid"], out["bb_upper"] = bollinger(
            out["close"], self.cfg.bb_period, self.cfg.bb_std
        )
        out["rsi"] = rsi(out["close"], self.cfg.rsi_period)
        return out

    # ------------------------------------------------------------------
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Devuelve el DataFrame con una columna 'signal':
            +1 = señal de ENTRADA (toca banda inferior + sobreventa + vela alcista)
            -1 = señal de SALIDA por objetivo (toca/cruza la banda media)
             0 = no hacer nada
        """
        out = self.compute_indicators(df)

        touches_lower = out["close"] <= out["bb_lower"]
        oversold = out["rsi"] < self.cfg.rsi_oversold
        bullish_candle = out["close"] > out["open"]

        reaches_mid = out["close"] >= out["bb_mid"]

        out["signal"] = 0
        out.loc[touches_lower & oversold & bullish_candle, "signal"] = 1
        out.loc[reaches_mid, "signal"] = -1
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
            "bb_lower": round(float(last["bb_lower"]), 2) if pd.notna(last["bb_lower"]) else None,
            "bb_mid": round(float(last["bb_mid"]), 2) if pd.notna(last["bb_mid"]) else None,
            "bb_upper": round(float(last["bb_upper"]), 2) if pd.notna(last["bb_upper"]) else None,
            "rsi": round(float(last["rsi"]), 2),
            "time": signed.index[-1],
        }
        return int(last["signal"]), context
