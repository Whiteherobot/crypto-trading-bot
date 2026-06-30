"""
config/config.py
================
Punto único de configuración del bot. TODO lo que quieras ajustar
(par, timeframe, periodos de indicadores, gestión de riesgo) vive aquí,
no disperso por el código.

- Las CLAVES de API se leen del archivo .env (nunca se escriben aquí).
- Los PARÁMETROS de estrategia/riesgo son dataclasses fáciles de editar.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Carga el .env que está en la raíz del proyecto
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


# ----------------------------------------------------------------------
# 1) Credenciales y modo (se leen del entorno / .env)
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class ExchangeConfig:
    api_key: str = os.getenv("BINANCE_TESTNET_API_KEY", "")
    api_secret: str = os.getenv("BINANCE_TESTNET_API_SECRET", "")
    mode: str = os.getenv("TRADING_MODE", "testnet").lower()  # "testnet" | "live"

    @property
    def is_testnet(self) -> bool:
        return self.mode != "live"


# ----------------------------------------------------------------------
# 2) Mercado a operar
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class MarketConfig:
    symbol: str = "BTC/USDT"   # par (formato ccxt: BASE/QUOTE)
    timeframe: str = "5m"      # 1m, 5m, 15m, 1h, 4h, 1d ...
    # Cuántas velas pedir como historial para el backtest (1h * 24 * 365 * 2 ≈ 2 años)
    history_limit: int = 24 * 365 * 2


# ----------------------------------------------------------------------
# 3) Parámetros de la estrategia (EMA cross + filtro RSI)
#    Cambia estos números para "tunear" la estrategia sin tocar la lógica.
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class StrategyConfig:
    ema_fast: int = 9          # EMA rápida
    ema_slow: int = 21         # EMA lenta
    rsi_period: int = 14       # periodo del RSI
    rsi_lower: float = 50.0    # solo COMPRAR si RSI > rsi_lower (hay momentum)
    rsi_upper: float = 70.0    # evitar comprar si RSI > rsi_upper (sobrecompra)


# ----------------------------------------------------------------------
# 4) Gestión de riesgo y capital
# ----------------------------------------------------------------------
@dataclass(frozen=True)
class RiskConfig:
    initial_capital: float = 10_000.0   # capital inicial (solo para backtest)
    position_size_pct: float = 0.10     # % del capital por operación (10%)
    stop_loss_pct: float = 0.02         # stop-loss 2% por debajo de la entrada
    take_profit_pct: float = 0.04       # take-profit 4% por encima (ratio 1:2)
    fee_pct: float = 0.001              # comisión estimada por lado (0.1% taker)


# ----------------------------------------------------------------------
# Instancias listas para importar:  from config.config import STRATEGY, RISK ...
# ----------------------------------------------------------------------
EXCHANGE = ExchangeConfig()
MARKET = MarketConfig()
STRATEGY = StrategyConfig()
RISK = RiskConfig()
