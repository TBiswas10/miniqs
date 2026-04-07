"""Versioned, replayable research dataset store.

Persists ticks/OHLC/features/signals/fills/PnL/strategy metrics into versioned SQLite datasets.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, Iterator, Optional


class ResearchDatasetStore:
    def __init__(self, dataset_name: str, root_dir: str = "research_data") -> None:
        self.dataset_name = dataset_name
        self.root_dir = Path(root_dir)
        self.dataset_dir = self.root_dir / dataset_name
        self.dataset_dir.mkdir(parents=True, exist_ok=True)
        self.version_id: Optional[str] = None
        self.db_path: Optional[Path] = None

    def create_version(self, metadata: Dict[str, Any]) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        h = hashlib.sha1(json.dumps(metadata, sort_keys=True).encode("utf-8")).hexdigest()[:8]
        self.version_id = f"{ts}_{h}"
        self.db_path = self.dataset_dir / f"{self.version_id}.db"
        self._init_db(self.db_path)
        self._write_manifest(metadata)
        return self.version_id

    def _connect(self) -> sqlite3.Connection:
        if self.db_path is None:
            raise RuntimeError("dataset version not initialized")
        return sqlite3.connect(str(self.db_path))

    def _init_db(self, db_path: Path) -> None:
        conn = sqlite3.connect(str(db_path))
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ticks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    price REAL NOT NULL,
                    volume REAL NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ohlc (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS features (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    price REAL NOT NULL,
                    rolling_mean REAL NOT NULL,
                    rolling_volatility REAL NOT NULL,
                    momentum REAL NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    action TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    reason TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS fills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    action TEXT NOT NULL,
                    requested_size REAL NOT NULL,
                    filled_size REAL NOT NULL,
                    remaining_size REAL NOT NULL,
                    fill_price REAL NOT NULL,
                    fee REAL NOT NULL,
                    order_state TEXT NOT NULL,
                    order_state_path TEXT NOT NULL,
                    raw_payload TEXT NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS pnl_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    equity REAL NOT NULL,
                    total_pnl REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    unrealized_pnl REAL NOT NULL
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS strategy_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    hit_rate REAL NOT NULL,
                    sharpe_ratio REAL NOT NULL,
                    max_drawdown REAL NOT NULL,
                    avg_trade_pnl REAL NOT NULL,
                    trade_count REAL NOT NULL,
                    raw_payload TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _write_manifest(self, metadata: Dict[str, Any]) -> None:
        if self.version_id is None:
            raise RuntimeError("dataset version not initialized")
        manifest = {
            "dataset_name": self.dataset_name,
            "version_id": self.version_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata,
        }
        manifest_path = self.dataset_dir / f"{self.version_id}.manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def log_tick(self, ts: str, symbol: str, price: float, volume: float) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO ticks(ts, symbol, price, volume) VALUES (?, ?, ?, ?)",
                (ts, symbol, float(price), float(volume)),
            )
            conn.commit()
        finally:
            conn.close()

    def log_ohlc(self, ts: str, symbol: str, o: float, h: float, l: float, c: float, volume: float) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO ohlc(ts, symbol, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ts, symbol, float(o), float(h), float(l), float(c), float(volume)),
            )
            conn.commit()
        finally:
            conn.close()

    def log_feature(
        self,
        ts: str,
        symbol: str,
        price: float,
        rolling_mean: float,
        rolling_volatility: float,
        momentum: float,
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO features(ts, symbol, price, rolling_mean, rolling_volatility, momentum)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ts, symbol, float(price), float(rolling_mean), float(rolling_volatility), float(momentum)),
            )
            conn.commit()
        finally:
            conn.close()

    def log_signal(self, ts: str, strategy: str, action: str, confidence: float, reason: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO signals(ts, strategy, action, confidence, reason) VALUES (?, ?, ?, ?, ?)",
                (ts, strategy, action, float(confidence), reason),
            )
            conn.commit()
        finally:
            conn.close()

    def log_fill(self, ts: str, strategy: str, result: Dict[str, Any]) -> None:
        path = result.get("order_state_path", [])
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO fills(
                    ts, strategy, action, requested_size, filled_size, remaining_size,
                    fill_price, fee, order_state, order_state_path, raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    strategy,
                    str(result.get("action", "")),
                    float(result.get("requested_size", result.get("size", 0.0))),
                    float(result.get("filled_size", result.get("size", 0.0))),
                    float(result.get("remaining_size", 0.0)),
                    float(result.get("applied_price", result.get("price", 0.0))),
                    float(result.get("fee", 0.0)),
                    str(result.get("order_state", "filled")),
                    json.dumps(path),
                    json.dumps(result, default=str),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def log_pnl(self, ts: str, equity: float, total_pnl: float, realized_pnl: float, unrealized_pnl: float) -> None:
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO pnl_snapshots(ts, equity, total_pnl, realized_pnl, unrealized_pnl) VALUES (?, ?, ?, ?, ?)",
                (ts, float(equity), float(total_pnl), float(realized_pnl), float(unrealized_pnl)),
            )
            conn.commit()
        finally:
            conn.close()

    def log_strategy_metric(self, ts: str, strategy: str, metrics: Dict[str, Any]) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO strategy_metrics(
                    ts, strategy, hit_rate, sharpe_ratio, max_drawdown, avg_trade_pnl, trade_count, raw_payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ts,
                    strategy,
                    float(metrics.get("hit_rate", metrics.get("win_rate", 0.0))),
                    float(metrics.get("sharpe_ratio", 0.0)),
                    float(metrics.get("max_drawdown", 0.0)),
                    float(metrics.get("avg_trade_pnl", 0.0)),
                    float(metrics.get("trade_count", 0.0)),
                    json.dumps(metrics, default=str),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def replay_ticks(self) -> Iterator[Dict[str, Any]]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            for ts, symbol, price, volume in cur.execute(
                "SELECT ts, symbol, price, volume FROM ticks ORDER BY ts ASC, id ASC"
            ):
                yield {
                    "timestamp": ts,
                    "symbol": symbol,
                    "price": float(price),
                    "volume": float(volume),
                }
        finally:
            conn.close()
