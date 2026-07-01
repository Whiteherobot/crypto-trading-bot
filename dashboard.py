"""
dashboard.py  —  Front de control y verificación del bot (local)
================================================================
Ejecutar con:

    streamlit run dashboard.py

Lee DOS fuentes y deja claro cuál es cuál:
  🟢 FUENTE A — API de Binance Testnet : la verdad oficial de qué se ejecutó.
  🔵 FUENTE B — Diario SQLite del bot   : el razonamiento detrás de cada orden.

Si una orden aparece en una fuente y no en la otra, se resalta como alerta.
Auto-refresco configurable en la barra lateral. Sin auth ni despliegue: 100% local.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from config.config import MARKET, STRATEGY
from data.data_fetcher import fetch_ohlcv
from data.journal import Journal
from strategy.ema_rsi_strategy import EmaRsiStrategy

# Si el último heartbeat del bot es más viejo que esto, lo consideramos DETENIDO
STALE_SECONDS = 180

st.set_page_config(page_title="Cryptobot — Panel de control", layout="wide")


# ======================================================================
#  Recursos cacheados y helpers
# ======================================================================
@st.cache_resource(show_spinner=False)
def get_journal() -> Journal:
    return Journal()


@st.cache_resource(show_spinner=False)
def get_exchange():
    """Conexión a Binance Testnet. Devuelve None si no está configurada."""
    try:
        from utils.exchange import get_exchange as _connect
        return _connect()
    except Exception as e:          # sin .env / sin claves -> el panel sigue con Fuente B
        st.session_state["exchange_error"] = str(e)
        return None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def naive(series: pd.Series) -> pd.Series:
    """Quita timezone para poder mezclar con el índice (naive) de las velas."""
    s = pd.to_datetime(series)
    return s.dt.tz_localize(None) if s.dt.tz is not None else s


# ======================================================================
#  Barra lateral: controles
# ======================================================================
st.sidebar.title("⚙️ Controles")
refresh_s = st.sidebar.slider("Auto-refresco (segundos)", 5, 120, 30, step=5)
if st.sidebar.button("🔄 Refrescar ahora"):
    st.rerun()
st.sidebar.caption(
    "🟢 = dato de **Binance Testnet** (verdad oficial)\n\n"
    "🔵 = dato del **diario del bot** (razonamiento)"
)

# Dispara un rerun automático cada `refresh_s` segundos
st_autorefresh(interval=refresh_s * 1000, key="auto_refresh")

journal = get_journal()
exchange = get_exchange()
status = journal.status()
trades = journal.trades_df()
equity = journal.equity_df()

st.title("🤖 Cryptobot — Panel de control")
st.caption(f"Par: **{MARKET.symbol}** · Timeframe: **{MARKET.timeframe}** · "
           f"Última carga del panel: {now_utc():%Y-%m-%d %H:%M:%S} UTC")


# ======================================================================
#  d) ESTADO DEL BOT
# ======================================================================
st.header("🩺 Estado del bot")

def bot_is_running(status: dict | None) -> bool:
    if not status or not status.get("running"):
        return False
    last = pd.to_datetime(status["ts"], utc=True)
    return (now_utc() - last.to_pydatetime()).total_seconds() < STALE_SECONDS

c1, c2, c3, c4 = st.columns(4)
if bot_is_running(status):
    c1.success("🟢 CORRIENDO")
else:
    c1.error("🔴 DETENIDO")

if status:
    c2.metric(f"EMA{STRATEGY.ema_fast}", f"{status['ema_fast']:.2f}" if status['ema_fast'] else "—")
    c3.metric(f"EMA{STRATEGY.ema_slow}", f"{status['ema_slow']:.2f}" if status['ema_slow'] else "—")
    rsi_val = status["rsi"]
    c4.metric("RSI", f"{rsi_val:.1f}" if rsi_val else "—")
    # Pista de cercanía a la próxima señal
    if status["ema_fast"] and status["ema_slow"]:
        gap = (status["ema_fast"] - status["ema_slow"]) / status["ema_slow"] * 100
        signo = "rápida ARRIBA" if gap > 0 else "rápida ABAJO"
        st.caption(f"🔵 Separación EMA{STRATEGY.ema_fast}/EMA{STRATEGY.ema_slow}: "
                   f"{gap:+.2f}% ({signo}) · último heartbeat: {status['ts']}")
else:
    st.info("Aún no hay datos del bot. Arráncalo con `python -m live.paper_trade`.")

st.divider()


# ======================================================================
#  a) RESUMEN DE CUENTA (en vivo desde la API)
# ======================================================================
st.header("💰 Resumen de cuenta  ·  🟢 Binance Testnet (en vivo)")

base, quote = MARKET.symbol.split("/")
live_price = None
if exchange is not None:
    try:
        bal = exchange.fetch_balance()
        live_price = float(exchange.fetch_ticker(MARKET.symbol)["last"])
        total = bal.get("total", {})
        a1, a2, a3 = st.columns(3)
        a1.metric(f"🟢 Saldo {quote}", f"{total.get(quote, 0):,.2f}")
        a2.metric(f"🟢 Saldo {base}", f"{total.get(base, 0):,.6f}")
        a3.metric(f"🟢 Precio {MARKET.symbol}", f"{live_price:,.2f}")

        # Posición abierta: la define el bot (Binance spot no guarda precio de entrada)
        if status and status.get("in_position") and status.get("entry_price"):
            entry = float(status["entry_price"])
            base_amt = float(total.get(base, 0) or 0)
            pnl_pct = (live_price / entry - 1) * 100
            pnl_abs = base_amt * (live_price - entry)
            st.subheader("📌 Posición abierta")
            p1, p2, p3 = st.columns(3)
            p1.metric("🔵 Precio de entrada", f"{entry:,.2f}")
            p2.metric("PnL no realizado %", f"{pnl_pct:+.2f}%")
            p3.metric(f"PnL no realizado ({quote})", f"{pnl_abs:+,.2f}")
        else:
            st.info("Sin posición abierta actualmente (🔵 según el bot).")
    except Exception as e:
        st.error(f"No se pudo leer la cuenta de Binance: {e}")
else:
    st.warning("⚠️ Sin conexión a Binance (revisa el `.env`). "
               f"Detalle: {st.session_state.get('exchange_error', 'desconocido')}")

st.divider()


# ======================================================================
#  b) HISTORIAL DE OPERACIONES  +  2) SINCRONIZACIÓN DE FUENTES
# ======================================================================
st.header("📜 Historial de operaciones  ·  reconciliación 🟢 Binance ↔ 🔵 Bot")

def binance_trades_df() -> pd.DataFrame:
    if exchange is None:
        return pd.DataFrame()
    try:
        rows = exchange.fetch_my_trades(MARKET.symbol, limit=100)
    except Exception as e:
        st.warning(f"No se pudo leer el historial de Binance: {e}")
        return pd.DataFrame()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(
        [{"order_id": str(r.get("order")), "ts": r.get("datetime"), "side": r.get("side"),
          "price": r.get("price"), "amount": r.get("amount")} for r in rows]
    )
    # Una orden puede tener varios fills: agregamos por order_id
    return (df.groupby("order_id")
              .agg(ts=("ts", "first"), side=("side", "first"),
                   price=("price", "mean"), amount=("amount", "sum"))
              .reset_index())

bin_df = binance_trades_df()

# --- Alertas de sincronización ---
local_ids = set(trades["order_id"].dropna().astype(str)) if not trades.empty else set()
bin_ids = set(bin_df["order_id"]) if not bin_df.empty else set()

solo_binance = bin_ids - local_ids   # ejecutadas en Binance sin registro local
solo_local = local_ids - bin_ids     # registradas por el bot sin confirmar en Binance

if solo_binance:
    st.error(f"🚨 {len(solo_binance)} orden(es) en Binance SIN registro local del bot: "
             f"{', '.join(sorted(solo_binance))}")
if solo_local:
    st.warning(f"⚠️ {len(solo_local)} orden(es) del bot SIN confirmar en Binance: "
               f"{', '.join(sorted(solo_local))}")
if not solo_binance and not solo_local and (local_ids or bin_ids):
    st.success("✅ Fuentes sincronizadas: cada orden del bot está confirmada en Binance.")

# --- Tabla combinada (razón del bot + confirmación de Binance) ---
if not trades.empty:
    view = trades.copy()
    view["confirmada_binance"] = view["order_id"].astype(str).isin(bin_ids)
    view["estado"] = view["confirmada_binance"].map(
        {True: "✅ Confirmada", False: "⚠️ Sin confirmar en Binance"})
    view = view.rename(columns={
        "ts": "fecha/hora", "side": "tipo", "price": "precio", "amount": "cantidad",
        "reason": "motivo (🔵 bot)", "pnl_pct": "resultado %"})
    cols = ["fecha/hora", "tipo", "precio", "cantidad", "motivo (🔵 bot)",
            "resultado %", "ema_fast", "ema_slow", "rsi", "estado", "order_id"]
    st.dataframe(view[cols].sort_values("fecha/hora", ascending=False),
                 width="stretch", hide_index=True)
else:
    st.info("Todavía no hay operaciones registradas por el bot.")

with st.expander("🟢 Ver historial crudo de Binance (Fuente A)"):
    st.dataframe(bin_df if not bin_df.empty else pd.DataFrame({"info": ["sin datos"]}),
                 width="stretch", hide_index=True)

st.divider()


# ======================================================================
#  c) GRÁFICAS
# ======================================================================
st.header("📈 Gráficas")

# --- 1) Curva de equity: estrategia vs comprar-y-mantener ---
st.subheader("Curva de equity  ·  🔵 Estrategia del bot vs 🟢 Comprar y mantener")
if not equity.empty:
    fig_eq = go.Figure()
    fig_eq.add_trace(go.Scatter(x=equity["ts"], y=equity["bot_equity"],
                                name="🔵 Estrategia", line=dict(color="#1c7ed6")))
    fig_eq.add_trace(go.Scatter(x=equity["ts"], y=equity["benchmark_equity"],
                                name="🟢 Comprar y mantener", line=dict(color="#2f9e44")))
    fig_eq.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10),
                         yaxis_title=f"Equity ({quote})", legend=dict(orientation="h"))
    st.plotly_chart(fig_eq, width="stretch")

    # ¿La estrategia le gana a simplemente HODLear?
    strat = equity["bot_equity"].iloc[-1]
    hold = equity["benchmark_equity"].iloc[-1]
    diff_pct = (strat / hold - 1) * 100 if hold else 0.0
    start = equity["bot_equity"].iloc[0]
    ret_pct = (strat / start - 1) * 100 if start else 0.0
    m1, m2 = st.columns(2)
    m1.metric("Retorno estrategia", f"{ret_pct:+.2f}%")
    m2.metric("vs comprar-y-mantener", f"{diff_pct:+.2f}%",
              help="Positivo = la estrategia va mejor que solo HODLear.")
    if diff_pct >= 0:
        st.success(f"✅ La estrategia va {diff_pct:+.2f}% respecto a comprar y mantener.")
    else:
        st.warning(f"⚠️ La estrategia va {diff_pct:+.2f}% respecto a comprar y mantener "
                   "(por ahora HODLear habría sido mejor).")
else:
    st.info("Sin snapshots de equity todavía (el bot los va generando al correr).")

# --- 2) Velas + EMAs + marcadores de compra/venta ---
st.subheader("Velas + EMAs + señales del bot")
if exchange is not None:
    try:
        ohlcv = fetch_ohlcv(exchange, MARKET.symbol, MARKET.timeframe, limit=200)
        ind = EmaRsiStrategy(STRATEGY).compute_indicators(ohlcv)
        fig_c = go.Figure()
        fig_c.add_trace(go.Candlestick(
            x=ind.index, open=ind["open"], high=ind["high"], low=ind["low"],
            close=ind["close"], name=MARKET.symbol))
        fig_c.add_trace(go.Scatter(x=ind.index, y=ind["ema_fast"],
                                   name=f"EMA{STRATEGY.ema_fast}", line=dict(color="#f59f00")))
        fig_c.add_trace(go.Scatter(x=ind.index, y=ind["ema_slow"],
                                   name=f"EMA{STRATEGY.ema_slow}", line=dict(color="#7048e8")))
        if not trades.empty:
            buys = trades[trades["side"] == "buy"]
            sells = trades[trades["side"] == "sell"]
            fig_c.add_trace(go.Scatter(
                x=naive(buys["ts"]), y=buys["price"], mode="markers", name="🔵 Compra",
                marker=dict(symbol="triangle-up", size=12, color="#2f9e44")))
            fig_c.add_trace(go.Scatter(
                x=naive(sells["ts"]), y=sells["price"], mode="markers", name="🔵 Venta",
                marker=dict(symbol="triangle-down", size=12, color="#e03131")))
        fig_c.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10),
                            xaxis_rangeslider_visible=False, legend=dict(orientation="h"))
        st.plotly_chart(fig_c, width="stretch")
    except Exception as e:
        st.error(f"No se pudo construir el gráfico de velas: {e}")
else:
    st.info("Conecta Binance (.env) para ver el gráfico de velas.")

# --- 3) Drawdown ---
st.subheader("Drawdown a lo largo del tiempo  ·  🔵 sobre equity de la estrategia")
if not equity.empty:
    eq = equity.set_index("ts")["bot_equity"]
    dd = (eq - eq.cummax()) / eq.cummax() * 100
    fig_dd = go.Figure()
    fig_dd.add_trace(go.Scatter(x=dd.index, y=dd.values, fill="tozeroy",
                                line=dict(color="#e03131"), name="Drawdown %"))
    fig_dd.update_layout(height=260, margin=dict(l=10, r=10, t=10, b=10),
                         yaxis_title="Drawdown %")
    st.plotly_chart(fig_dd, width="stretch")
    st.caption(f"Drawdown máximo observado: {dd.min():.2f}%")
else:
    st.info("Sin datos de equity para calcular drawdown todavía.")
