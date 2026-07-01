"""
live/paper_trade.py
===================
Paper trading EN VIVO contra la Testnet de Binance Spot. Ejecuta órdenes de
mercado REALES pero con dinero FICTICIO de la cuenta de prueba.

    python -m live.paper_trade

Flujo del bucle:
  1. Descarga las últimas velas CERRADAS y calcula la señal.
  2. Comprueba el KILL-SWITCH de pérdida (diario/semanal) antes de operar.
  3. Si estamos FUERA y hay señal de entrada -> compra a mercado, fija SL/TP y
     coloca una orden STOP_LOSS_LIMIT REAL que queda descansando en Binance.
  4. Si estamos DENTRO -> vigila si el SL real ya se ejecutó, o sale por
     take-profit / cruce bajista (cancelando antes el SL real).
  5. Registra CADA decisión en logs/live.log Y en el diario SQLite (data/journal),
     y PERSISTE el estado para poder recuperarlo si el bot se reinicia.
  6. Maneja errores de red / rate limit con reintentos y backoff.

CONTABILIDAD LIMPIA: la estrategia lleva su propia posición (`position_units`)
y su propio efectivo (`cash`), SEPARADOS del resto de saldos de la cuenta. Así
el bot nunca vende monedas que no compró y las métricas son interpretables.

Es long-only y usa el saldo de USDT de la cuenta de prueba.
Pide fondos ficticios en https://testnet.binance.vision/ si el balance es 0.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timezone

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


class StopTrading(Exception):
    """Se alcanzó un límite de pérdida: hay que cerrar y detener el bot."""


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class PaperTrader:
    def __init__(self, exchange: ccxt.binance):
        self.ex = exchange
        self.strategy = EmaRsiStrategy(STRATEGY)
        self.symbol = MARKET.symbol
        self.base, self.quote = self.symbol.split("/")   # p.ej. "BTC", "USDT"
        self.journal = Journal()

        # --- Estado de la POSICIÓN de la estrategia (NO incluye saldos ajenos) ---
        self.in_position = False
        self.position_units = 0.0     # BTC comprado por la estrategia (solo eso)
        self.entry_price = 0.0
        self.stop_price = 0.0
        self.tp_price = 0.0
        self.sl_order_id: str | None = None   # id de la orden STOP real en Binance

        # --- Contabilidad VIRTUAL de la estrategia (para su equity) ---
        self.cash = 0.0               # USDT libre asignado a la estrategia
        self.initial_capital = 0.0    # equity de partida (para benchmark y %)
        self.price0 = 0.0             # precio de referencia del benchmark buy&hold

        # --- Kill-switch de pérdida ---
        self.day_start_equity = 0.0
        self.day_start_date = ""
        self.week_start_equity = 0.0
        self.week_start_date = ""

    # ==================================================================
    #  Lectura de mercado / cuenta
    # ==================================================================
    def _current_price(self) -> float:
        return float(self.ex.fetch_ticker(self.symbol)["last"])

    def _closed_candles(self):
        """Velas cerradas (descarta la última, que aún se está formando)."""
        df = fetch_ohlcv(self.ex, self.symbol, MARKET.timeframe, limit=CANDLES_TO_FETCH)
        return df.iloc[:-1]

    def _usdt_total(self) -> float:
        total = self.ex.fetch_balance().get("total", {})
        return float(total.get(self.quote, 0) or 0)

    @staticmethod
    def _fill(order: dict, fallback_price: float, fallback_amount: float) -> tuple[float, float]:
        """Precio/cantidad REALMENTE ejecutados que confirma Binance (con respaldo)."""
        price = order.get("average") or order.get("price") or fallback_price
        amount = order.get("filled") or fallback_amount
        return float(price), float(amount)

    # ==================================================================
    #  Equity de la estrategia y benchmark
    # ==================================================================
    def _strategy_equity(self, price: float) -> float:
        """Equity de la estrategia = efectivo + valor de SU posición."""
        return self.cash + self.position_units * price

    def _benchmark_equity(self, price: float) -> float:
        """Comprar-y-mantener: qué valdría el capital inicial si solo hubieras HODLeado."""
        if self.price0 <= 0:
            return self.initial_capital
        return self.initial_capital * (price / self.price0)

    # ==================================================================
    #  Persistencia de estado (recuperación tras reinicio)
    # ==================================================================
    def _persist(self) -> None:
        self.journal.save_position({
            "in_position": int(self.in_position),
            "position_units": self.position_units,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "tp_price": self.tp_price,
            "sl_order_id": self.sl_order_id,
            "cash": self.cash,
            "initial_capital": self.initial_capital,
            "price0": self.price0,
            "day_start_equity": self.day_start_equity,
            "day_start_date": self.day_start_date,
            "week_start_equity": self.week_start_equity,
            "week_start_date": self.week_start_date,
        })

    def _bootstrap(self) -> None:
        """Arranque: recupera estado previo si existe, o inicia limpio."""
        price = self._current_price()
        _, ctx = self.strategy.latest_signal(self._closed_candles())
        saved = self.journal.load_position()
        if saved and saved.get("initial_capital"):
            self._restore(saved, price, ctx)
        else:
            self._fresh_start(price)

    def _fresh_start(self, price: float) -> None:
        usdt = self._usdt_total()
        self.cash = usdt
        self.initial_capital = usdt
        self.price0 = price
        self.in_position = False
        self.position_units = 0.0
        self.sl_order_id = None
        self.day_start_equity = self.week_start_equity = usdt
        self.day_start_date = self.week_start_date = _today()
        self._persist()
        log.info("Inicio LIMPIO | capital estrategia=%.2f %s | precio ref=%.2f",
                 usdt, self.quote, price)

    def _restore(self, s: dict, price: float, ctx: dict) -> None:
        self.in_position = bool(s.get("in_position"))
        self.position_units = float(s.get("position_units") or 0)
        self.entry_price = float(s.get("entry_price") or 0)
        self.stop_price = float(s.get("stop_price") or 0)
        self.tp_price = float(s.get("tp_price") or 0)
        self.sl_order_id = s.get("sl_order_id") or None
        self.cash = float(s.get("cash") or 0)
        self.initial_capital = float(s.get("initial_capital") or self.cash)
        self.price0 = float(s.get("price0") or price)
        self.day_start_equity = float(s.get("day_start_equity") or self.initial_capital)
        self.day_start_date = s.get("day_start_date") or _today()
        self.week_start_equity = float(s.get("week_start_equity") or self.initial_capital)
        self.week_start_date = s.get("week_start_date") or _today()
        log.info("Estado RECUPERADO | %s | cash=%.2f units=%.6f entry=%.2f SL=%.2f TP=%.2f",
                 "EN POSICIÓN" if self.in_position else "fuera",
                 self.cash, self.position_units, self.entry_price, self.stop_price, self.tp_price)
        # ¿El SL real se ejecutó mientras el bot estaba caído?
        if self.in_position and self.sl_order_id:
            self._check_sl_order(price, ctx)

    # ==================================================================
    #  Órdenes de stop-loss REALES en Binance
    # ==================================================================
    def _place_stop_order(self) -> None:
        """Coloca un STOP_LOSS_LIMIT de venta que queda descansando en Binance."""
        if not RISK.use_exchange_stop:
            self.sl_order_id = None
            return
        try:
            amount = float(self.ex.amount_to_precision(self.symbol, self.position_units))
            stop = float(self.ex.price_to_precision(self.symbol, self.stop_price))
            limit = float(self.ex.price_to_precision(
                self.symbol, self.stop_price * (1 - RISK.stop_limit_buffer_pct)))
            order = self.ex.create_order(
                self.symbol, "STOP_LOSS_LIMIT", "sell", amount, limit,
                {"stopPrice": stop, "timeInForce": "GTC"},
            )
            self.sl_order_id = str(order.get("id"))
            log.info("SL REAL colocado en Binance | stop=%.2f limit=%.2f | order_id=%s",
                     stop, limit, self.sl_order_id)
        except Exception as e:                                  # noqa: BLE001
            self.sl_order_id = None
            log.warning("No se pudo colocar SL real (%s). Uso SL interno por sondeo.", e)

    def _cancel_stop_order(self) -> None:
        if not self.sl_order_id:
            return
        try:
            self.ex.cancel_order(self.sl_order_id, self.symbol)
            log.info("SL real cancelado (order_id=%s).", self.sl_order_id)
        except Exception as e:                                  # noqa: BLE001
            log.warning("No se pudo cancelar el SL real %s (%s).", self.sl_order_id, e)
        finally:
            self.sl_order_id = None

    def _check_sl_order(self, price: float, ctx: dict) -> bool:
        """¿La orden STOP real ya se ejecutó? Si sí, contabiliza el cierre."""
        if not self.sl_order_id:
            return False
        try:
            o = self.ex.fetch_order(self.sl_order_id, self.symbol)
        except Exception as e:                                  # noqa: BLE001
            log.warning("No se pudo consultar el SL real %s (%s).", self.sl_order_id, e)
            return False
        status = o.get("status")
        if status == "closed":
            fill_price, fill_amount = self._fill(o, self.stop_price, self.position_units)
            log.info("SL REAL EJECUTADO por Binance @ %.2f (order_id=%s).",
                     fill_price, self.sl_order_id)
            self.sl_order_id = None
            self._book_close(fill_price, fill_amount, "stop_loss", ctx, order_id=str(o.get("id")))
            return True
        if status in ("canceled", "expired", "rejected"):
            self.sl_order_id = None
        return False

    # ==================================================================
    #  Apertura / cierre de posición
    # ==================================================================
    def _open_position(self, price: float, ctx: dict) -> None:
        quote_to_spend = self.cash * RISK.position_size_pct
        if quote_to_spend <= 0:
            log.warning("Sin %s disponible para abrir posición. Pide fondos de prueba.",
                        self.quote)
            return

        base_amount = float(self.ex.amount_to_precision(self.symbol, quote_to_spend / price))
        order = self.ex.create_market_buy_order(self.symbol, base_amount)
        fill_price, fill_amount = self._fill(order, price, base_amount)

        self.in_position = True
        self.position_units = fill_amount
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
        self._place_stop_order()   # deja el SL real descansando en el exchange
        self._persist()

    def _market_close(self, price: float, reason: str, ctx: dict) -> None:
        """Venta a mercado de la posición (cancela antes el SL real si existe)."""
        self._cancel_stop_order()
        amount = float(self.ex.amount_to_precision(self.symbol, self.position_units))
        order = self.ex.create_market_sell_order(self.symbol, amount)
        fill_price, fill_amount = self._fill(order, price, amount)
        self._book_close(fill_price, fill_amount, reason, ctx, order_id=str(order.get("id")))

    def _book_close(self, fill_price: float, fill_amount: float, reason: str,
                    ctx: dict, order_id: str | None) -> None:
        """Contabiliza un cierre (venga de venta a mercado o del SL real ya ejecutado)."""
        pnl_pct = (fill_price / self.entry_price - 1) * 100 if self.entry_price else 0.0
        self.cash += fill_amount * fill_price
        self.position_units -= fill_amount
        if self.position_units < 1e-9:
            self.position_units = 0.0
        self.in_position = False
        self.entry_price = self.stop_price = self.tp_price = 0.0
        log.info(
            "SALIDA   | VENTA confirmada motivo=%s | %.6f @ %.2f | PnL=%.2f%% | order_id=%s",
            reason, fill_amount, fill_price, pnl_pct, order_id,
        )
        self.journal.record_trade(
            side="sell", price=fill_price, amount=fill_amount, order_id=order_id,
            reason=reason, ema_fast=ctx["ema_fast"], ema_slow=ctx["ema_slow"],
            rsi=ctx["rsi"], pnl_pct=pnl_pct,
        )
        self._persist()

    # ==================================================================
    #  Gestión de riesgo temporal (kill-switch)
    # ==================================================================
    def _roll_periods(self, price: float) -> None:
        """Reinicia la referencia de pérdida al cambiar de día / de semana."""
        today = _today()
        if self.day_start_date != today:
            self.day_start_date = today
            self.day_start_equity = self._strategy_equity(price)
            log.info("Nuevo día: referencia de pérdida diaria = %.2f", self.day_start_equity)
        if self.week_start_date:
            days = (date.fromisoformat(today) - date.fromisoformat(self.week_start_date)).days
            if days >= 7:
                self.week_start_date = today
                self.week_start_equity = self._strategy_equity(price)
                log.info("Nueva semana: referencia de pérdida semanal = %.2f",
                         self.week_start_equity)

    def _check_loss_limits(self, price: float, ctx: dict) -> None:
        equity = self._strategy_equity(price)
        breach = None
        if equity <= self.day_start_equity * (1 - RISK.max_daily_loss_pct):
            breach = f"pérdida DIARIA máx ({RISK.max_daily_loss_pct*100:.0f}%)"
        elif equity <= self.week_start_equity * (1 - RISK.max_weekly_loss_pct):
            breach = f"pérdida SEMANAL máx ({RISK.max_weekly_loss_pct*100:.0f}%)"
        if breach:
            log.error("KILL-SWITCH: %s alcanzado. Equity=%.2f. Cerrando y deteniendo.",
                      breach, equity)
            if self.in_position:
                self._market_close(price, "kill_switch", ctx)
            raise StopTrading(breach)

    # ==================================================================
    #  Una iteración
    # ==================================================================
    def step(self) -> None:
        df = self._closed_candles()
        signal, ctx = self.strategy.latest_signal(df)
        price = self._current_price()

        log.info(
            "tick     | precio=%.2f | EMA%d=%.2f EMA%d=%.2f RSI=%.2f | señal=%+d | %s | equity=%.2f",
            price, STRATEGY.ema_fast, ctx["ema_fast"], STRATEGY.ema_slow, ctx["ema_slow"],
            ctx["rsi"], signal, "EN POSICIÓN" if self.in_position else "fuera",
            self._strategy_equity(price),
        )

        # 1) Gestión de riesgo temporal (puede detener el bot)
        self._roll_periods(price)
        self._check_loss_limits(price, ctx)

        # 2) Gestión de la posición
        if self.in_position:
            if self._check_sl_order(price, ctx):
                pass                                            # el SL real ya cerró
            elif price >= self.tp_price:
                self._market_close(price, "take_profit", ctx)
            elif signal == -1:
                self._market_close(price, "ema_cross_bajista", ctx)
            elif self.sl_order_id is None and price <= self.stop_price:
                self._market_close(price, "stop_loss", ctx)    # respaldo si no hay SL real
        elif signal == 1:
            log.info("Señal de ENTRADA detectada (cruce alcista + RSI=%.2f).", ctx["rsi"])
            self._open_position(price, ctx)

        # 3) Snapshots para el dashboard
        self.journal.record_equity(self._strategy_equity(price), self._benchmark_equity(price))
        self.journal.update_status(
            running=True, price=price, ema_fast=ctx["ema_fast"], ema_slow=ctx["ema_slow"],
            rsi=ctx["rsi"], in_position=self.in_position,
            entry_price=self.entry_price if self.in_position else None,
        )
        self._persist()

    # ==================================================================
    #  Bucle principal
    # ==================================================================
    def run(self) -> None:
        log.info("=== Paper trading iniciado: %s %s ===", self.symbol, MARKET.timeframe)
        self._bootstrap()
        backoff = POLL_SECONDS
        try:
            while True:
                try:
                    self.step()
                    backoff = POLL_SECONDS
                    time.sleep(POLL_SECONDS)
                except StopTrading as e:
                    log.error("Bot DETENIDO por gestión de riesgo: %s", e)
                    break
                except ccxt.RateLimitExceeded as e:
                    log.warning("Rate limit: espero %ds. %s", backoff, e)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 600)
                except ccxt.NetworkError as e:
                    log.warning("Error de red (reintento en %ds): %s", backoff, e)
                    time.sleep(backoff)
                    backoff = min(backoff * 2, 600)
                except ccxt.ExchangeError as e:
                    log.error("Error del exchange (orden rechazada?): %s", e)
                    time.sleep(POLL_SECONDS)
        except KeyboardInterrupt:
            log.info("Detenido por el usuario (Ctrl+C).")
        except Exception as e:                                 # red de seguridad
            log.exception("Error inesperado: %s", e)
        finally:
            self.journal.update_status(running=False)
            self._persist()
            log.info("Estado del bot marcado como DETENIDO en el diario.")


def main() -> None:
    exchange = get_exchange()
    PaperTrader(exchange).run()


if __name__ == "__main__":
    main()
