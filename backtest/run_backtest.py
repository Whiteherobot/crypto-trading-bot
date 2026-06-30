"""
backtest/run_backtest.py
========================
Script de entrada para correr el backtest:

    python -m backtest.run_backtest

Descarga el histórico configurado (config.py), corre la estrategia, imprime
métricas y guarda la curva de equity como PNG en backtest/output/.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")            # backend sin ventana (guarda a archivo)
import matplotlib.pyplot as plt

from backtest.backtester import PERIODS_PER_YEAR, Backtester
from config.config import MARKET, RISK, STRATEGY
from data.data_fetcher import fetch_ohlcv
from utils.exchange import get_exchange
from utils.logger import get_logger

log = get_logger("backtest", filename="backtest.log")
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def main() -> None:
    log.info("Descargando histórico de %s %s ...", MARKET.symbol, MARKET.timeframe)
    exchange = get_exchange()
    df = fetch_ohlcv(exchange, MARKET.symbol, MARKET.timeframe, limit=MARKET.history_limit)
    log.info("Velas descargadas: %d  (%s -> %s)", len(df), df.index[0], df.index[-1])

    result = Backtester(STRATEGY, RISK).run(df)

    # ---- Métricas ----
    ppy = PERIODS_PER_YEAR[MARKET.timeframe]
    print("\n" + "=" * 42)
    print(f"  RESULTADOS BACKTEST  {MARKET.symbol} {MARKET.timeframe}")
    print("=" * 42)
    for k, v in result.summary(ppy).items():
        print(f"  {k:<20}: {v}")
    print("=" * 42)

    # ---- Gráfico de equity ----
    out_path = OUTPUT_DIR / f"equity_{MARKET.symbol.replace('/', '')}_{MARKET.timeframe}.png"
    plt.figure(figsize=(11, 5))
    plt.plot(result.equity_curve.index, result.equity_curve.values, color="#2b8a3e")
    plt.title(f"Curva de equity — {MARKET.symbol} {MARKET.timeframe}")
    plt.xlabel("Fecha")
    plt.ylabel("Capital (USDT)")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=120)
    print(f"\nGráfico guardado en: {out_path}\n")


if __name__ == "__main__":
    main()
