"""
backtest/backtester.py
======================
Motor de backtest propio, event-driven (vela a vela). Es deliberadamente
simple y legible para que entiendas EXACTAMENTE cómo se calcula cada métrica.

Funciona con CUALQUIER estrategia que implemente generate_signals() (columna
'signal': +1 entrada, -1 salida por indicador) — hoy hay tres:
  - EmaRsiStrategy (EXIT_STYLE="trailing"): seguimiento de tendencia, stop
    fijo/ATR con trailing desde el máximo alcanzado.
  - BBRsiStrategy (EXIT_STYLE="target_time_stop"): reversión a la media,
    objetivo en la banda media + stop fijo + cierre forzado por tiempo.
  - RegimeSwitchStrategy (EXIT_STYLE="regime_switch"): usa ema_rsi en
    régimen alcista y bb_rsi en régimen lateral; cada POSICIÓN recuerda con
    cuál entró (`entry_style`) y se gestiona con la lógica correspondiente
    aunque el régimen cambie mientras está abierta.
La gestión de posición (qué dispara la salida, en qué orden) se delega a
`_manage_trailing()`, `_manage_target_time_stop()` o `_manage_regime_switch()`
según ese atributo, porque cada estilo de estrategia protege el riesgo de
forma distinta.

Supuestos comunes (realistas pero sencillos):
- Long-only (compramos y vendemos; no hay cortos).
- Entramos al CIERRE de la vela que da la señal (sin mirar el futuro).
- Tras cerrar una posición, se ignoran nuevas señales de entrada durante
  `cooldown_candles` velas.
- Aplicamos una comisión `fee_pct` por cada lado (compra y venta).
- Tamaño de posición = position_size_pct del capital disponible.

EmaRsiStrategy — gestión "trailing":
- En cada vela con posición abierta comprobamos si el LOW tocó el stop
  efectivo (gestión de riesgo intra-vela).
- Stop efectivo = max(stop fijo, trailing stop). El trailing stop sigue el
  precio HIGH máximo alcanzado desde la entrada ("peak"); nunca es más laxo
  que el stop fijo, pero sube a medida que sube el precio. Si `atr_multiplier`
  está activo, tanto el stop inicial como el trailing se basan en el ATR
  (volatilidad) en vez de un % fijo -- el % fijo (`stop_loss_pct`) actúa
  como techo máximo de riesgo del stop inicial. Si ambos son None, el stop
  efectivo es siempre el fijo (sin trailing).

BBRsiStrategy — gestión "target_time_stop" (SIN trailing, a propósito):
- Orden de prioridad de salida: 1) objetivo (banda media, señal=-1),
  2) stop-loss fijo (`BBRsiConfig.stop_loss_pct`), 3) time-stop
  (`BBRsiConfig.time_stop_candles` velas sin llegar al objetivo).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from config.config import RiskConfig


@dataclass
class Trade:
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    units: float
    pnl: float
    reason: str          # "trailing_stop" | "stop_loss" | "ema_cross" | "target_mean" | "time_stop" | "trend_exit"


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: list[Trade] = field(default_factory=list)
    initial_capital: float = 0.0

    # -------------------- métricas --------------------
    @property
    def final_equity(self) -> float:
        return float(self.equity_curve.iloc[-1])

    @property
    def total_return_pct(self) -> float:
        return (self.final_equity / self.initial_capital - 1) * 100

    @property
    def num_trades(self) -> int:
        return len(self.trades)

    @property
    def win_rate_pct(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t.pnl > 0)
        return wins / len(self.trades) * 100

    @property
    def max_drawdown_pct(self) -> float:
        """Mayor caída desde un máximo previo de la curva de equity."""
        running_max = self.equity_curve.cummax()
        drawdown = (self.equity_curve - running_max) / running_max
        return float(drawdown.min() * 100)

    def sharpe_ratio(self, periods_per_year: int) -> float:
        """Sharpe anualizado a partir de los retornos por vela (rf = 0)."""
        returns = self.equity_curve.pct_change().dropna()
        if returns.std() == 0 or returns.empty:
            return 0.0
        return float(returns.mean() / returns.std() * np.sqrt(periods_per_year))

    def summary(self, periods_per_year: int) -> dict:
        return {
            "Capital inicial": round(self.initial_capital, 2),
            "Capital final": round(self.final_equity, 2),
            "Retorno total %": round(self.total_return_pct, 2),
            "Operaciones": self.num_trades,
            "Win rate %": round(self.win_rate_pct, 2),
            "Max drawdown %": round(self.max_drawdown_pct, 2),
            "Sharpe (anual.)": round(self.sharpe_ratio(periods_per_year), 2),
        }


# Velas por año según timeframe, para anualizar el Sharpe
PERIODS_PER_YEAR = {
    "1m": 525_600, "5m": 105_120, "15m": 35_040, "30m": 17_520,
    "1h": 8_760, "4h": 2_190, "1d": 365,
}


class Backtester:
    def __init__(self, strategy, risk_cfg: RiskConfig):
        """`strategy` es un objeto YA INSTANCIADO (EmaRsiStrategy(...) o
        BBRsiStrategy(...)), no una config cruda — así el backtester no
        necesita saber qué clase de estrategia es, solo su EXIT_STYLE."""
        self.strategy = strategy
        self.risk = risk_cfg

    # ------------------------------------------------------------------
    #  Gestión de posición para EmaRsiStrategy (EXIT_STYLE="trailing")
    # ------------------------------------------------------------------
    def _manage_trailing(self, row, state: dict) -> tuple[float | None, str | None]:
        state["peak_price"] = max(state["peak_price"], row["high"])
        effective_stop = state["stop_price"]
        if self.risk.atr_multiplier:
            trail_distance = self.risk.atr_multiplier * row["atr"]
            effective_stop = max(effective_stop, state["peak_price"] - trail_distance)
        elif self.risk.trail_pct:
            effective_stop = max(effective_stop, state["peak_price"] * (1 - self.risk.trail_pct))

        if row["low"] <= effective_stop:
            reason = "trailing_stop" if effective_stop > state["stop_price"] else "stop_loss"
            return effective_stop, reason
        if not row["regime_ok"]:
            return row["close"], "regime_exit"
        if row["signal"] == -1:
            return row["close"], "ema_cross"
        return None, None

    def _open_trailing(self, row, price: float) -> dict:
        fixed_stop_distance = price * self.risk.stop_loss_pct
        if self.risk.atr_multiplier:
            # ATR como distancia de stop, pero nunca más ancho que el % fijo (techo de riesgo)
            stop_distance = min(self.risk.atr_multiplier * row["atr"], fixed_stop_distance)
        else:
            stop_distance = fixed_stop_distance
        return {"stop_price": price - stop_distance, "peak_price": price}

    # ------------------------------------------------------------------
    #  Gestión de posición para BBRsiStrategy (EXIT_STYLE="target_time_stop")
    # ------------------------------------------------------------------
    def _manage_target_time_stop(self, row, state: dict, i: int) -> tuple[float | None, str | None]:
        # Orden de prioridad pedido: 1) objetivo, 2) stop fijo, 3) time-stop
        if row["signal"] == -1:
            return row["close"], "target_mean"
        if row["low"] <= state["stop_price"]:
            return state["stop_price"], "stop_loss"
        if (i - state["entry_i"]) >= self.strategy.cfg.time_stop_candles:
            return row["close"], "time_stop"
        return None, None

    def _open_target_time_stop(self, price: float, i: int) -> dict:
        stop_price = price * (1 - self.strategy.cfg.stop_loss_pct)
        return {"stop_price": stop_price, "entry_i": i}

    # ------------------------------------------------------------------
    #  Gestión de posición para RegimeSwitchStrategy (EXIT_STYLE="regime_switch")
    # ------------------------------------------------------------------
    def _manage_regime_switch(self, row, state: dict, i: int) -> tuple[float | None, str | None]:
        if state["sub_style"] == "trend":
            state["peak_price"] = max(state["peak_price"], row["high"])
            effective_stop = state["stop_price"]
            if self.risk.atr_multiplier:
                effective_stop = max(effective_stop, state["peak_price"] - self.risk.atr_multiplier * row["atr"])
            elif self.risk.trail_pct:
                effective_stop = max(effective_stop, state["peak_price"] * (1 - self.risk.trail_pct))
            if row["low"] <= effective_stop:
                reason = "trailing_stop" if effective_stop > state["stop_price"] else "stop_loss"
                return effective_stop, reason
            if row["trend_exit_ok"]:
                return row["close"], "trend_exit"
            return None, None
        else:   # sub_style == "reversion"
            if row["reversion_exit_ok"]:
                return row["close"], "target_mean"
            if row["low"] <= state["stop_price"]:
                return state["stop_price"], "stop_loss"
            if (i - state["entry_i"]) >= self.strategy.bb_cfg.time_stop_candles:
                return row["close"], "time_stop"
            return None, None

    def _open_regime_switch(self, row, price: float, i: int) -> dict:
        sub_style = row["entry_style"]
        if sub_style == "trend":
            state = self._open_trailing(row, price)
        else:
            state = {"stop_price": price * (1 - self.strategy.bb_cfg.stop_loss_pct), "entry_i": i}
        state["sub_style"] = sub_style
        return state

    # ------------------------------------------------------------------
    def run(self, df: pd.DataFrame) -> BacktestResult:
        data = self.strategy.generate_signals(df).dropna()
        style = self.strategy.EXIT_STYLE

        cash = self.risk.initial_capital
        in_position = False
        units = 0.0
        entry_price = 0.0
        entry_time = None
        state: dict = {}
        last_exit_i = -10**9   # índice de vela del último cierre (para el cooldown)

        trades: list[Trade] = []
        equity_curve: list[float] = []

        for i, (ts, row) in enumerate(data.iterrows()):
            price = row["close"]

            if in_position:
                if style == "trailing":
                    exit_price, exit_reason = self._manage_trailing(row, state)
                elif style == "regime_switch":
                    exit_price, exit_reason = self._manage_regime_switch(row, state, i)
                else:
                    exit_price, exit_reason = self._manage_target_time_stop(row, state, i)

                if exit_price is not None:
                    proceeds = units * exit_price * (1 - self.risk.fee_pct)
                    cost = units * entry_price
                    pnl = proceeds - cost
                    cash += proceeds
                    trades.append(
                        Trade(entry_time, entry_price, ts, exit_price, units, pnl, exit_reason)
                    )
                    in_position = False
                    units = 0.0
                    last_exit_i = i

            # ¿Señal de entrada, estamos fuera del mercado y ya pasó el cooldown?
            elif row["signal"] == 1 and (i - last_exit_i) >= self.risk.cooldown_candles:
                position_value = cash * self.risk.position_size_pct
                units = position_value / price * (1 - self.risk.fee_pct)
                cash -= position_value
                entry_price = price
                entry_time = ts
                if style == "trailing":
                    state = self._open_trailing(row, price)
                elif style == "regime_switch":
                    state = self._open_regime_switch(row, price, i)
                else:
                    state = self._open_target_time_stop(price, i)
                in_position = True

            # Equity = efectivo + valor de la posición abierta a precio actual
            equity_curve.append(cash + units * price)

        result = BacktestResult(
            equity_curve=pd.Series(equity_curve, index=data.index),
            trades=trades,
            initial_capital=self.risk.initial_capital,
        )
        return result
