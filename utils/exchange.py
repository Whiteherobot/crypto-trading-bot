"""
utils/exchange.py
=================
Conexión al exchange vía ccxt. Por defecto apunta a la TESTNET de Binance Spot
(dinero ficticio). La función clave es set_sandbox_mode(True), que reemplaza las
URLs de producción por las de testnet -> imposible operar con dinero real.

Funciones:
- get_exchange()        -> objeto ccxt listo y autenticado
- fetch_balance_summary -> balances con saldo > 0 de la cuenta de prueba
"""

from __future__ import annotations

import ccxt

from config.config import EXCHANGE
from utils.logger import get_logger

log = get_logger("exchange")


def get_exchange() -> ccxt.binance:
    """
    Crea y devuelve un cliente ccxt de Binance.
    - enableRateLimit: ccxt espacía las peticiones para no chocar con rate limits.
    - defaultType 'spot': operamos en el mercado spot (no futuros/margin).
    - set_sandbox_mode(True): conmuta a https://testnet.binance.vision (TESTNET).
    """
    if not EXCHANGE.api_key or not EXCHANGE.api_secret:
        raise RuntimeError(
            "Faltan credenciales. Copia .env.example a .env y rellena tus "
            "claves de la Testnet (https://testnet.binance.vision/)."
        )

    exchange = ccxt.binance(
        {
            "apiKey": EXCHANGE.api_key,
            "secret": EXCHANGE.api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": "spot",
                # Solo cargar mercados SPOT. Sin esto, ccxt también intenta
                # cargar futuros (linear/inverse) y en testnet pega a
                # testnet.binancefuture.com, que aquí se cuelga (timeout).
                "fetchMarkets": {"types": ["spot"]},
            },
        }
    )

    if EXCHANGE.is_testnet:
        exchange.set_sandbox_mode(True)
        log.info("Conectado a Binance Spot TESTNET (dinero de prueba).")
    else:
        # Salvaguarda: no permitimos producción sin un cambio explícito de código.
        raise RuntimeError(
            "TRADING_MODE=live está bloqueado por seguridad. "
            "Este bot está pensado solo para testnet."
        )

    exchange.load_markets()
    return exchange


def fetch_balance_summary(exchange: ccxt.binance) -> dict[str, float]:
    """Devuelve {moneda: saldo_total} solo de las monedas con saldo > 0."""
    balance = exchange.fetch_balance()
    totals = balance.get("total", {})
    summary = {coin: amount for coin, amount in totals.items() if amount and amount > 0}
    return summary


# Permite probar la conexión rápidamente:  python -m utils.exchange
if __name__ == "__main__":
    ex = get_exchange()
    print("\n=== Balance de la cuenta de prueba ===")
    saldos = fetch_balance_summary(ex)
    if not saldos:
        print("(sin saldo) Pide fondos de prueba en https://testnet.binance.vision/")
    for coin, amount in saldos.items():
        print(f"  {coin:>6}: {amount}")
