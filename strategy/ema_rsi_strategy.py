"""
strategy/ema_rsi_strategy.py
============================
Estrategia: cruce de EMAs (9/21) + filtro RSI.

REGLAS (long-only, pensado para spot):
  ENTRADA (comprar) cuando se cumplen TODAS:
    1. La EMA rápida cruza hacia ARRIBA a la EMA lenta (señal alcista).
    2. RSI > rsi_lower  -> confirma que hay momentum (no entrar en caída).
    3. RSI < rsi_upper  -> evita comprar en zona de sobrecompra.

  SALIDA (vender) cuando ocurre CUALQUIERA:
    1. La EMA rápida cruza hacia ABAJO a la EMA lenta (señal bajista), o
    2. Se toca el STOP-LOSS o el TAKE-PROFIT (lo gestiona el backtest/live,
       porque dependen del precio de entrada, no solo de los indicadores).

La misma clase la usan el backtest (toda la serie) y el live (última vela),
así garantizamos que se opera EXACTAMENTE con la misma lógica.
"""

from __future__ import annotations

import pandas as pd

from config.config import StrategyConfig
from utils.indicators import ema, rsi


class EmaRsiStrategy:
    def __init__(self, cfg: StrategyConfig):
        self.cfg = cfg

    # ------------------------------------------------------------------
    def compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Añade columnas ema_fast, ema_slow y rsi al DataFrame de velas."""
        out = df.copy()
        out["ema_fast"] = ema(out["close"], self.cfg.ema_fast)
        out["ema_slow"] = ema(out["close"], self.cfg.ema_slow)
        out["rsi"] = rsi(out["close"], self.cfg.rsi_period)
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

        out["signal"] = 0
        out.loc[cross_up & rsi_ok, "signal"] = 1
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
        return int(last["signal"]), context
