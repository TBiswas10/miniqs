from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from .event_schemas import EventMessage


class EventStore:
    def __init__(self, db_path: Path, jsonl_path: Path) -> None:
        self.db_path = db_path
        self.jsonl_path = jsonl_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    strategy_id TEXT,
                    symbol TEXT,
                    session_id TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    side TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    reason TEXT NOT NULL,
                    symbol TEXT
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    order_id TEXT,
                    strategy TEXT,
                    state TEXT NOT NULL,
                    symbol TEXT,
                    expected_price REAL,
                    fill_price REAL,
                    slippage REAL,
                    fees REAL,
                    payload TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    equity REAL,
                    total_pnl REAL,
                    cash REAL,
                    position_size REAL,
                    drawdown REAL,
                    payload TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS risk_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    risk_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    strategy TEXT,
                    payload TEXT NOT NULL
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_events_type_ts ON events(event_type, ts)")
            conn.commit()
        finally:
            conn.close()

    def persist(self, event: EventMessage) -> None:
        record = event.model_dump()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO events(ts, event_type, source, strategy_id, symbol, session_id, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.ts,
                    event.event_type,
                    event.source,
                    event.strategy_id,
                    event.symbol,
                    event.session_id,
                    json.dumps(event.payload, default=str),
                ),
            )

            if event.event_type == "strategy_signal":
                conn.execute(
                    """
                    INSERT INTO signals(ts, strategy, side, confidence, reason, symbol)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.ts,
                        event.strategy_id or str(event.payload.get("strategy", "unknown")),
                        str(event.payload.get("side", "HOLD")),
                        float(event.payload.get("confidence", 0.0)),
                        str(event.payload.get("reason", "")),
                        event.symbol,
                    ),
                )
            elif event.event_type == "order_update":
                expected_price = float(event.payload.get("expected_price", 0.0) or 0.0)
                fill_price = float(event.payload.get("fill_price", expected_price) or expected_price)
                conn.execute(
                    """
                    INSERT INTO orders(ts, order_id, strategy, state, symbol, expected_price, fill_price, slippage, fees, payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.ts,
                        str(event.payload.get("order_id", "")),
                        event.strategy_id,
                        str(event.payload.get("state", "created")),
                        event.symbol,
                        expected_price,
                        fill_price,
                        float(event.payload.get("slippage", fill_price - expected_price)),
                        float(event.payload.get("fees", 0.0)),
                        json.dumps(event.payload, default=str),
                    ),
                )
            elif event.event_type == "portfolio_update":
                conn.execute(
                    """
                    INSERT INTO portfolio_snapshots(ts, equity, total_pnl, cash, position_size, drawdown, payload)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.ts,
                        float(event.payload.get("equity", 0.0) or 0.0),
                        float(event.payload.get("total_pnl", 0.0) or 0.0),
                        float(event.payload.get("cash", 0.0) or 0.0),
                        float(event.payload.get("position_size", 0.0) or 0.0),
                        float(event.payload.get("drawdown", 0.0) or 0.0),
                        json.dumps(event.payload, default=str),
                    ),
                )
            elif event.event_type == "risk_event":
                conn.execute(
                    """
                    INSERT INTO risk_events(ts, risk_type, severity, reason, strategy, payload)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.ts,
                        str(event.payload.get("risk_type", "generic")),
                        str(event.payload.get("severity", "warn")),
                        str(event.payload.get("reason", "")),
                        event.strategy_id,
                        json.dumps(event.payload, default=str),
                    ),
                )

            conn.commit()
        finally:
            conn.close()

        with self.jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")

    def recent_events(self, limit: int = 200, event_type: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            if event_type:
                rows = conn.execute(
                    """
                    SELECT ts, event_type, source, strategy_id, symbol, session_id, payload
                    FROM events WHERE event_type = ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (event_type, int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT ts, event_type, source, strategy_id, symbol, session_id, payload
                    FROM events ORDER BY id DESC LIMIT ?
                    """,
                    (int(limit),),
                ).fetchall()
        finally:
            conn.close()

        out: List[Dict[str, Any]] = []
        for row in reversed(rows):
            out.append(
                {
                    "ts": row["ts"],
                    "event_type": row["event_type"],
                    "source": row["source"],
                    "strategy_id": row["strategy_id"],
                    "symbol": row["symbol"],
                    "session_id": row["session_id"],
                    "payload": json.loads(row["payload"]),
                }
            )
        return out

    def replay_session(self, session_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT ts, event_type, source, strategy_id, symbol, session_id, payload
                FROM events WHERE session_id = ?
                ORDER BY id ASC LIMIT ?
                """,
                (str(session_id), int(limit)),
            ).fetchall()
        finally:
            conn.close()

        return [
            {
                "ts": row["ts"],
                "event_type": row["event_type"],
                "source": row["source"],
                "strategy_id": row["strategy_id"],
                "symbol": row["symbol"],
                "session_id": row["session_id"],
                "payload": json.loads(row["payload"]),
            }
            for row in rows
        ]

    def clear_all(self) -> None:
        """Fully reset the dashboard storage for a fresh session."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            tables = ["events", "signals", "orders", "portfolio_snapshots", "risk_events"]
            for table in tables:
                cur.execute(f"DELETE FROM {table}")
            conn.commit()
            # Truncate JSONL
            with self.jsonl_path.open("w", encoding="utf-8") as handle:
                handle.truncate(0)
        except Exception as e:
            print(f"Dashboard purge failed: {e}")
        finally:
            conn.close()
