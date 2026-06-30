"""
live/paper_trade.py
===================
Paper trading EN VIVO contra la Testnet de Binance Spot. Ejecuta órdenes de
mercado REALES pero con dinero FICTICIO de la cuenta de prueba.

    python -m live.paper_trade

Flujo del bucle:
  1. Descarga las últimas velas CERRADAS y calcula la señal.
  2. Si estamos FUERA y hay señal de entrada -> compra a mercado y fija SL/TP.
  3. Si estamos DENTRO -> vigila precio actual; sale por SL, TP o cruce bajista.
  4. Registra CADA decisión en logs/live.log Y en el diario SQLite (data/journal),
     que es lo que consume el dashboard.
  5. Maneja errores de red / rate limit con reintentos y backoff.

IMPORTANTE: es long-only y usa el balance de USDT de la cuenta de prueba.
Pide fondos ficticios en https://testnet.binance.vision/ si el balance es 0.
"""

from __future__ import annotations

import time

import ccxt

from config.config import MARKET, RISK, STRATEGY
from data.data_fetcher import fetch_ohlcv
from data.journal import Journal
from strategy.ema_rsi_strategy import EmaRsiStrategy
from utils.exchange import get_exchange
from utils.logger import get_logger

log = get_logger("live", filename="live.log")

POLL_SECONDS = 60          # cada cuánto revisa el mercado
CANDLES_TO_FETCH = 200     # suficientes para estabilizar EMA/RSI


class PaperTrader:
    def __init__(self, exchange: ccxt.binance):
        self.ex = exchange
        self.strategy = EmaRsiStrategy(STRATEGY)
        self.symbol = MARKET.symbol
        self.base, self.quote = self.symbol.split("/")   # p.ej. "BTC", "USDT"
        self.journal = Journal()

        # Estado de la posición (en memoria)
        self.in_position = False
        self.units = 0.0
        self.entry_price = 0.0
        self.stop_price = 0.0
        self.tp_price = 0.0

        # Contabilidad propia del bot (para comparar su equity vs Binance)
        self.cash = 0.0          # quote (USDT) que el bot cree tener libre

    # ------------------------------------------------------------------
    def _current_price(self) -> float:
        return float(self.ex.fetch_ticker(self.symbol)["last"])

    def _closed_candles(self):
        """Velas cerradas (descarta la última, que aún se está formando)."""
        df = fetch_ohlcv(self.ex, self.symbol, MARKET.timeframe, limit=CANDLES_TO_FETCH)
        return df.iloc[:-1]

    @staticmethod
    def _fill(order: dict, fallback_price: float, fallback_amount: float) -> tuple[float, float]:
        """
        Extrae el precio/cantidad REALMENTE ejecutados que confirma Binance.
        En órdenes de mercado el fill viene en 'average'/'filled'; si por algún
        motivo no llega, caemos al valor estimado para no romper el flujo.
        """
        price = order.get("average") or order.get("price") or fallback_price
        amount = order.get("filled") or fallback_amount
        return float(price), float(amount)

    def _account_totals(self) -> tuple[float, float]:
        """(quote_total, base_total) leídos de la API de Binance."""
        total = self.ex.fetch_balance().get("total", {})
        return float(total.get(self.quote, 0) or 0), float(total.get(self.base, 0) or 0)

    def _binance_equity(self, price: float) -> float:
        """Valor REAL de la cuenta de prueba, en quote (USDT)."""
        quote_amt, base_amt = self._account_totals()
        return quote_amt + base_amt * price

    def _bot_equity(self, price: float) -> float:
        """Equity que el BOT cree tener, según su propia contabilidad."""
        return self.cash + self.units * price

    def _init_bookkeeping(self, price: float) -> None:
        """Alinea la contabilidad del bot con el balance real al arrancar."""
        quote_amt, base_amt = self._account_totals()
        self.cash = quote_amt
        self.units = base_amt
        log.info("Contabilidad inicial: %.2f %s + %.6f %s (equity ~%.2f)",
                 quote_amt, self.quote, base_amt, self.base, self._bot_equity(price))

    # ------------------------------------------------------------------
    def _open_position(self, price: float, ctx: dict) -> None:
        """Compra a mercado usando position_size_pct del USDT disponible."""
        quote_to_spend = self.cash * RISK.position_size_pct
        if quote_to_spend <= 0:
            log.warning("Sin %s disponible para abrir posición. Pide fondos de prueba.",
                        self.quote)
            return

        base_amount = float(self.ex.amount_to_precision(self.symbol, quote_to_spend / price))
        order = self.ex.create_market_buy_order(self.symbol, base_amount)

        # Precio/cantidad REALES confirmados por Binance (no los estimados)
        fill_price, fill_amount = self._fill(order, price, base_amount)

        self.in_position = True
        self.units += fill_amount
        self.cash -= fill_amount * fill_price
        self.entry_price = fill_price
        self.stop_price = fill_price * (1 - RISK.stop_loss_pct)
        self.tp_price = fill_price * (1 + RISK.take_profit_pct)
        log.info(
            "ENTRADA  | COMPRA confirmada %.6f %s @ %.2f | SL=%.2f TP=%.2f | order_id=%s",
            fill_amount, self.symbol, fill_price, self.stop_price, self.tp_price, order.get("id"),
        )
        self.journal.record_trade(
            side="buy", price=fill_price, amount=fill_amount, order_id=str(order.get("id")),
            reason="ema_cross_alcista", ema_fast=ctx["ema_fast"], ema_slow=ctx["ema_slow"],
            rsi=ctx["rsi"],
        )

    def _close_position(self, price: float, reason: str, ctx: dict) -> None:
        """Vende a mercado toda la posición."""
        amount = float(self.ex.amount_to_precision(self.symbol, self.units))
        order = self.ex.create_market_sell_order(self.symbol, amount)

        # Precio/cantidad REALES confirmados por Binance (no los estimados)
        fill_price, fill_amount = self._fill(order, price, amount)
        pnl_pct = (fill_price / self.entry_price - 1) * 100

        self.cash += fill_amount * fill_price
        self.units -= fill_amount
        self.in_position = False
        log.info(
            "SALIDA   | VENTA confirmada motivo=%s | %.6f @ %.2f | PnL=%.2f%% | order_id=%s",
            reason, fill_amount, fill_price, pnl_pct, order.get("id"),
        )
        self.journal.record_trade(
            side="sell", price=fill_price, amount=fill_amount, order_id=str(order.get("id")),
            reason=reason, ema_fast=ctx["ema_fast"], ema_slow=ctx["ema_slow"],
            rsi=ctx["rsi"], pnl_pct=pnl_pct,
        )

    # ------------------------------------------------------------------
    def step(self) -> None:
        """Una iteración de la lógica de trading."""
        df = self._closed_candles()
        signal, ctx = self.strategy.latest_signal(df)
        price = self._current_price()

        log.info(
            "tick     | precio=%.2f | EMA%d=%.2f EMA%d=%.2f RSI=%.2f | señal=%+d | %s",
            price, STRATEGY.ema_fast, ctx["ema_fast"], STRATEGY.ema_slow, ctx["ema_slow"],
            ctx["rsi"], signal, "EN POSICIÓN" if self.in_position else "fuera",
        )

        if self.in_position:
            if price <= self.stop_price:
                self._close_position(price, "stop_loss", ctx)
            elif price >= self.tp_price:
                self._close_position(price, "take_profit", ctx)
            elif signal == -1:
                self._close_position(price, "ema_cross_bajista", ctx)
        elif signal == 1:
            log.info("Señal de ENTRADA detectada (cruce alcista + RSI=%.2f).", ctx["rsi"])
            self._open_position(price, ctx)

        # --- Snapshots para el dashboard (Fuente B) ---
        self.journal.record_equity(self._bot_equity(price), self._binance_equity(price))
        self.journal.update_status(
            running=True, price=price, ema_fast=ctx["ema_fast"], ema_slow=ctx["ema_slow"],
            rsi=ctx["rsi"], in_position=self.in_position,
            entry_price=self.entry_price if self.in_position else None,
        )

    # ------------------------------------------------------------------
    def run(self) -> None:
        log.info("=== Paper trading iniciado: %s %s ===", self.symbol, MARKET.timeframe)
        self._init_bookkeeping(self._current_price())
        backoff = POLL_SECONDS
        try:
            while True:
                try:
                    self.step()
                    backoff = POLL_SECONDS                 # reset tras éxito
                    time.sleep(POLL_SECONDS)
                except ccxt.RateLimitExceeded as e:
                    log.warning("Rate limit: espero %ds. %s", backoff, e)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 600)        # backoff exponencial (máx 10 min)
                except ccxt.NetworkError as e:
                    log.warning("Error de red (reintento en %ds): %s", backoff, e)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 600)
                except ccxt.ExchangeError as e:
                    log.error("Error del exchange (orden rechazada?): %s", e)
                    time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            log.info("Detenido por el usuario (Ctrl+C).")
        except Exception as e:                             # red de seguridad
            log.exception("Error inesperado: %s", e)
        finally:
            # Marca el bot como DETENIDO para que el dashboard lo refleje.
            self.journal.update_status(running=False)
            log.info("Estado del bot marcado como DETENIDO en el diario.")


def main() -> None:
    exchange = get_exchange()
    PaperTrader(exchange).run()


if __name__ == "__main__":
    main()
