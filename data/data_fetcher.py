"""
data/data_fetcher.py
====================
Descarga de datos OHLCV (Open/High/Low/Close/Volume) desde Binance.

Binance limita cada petición a ~1000 velas, así que para traer 1-2 años
paginamos: pedimos bloques y avanzamos en el tiempo hasta completar.

OHLCV = la "vela" de cada periodo:
    timestamp, open, high, low, close, volume
"""

from __future__ import annotations

import time

import ccxt
import pandas as pd

from utils.logger import get_logger

log = get_logger("data")

# Milisegundos por unidad de timeframe (para calcular cuánto avanzar al paginar)
_TF_MS = {
    "1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
    "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
}


def fetch_ohlcv(
    exchange: ccxt.binance,
    symbol: str,
    timeframe: str = "1h",
    limit: int = 1000,
) -> pd.DataFrame:
    """
    Descarga `limit` velas (las más recientes) y devuelve un DataFrame indexado
    por fecha. Pagina automáticamente si limit > 1000.
    """
    if timeframe not in _TF_MS:
        raise ValueError(f"Timeframe no soportado: {timeframe}")

    tf_ms = _TF_MS[timeframe]
    now = exchange.milliseconds()
    since = now - limit * tf_ms          # punto de partida hacia atrás en el tiempo

    all_rows: list[list] = []
    while since < now:
        batch = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
        if not batch:
            break
        all_rows += batch
        since = batch[-1][0] + tf_ms      # avanza justo después de la última vela
        log.info("Descargadas %d velas de %s %s ...", len(all_rows), symbol, timeframe)
        time.sleep(exchange.rateLimit / 1000)  # respeta el rate limit

    df = _to_dataframe(all_rows)
    return df.tail(limit)                 # recorta por si paginamos de más


def _to_dataframe(rows: list[list]) -> pd.DataFrame:
    """Convierte la lista cruda de ccxt en un DataFrame limpio y sin duplicados."""
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.drop_duplicates("timestamp").set_index("timestamp").sort_index()
    return df.astype(float)


# Prueba rápida:  python -m data.data_fetcher
if __name__ == "__main__":
    from config.config import MARKET
    from utils.exchange import get_exchange

    ex = get_exchange()
    data = fetch_ohlcv(ex, MARKET.symbol, MARKET.timeframe, limit=300)
    print(data.tail())
    print(f"\n{len(data)} velas de {MARKET.symbol} ({MARKET.timeframe})")
