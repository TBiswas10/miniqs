"""SQLite-backed logging utilities for the quant pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, Optional


class QuantLogger:
	"""Persist runtime artifacts for review and debugging."""

	def __init__(self, db_path: str = "logs.db", jsonl_path: Optional[str] = None, run_id: Optional[str] = None) -> None:
		self.db_path = db_path
		self.jsonl_path = jsonl_path or str(Path(db_path).with_suffix(".events.jsonl"))
		self.run_id = run_id or datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S")
		self._sequence = 0
		Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
		Path(self.jsonl_path).parent.mkdir(parents=True, exist_ok=True)
		self._init_db()

	def _connect(self) -> sqlite3.Connection:
		return sqlite3.connect(self.db_path)

	def _init_db(self) -> None:
		conn = self._connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"""
				CREATE TABLE IF NOT EXISTS event_log (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					ts TEXT NOT NULL,
					run_id TEXT NOT NULL,
					seq INTEGER NOT NULL,
					event_type TEXT NOT NULL,
					payload_json TEXT NOT NULL
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
				CREATE TABLE IF NOT EXISTS trades (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					ts TEXT NOT NULL,
					strategy TEXT NOT NULL,
					action TEXT NOT NULL,
					size REAL NOT NULL,
					price REAL NOT NULL,
					fee REAL NOT NULL,
					realized_pnl_trade REAL NOT NULL
				)
				"""
			)
			cur.execute(
				"""
				CREATE TABLE IF NOT EXISTS portfolio_snapshots (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					ts TEXT NOT NULL,
					cash REAL NOT NULL,
					position_size REAL NOT NULL,
					equity REAL NOT NULL,
					total_pnl REAL NOT NULL
				)
				"""
			)
			cur.execute(
				"""
				CREATE TABLE IF NOT EXISTS performance_metrics (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					ts TEXT NOT NULL,
					total_pnl REAL NOT NULL,
					win_rate REAL NOT NULL,
					avg_trade_pnl REAL NOT NULL,
					max_drawdown REAL NOT NULL,
					sharpe_ratio REAL NOT NULL
				)
				"""
			)
			cur.execute(
				"""
				CREATE TABLE IF NOT EXISTS ws_events (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					ts TEXT NOT NULL,
					source TEXT NOT NULL,
					message TEXT NOT NULL
				)
				"""
			)
			cur.execute(
				"""
				CREATE TABLE IF NOT EXISTS connection_events (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					ts TEXT NOT NULL,
					component TEXT NOT NULL,
					status TEXT NOT NULL,
					detail TEXT NOT NULL
				)
				"""
			)
			cur.execute(
				"""
				CREATE TABLE IF NOT EXISTS risk_blocks (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					ts TEXT NOT NULL,
					reason TEXT NOT NULL,
					detail TEXT NOT NULL
				)
				"""
			)
			cur.execute(
				"""
				CREATE TABLE IF NOT EXISTS feedback_log (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					ts TEXT NOT NULL,
					mean_reversion REAL NOT NULL,
					momentum REAL NOT NULL,
					volatility_breakout REAL NOT NULL DEFAULT 0.0,
					reason TEXT NOT NULL
				)
				"""
			)
			cur.execute("PRAGMA table_info(feedback_log)")
			feedback_columns = {str(row[1]) for row in cur.fetchall()}
			if "volatility_breakout" not in feedback_columns:
				cur.execute(
					"ALTER TABLE feedback_log ADD COLUMN volatility_breakout REAL NOT NULL DEFAULT 0.0"
				)
			conn.commit()
		finally:
			conn.close()

	def _emit_structured_event(self, event_type: str, payload: Dict[str, Any]) -> None:
		ts = datetime.now(timezone.utc).isoformat()
		self._sequence += 1
		record = {
			"ts": ts,
			"run_id": self.run_id,
			"seq": int(self._sequence),
			"event_type": str(event_type),
			"payload": payload,
		}
		encoded = json.dumps(record, default=str)

		conn = self._connect()
		try:
			conn.execute(
				"""
				INSERT INTO event_log (ts, run_id, seq, event_type, payload_json)
				VALUES (?, ?, ?, ?, ?)
				""",
				(ts, self.run_id, int(self._sequence), str(event_type), encoded),
			)
			conn.commit()
		finally:
			conn.close()

		with open(self.jsonl_path, "a", encoding="utf-8") as handle:
			handle.write(encoded + "\n")

	def log_signal(self, strategy: str, action: str, confidence: float, reason: str) -> None:
		ts = datetime.now(timezone.utc).isoformat()
		payload = {
			"strategy": str(strategy),
			"action": str(action),
			"confidence": float(confidence),
			"reason": str(reason),
		}
		conn = self._connect()
		try:
			conn.execute(
				"INSERT INTO signals (ts, strategy, action, confidence, reason) VALUES (?, ?, ?, ?, ?)",
				(ts, strategy, action, float(confidence), reason),
			)
			conn.commit()
		finally:
			conn.close()
		self._emit_structured_event("signal", payload)

	def log_trade(self, trade_result: Dict[str, float], strategy: str) -> None:
		ts = datetime.now(timezone.utc).isoformat()
		payload = {
			"strategy": str(strategy),
			"action": str(trade_result.get("action", "")),
			"size": float(trade_result.get("size", 0.0)),
			"price": float(trade_result.get("price", 0.0)),
			"fee": float(trade_result.get("fee", 0.0)),
			"realized_pnl_trade": float(trade_result.get("realized_pnl_trade", 0.0)),
			"raw": dict(trade_result),
		}
		conn = self._connect()
		try:
			conn.execute(
				"""
				INSERT INTO trades (ts, strategy, action, size, price, fee, realized_pnl_trade)
				VALUES (?, ?, ?, ?, ?, ?, ?)
				""",
				(
					ts,
					strategy,
					str(trade_result.get("action", "")),
					float(trade_result.get("size", 0.0)),
					float(trade_result.get("price", 0.0)),
					float(trade_result.get("fee", 0.0)),
					float(trade_result.get("realized_pnl_trade", 0.0)),
				),
			)
			conn.commit()
		finally:
			conn.close()
		self._emit_structured_event("trade", payload)

	def log_portfolio_snapshot(self, state: Dict[str, float]) -> None:
		ts = datetime.now(timezone.utc).isoformat()
		payload = {k: float(v) for k, v in state.items()}
		conn = self._connect()
		try:
			conn.execute(
				"""
				INSERT INTO portfolio_snapshots (ts, cash, position_size, equity, total_pnl)
				VALUES (?, ?, ?, ?, ?)
				""",
				(
					ts,
					float(state.get("cash", 0.0)),
					float(state.get("position_size", 0.0)),
					float(state.get("equity", 0.0)),
					float(state.get("total_pnl", 0.0)),
				),
			)
			conn.commit()
		finally:
			conn.close()
		self._emit_structured_event("portfolio_snapshot", payload)

	def log_performance_metrics(self, metrics: Dict[str, float]) -> None:
		ts = datetime.now(timezone.utc).isoformat()
		payload = {k: float(v) for k, v in metrics.items()}
		conn = self._connect()
		try:
			conn.execute(
				"""
				INSERT INTO performance_metrics (ts, total_pnl, win_rate, avg_trade_pnl, max_drawdown, sharpe_ratio)
				VALUES (?, ?, ?, ?, ?, ?)
				""",
				(
					ts,
					float(metrics.get("total_pnl", 0.0)),
					float(metrics.get("win_rate", 0.0)),
					float(metrics.get("avg_trade_pnl", 0.0)),
					float(metrics.get("max_drawdown", 0.0)),
					float(metrics.get("sharpe_ratio", 0.0)),
				),
			)
			conn.commit()
		finally:
			conn.close()
		self._emit_structured_event("performance_metrics", payload)

	def log_ws_event(self, source: str, message: str) -> None:
		ts = datetime.now(timezone.utc).isoformat()
		payload = {"source": str(source), "message": str(message)[:8000]}
		conn = self._connect()
		try:
			conn.execute(
				"INSERT INTO ws_events (ts, source, message) VALUES (?, ?, ?)",
				(ts, str(source), str(message)[:8000]),
			)
			conn.commit()
		finally:
			conn.close()
		self._emit_structured_event("ws_event", payload)

	def log_connection_event(self, component: str, status: str, detail: str = "") -> None:
		ts = datetime.now(timezone.utc).isoformat()
		payload = {"component": str(component), "status": str(status), "detail": str(detail)[:8000]}
		conn = self._connect()
		try:
			conn.execute(
				"INSERT INTO connection_events (ts, component, status, detail) VALUES (?, ?, ?, ?)",
				(ts, str(component), str(status), str(detail)[:8000]),
			)
			conn.commit()
		finally:
			conn.close()
		self._emit_structured_event("connection_event", payload)

	def log_risk_block(self, reason: str, detail: str = "") -> None:
		ts = datetime.now(timezone.utc).isoformat()
		payload = {"reason": str(reason), "detail": str(detail)[:8000]}
		conn = self._connect()
		try:
			conn.execute(
				"INSERT INTO risk_blocks (ts, reason, detail) VALUES (?, ?, ?)",
				(ts, str(reason), str(detail)[:8000]),
			)
			conn.commit()
		finally:
			conn.close()
		self._emit_structured_event("risk_block", payload)

	def log_feedback(self, weights: Dict[str, float], reason: str) -> None:
		ts = datetime.now(timezone.utc).isoformat()
		payload = {
			"weights": {k: float(v) for k, v in weights.items()},
			"reason": str(reason)[:8000],
		}
		conn = self._connect()
		try:
			conn.execute(
				"""
				INSERT INTO feedback_log (ts, mean_reversion, momentum, volatility_breakout, reason)
				VALUES (?, ?, ?, ?, ?)
				""",
				(
					ts,
					float(weights.get("mean_reversion", 0.0)),
					float(weights.get("momentum", 0.0)),
					float(weights.get("volatility_breakout", 0.0)),
					str(reason)[:8000],
				),
			)
			conn.commit()
		finally:
			conn.close()
		self._emit_structured_event("feedback", payload)

	def log_trade_update_event(self, event: str, payload: Optional[Dict[str, Any]] = None) -> None:
		"""Alpaca trade_updates stream (order lifecycle)."""
		import json as _json

		msg = _json.dumps(payload, default=str) if payload is not None else ""
		self.log_ws_event(f"trade_updates:{event}", msg[:8000])
