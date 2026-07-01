"""
data/journal.py
===============
Diario estructurado del bot en SQLite (stdlib, sin dependencias nuevas).
Es la "Fuente B" del dashboard: el razonamiento interno del bot.

El bot (live/paper_trade.py) ESCRIBE aquí; el dashboard LEE. Como son procesos
distintos, activamos WAL para permitir lectura concurrente sin bloqueos.

Tablas:
  - trades : cada orden ejecutada, con su order_id, motivo e indicadores
             en el momento de la decisión (para cruzar con la API de Binance).
  - equity : snapshots de equity de la ESTRATEGIA vs benchmark comprar-y-mantener.
  - bot_status : una sola fila = heartbeat + últimos indicadores + posición.
  - position_state : una sola fila = estado persistente de la posición, para
                     poder RECUPERARLO si el bot se reinicia (crash, reboot).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

DEFAULT_DB = Path(__file__).resolve().parent / "cryptobot.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Journal:
    def __init__(self, db_path: Path | str = DEFAULT_DB):
        self.db_path = str(db_path)
        self._init_db()

    # ------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.execute("PRAGMA journal_mode=WAL;")      # lectura concurrente
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS trades (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts        TEXT NOT NULL,
                    side      TEXT NOT NULL,          -- buy | sell
                    price     REAL NOT NULL,
                    amount    REAL NOT NULL,
                    order_id  TEXT,
                    reason    TEXT,                   -- por qué se tomó la decisión
                    ema_fast  REAL,
                    ema_slow  REAL,
                    rsi       REAL,
                    pnl_pct   REAL                    -- solo en ventas (cierres)
                );

                CREATE TABLE IF NOT EXISTS equity (
                    ts               TEXT NOT NULL,
                    bot_equity       REAL NOT NULL,
                    benchmark_equity REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS bot_status (
                    id          INTEGER PRIMARY KEY CHECK (id = 1),
                    ts          TEXT,
                    running     INTEGER,
                    price       REAL,
                    ema_fast    REAL,
                    ema_slow    REAL,
                    rsi         REAL,
                    in_position INTEGER,
                    entry_price REAL
                );

                CREATE TABLE IF NOT EXISTS position_state (
                    id               INTEGER PRIMARY KEY CHECK (id = 1),
                    ts               TEXT,
                    in_position      INTEGER,
                    position_units   REAL,
                    entry_price      REAL,
                    stop_price       REAL,
                    tp_price         REAL,
                    sl_order_id      TEXT,
                    cash             REAL,
                    initial_capital  REAL,
                    price0           REAL,
                    day_start_equity REAL,
                    day_start_date   TEXT,
                    week_start_equity REAL,
                    week_start_date  TEXT
                );
                """
            )

    # ------------------------------------------------------------------
    # Escritura (la usa el bot)
    # ------------------------------------------------------------------
    def record_trade(
        self,
        side: str,
        price: float,
        amount: float,
        order_id: str | None,
        reason: str,
        ema_fast: float | None = None,
        ema_slow: float | None = None,
        rsi: float | None = None,
        pnl_pct: float | None = None,
        ts: str | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO trades
                   (ts, side, price, amount, order_id, reason, ema_fast, ema_slow, rsi, pnl_pct)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (ts or _now_iso(), side, price, amount, order_id, reason,
                 ema_fast, ema_slow, rsi, pnl_pct),
            )

    def record_equity(self, bot_equity: float, benchmark_equity: float, ts: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO equity (ts, bot_equity, benchmark_equity) VALUES (?,?,?)",
                (ts or _now_iso(), bot_equity, benchmark_equity),
            )

    def update_status(
        self,
        running: bool,
        price: float | None = None,
        ema_fast: float | None = None,
        ema_slow: float | None = None,
        rsi: float | None = None,
        in_position: bool = False,
        entry_price: float | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO bot_status
                   (id, ts, running, price, ema_fast, ema_slow, rsi, in_position, entry_price)
                   VALUES (1,?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     ts=excluded.ts, running=excluded.running, price=excluded.price,
                     ema_fast=excluded.ema_fast, ema_slow=excluded.ema_slow, rsi=excluded.rsi,
                     in_position=excluded.in_position, entry_price=excluded.entry_price""",
                (_now_iso(), int(running), price, ema_fast, ema_slow, rsi,
                 int(in_position), entry_price),
            )

    # ------------------------------------------------------------------
    # Lectura (la usa el dashboard)
    # ------------------------------------------------------------------
    def trades_df(self) -> pd.DataFrame:
        with self._connect() as conn:
            return pd.read_sql_query(
                "SELECT * FROM trades ORDER BY ts", conn, parse_dates=["ts"]
            )

    def equity_df(self) -> pd.DataFrame:
        with self._connect() as conn:
            return pd.read_sql_query(
                "SELECT * FROM equity ORDER BY ts", conn, parse_dates=["ts"]
            )

    def status(self) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM bot_status WHERE id = 1").fetchone()
            return dict(row) if row else None

    # ------------------------------------------------------------------
    # Estado persistente de la posición (para recuperar tras un reinicio)
    # ------------------------------------------------------------------
    _POSITION_FIELDS = (
        "in_position", "position_units", "entry_price", "stop_price", "tp_price",
        "sl_order_id", "cash", "initial_capital", "price0",
        "day_start_equity", "day_start_date", "week_start_equity", "week_start_date",
    )

    def save_position(self, state: dict) -> None:
        """Guarda (upsert) el estado completo de la posición en una sola fila."""
        cols = ", ".join(self._POSITION_FIELDS)
        placeholders = ", ".join("?" for _ in self._POSITION_FIELDS)
        updates = ", ".join(f"{c}=excluded.{c}" for c in self._POSITION_FIELDS)
        values = [state.get(f) for f in self._POSITION_FIELDS]
        with self._connect() as conn:
            conn.execute(
                f"""INSERT INTO position_state (id, ts, {cols})
                    VALUES (1, ?, {placeholders})
                    ON CONFLICT(id) DO UPDATE SET ts=excluded.ts, {updates}""",
                [_now_iso(), *values],
            )

    def load_position(self) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM position_state WHERE id = 1").fetchone()
            return dict(row) if row else None
