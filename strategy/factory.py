"""
strategy/factory.py
====================
Instancia la estrategia ACTIVA según config.MARKET.strategy, para que
backtester.py y live/paper_trade.py no tengan que saber qué clases existen.
"""

from __future__ import annotations

from config.config import BB_STRATEGY, MARKET, STRATEGY
from strategy.bb_rsi_strategy import BBRsiStrategy
from strategy.ema_rsi_strategy import EmaRsiStrategy
from strategy.regime_switch_strategy import RegimeSwitchStrategy

_BUILDERS = {
    "ema_rsi": lambda: EmaRsiStrategy(STRATEGY),
    "bb_rsi": lambda: BBRsiStrategy(BB_STRATEGY),
    "regime_switch": lambda: RegimeSwitchStrategy(STRATEGY, BB_STRATEGY),
}


def build_strategy(name: str | None = None):
    """Devuelve una instancia de la estrategia `name` (por defecto, MARKET.strategy)."""
    name = name or MARKET.strategy
    try:
        return _BUILDERS[name]()
    except KeyError:
        raise ValueError(
            f"Estrategia desconocida: {name!r}. Opciones: {list(_BUILDERS)}"
        ) from None
