"""
backtest/backtester.py
======================
Motor de backtest propio, event-driven (vela a vela). Es deliberadamente
simple y legible para que entiendas EXACTAMENTE cómo se calcula cada métrica.

Supuestos (realistas pero sencillos):
- Long-only (compramos y vendemos; no hay cortos).
- Entramos al CIERRE de la vela que da la señal (sin mirar el futuro).
- En cada vela con posición abierta comprobamos si el LOW tocó el stop-loss
  o el HIGH tocó el take-profit (gestión de riesgo intra-vela).
- Aplicamos una comisión `fee_pct` por cada lado (compra y venta).
- Tamaño de posición = position_size_pct del capital disponible.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from config.config import RiskConfig, StrategyConfig
from strategy.ema_rsi_strategy import EmaRsiStrategy


@dataclass
class Trade:
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    units: float
    pnl: float
    reason: str          # "take_profit" | "stop_loss" | "ema_cross"


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
    def __init__(self, strat_cfg: StrategyConfig, risk_cfg: RiskConfig):
        self.strategy = EmaRsiStrategy(strat_cfg)
        self.risk = risk_cfg

    def run(self, df: pd.DataFrame) -> BacktestResult:
        data = self.strategy.generate_signals(df).dropna()

        cash = self.risk.initial_capital
        in_position = False
        units = 0.0
        entry_price = stop_price = tp_price = 0.0
        entry_time = None

        trades: list[Trade] = []
        equity_curve: list[float] = []

        for ts, row in data.iterrows():
            price = row["close"]

            if in_position:
                exit_price = exit_reason = None

                # 1) ¿Se tocó stop-loss o take-profit dentro de la vela?
                if row["low"] <= stop_price:
                    exit_price, exit_reason = stop_price, "stop_loss"
                elif row["high"] >= tp_price:
                    exit_price, exit_reason = tp_price, "take_profit"
                # 2) ¿Señal de salida por cruce bajista de EMAs?
                elif row["signal"] == -1:
                    exit_price, exit_reason = price, "ema_cross"

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

            # 3) ¿Señal de entrada y estamos fuera del mercado?
            elif row["signal"] == 1:
                position_value = cash * self.risk.position_size_pct
                units = position_value / price * (1 - self.risk.fee_pct)
                cash -= position_value
                entry_price = price
                entry_time = ts
                stop_price = price * (1 - self.risk.stop_loss_pct)
                tp_price = price * (1 + self.risk.take_profit_pct)
                in_position = True

            # Equity = efectivo + valor de la posición abierta a precio actual
            equity_curve.append(cash + units * price)

        result = BacktestResult(
            equity_curve=pd.Series(equity_curve, index=data.index),
            trades=trades,
            initial_capital=self.risk.initial_capital,
        )
        return result
