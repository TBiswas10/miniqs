"""Portfolio module for paper trading.

Input:
- trade dict: {action, size, price, timestamp?}
- market price updates for mark-to-market PnL

Output:
- portfolio state dict with position, PnL, fees, and balances
"""

from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
from typing import Any, Dict, Optional


class Portfolio:
	"""Track paper positions, PnL, fees, and persisted trade history."""

	def __init__(
		self,
		db_path: str = "portfolio.db",
		initial_cash: float = 100000.0,
		fee_rate: float = 0.001,
	) -> None:
		self.db_path = db_path
		self.initial_cash = float(initial_cash)
		self.fee_rate = float(fee_rate)

		self.cash = float(initial_cash)
		self.position_size = 0.0
		self.avg_entry_price = 0.0
		self.realized_pnl = 0.0
		self.unrealized_pnl = 0.0
		self.total_fees = 0.0
		self.last_price: Optional[float] = None

		self._init_db()

	def _connect(self) -> sqlite3.Connection:
		return sqlite3.connect(self.db_path)

	def _init_db(self) -> None:
		conn = self._connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"""
				CREATE TABLE IF NOT EXISTS trades (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					ts TEXT NOT NULL,
					action TEXT NOT NULL,
					size REAL NOT NULL,
					price REAL NOT NULL,
					fee REAL NOT NULL,
					realized_pnl REAL NOT NULL
				)
				"""
			)
			conn.commit()
		finally:
			conn.close()

	def execute_trade(self, trade: Dict[str, Any]) -> Dict[str, Any]:
		"""Apply a paper trade and persist it.

		Input:
		- trade: {"action": buy/sell, "size": float, "price": float, "timestamp": optional}

		Output:
		- result dict with status and updated state summary
		"""
		action = str(trade.get("action", "")).lower()
		size = float(trade.get("size", 0.0))
		price = float(trade.get("price", 0.0))
		ts = trade.get("timestamp") or datetime.now(timezone.utc).isoformat()

		if action not in {"buy", "sell"}:
			raise ValueError("trade action must be 'buy' or 'sell'")
		if size <= 0:
			raise ValueError("trade size must be positive")
		if price <= 0:
			raise ValueError("trade price must be positive")

		notional = size * price
		fee = notional * self.fee_rate
		realized_for_trade = 0.0

		if action == "buy":
			new_position = self.position_size + size
			if new_position <= 0:
				raise ValueError("invalid resulting position")
			weighted_cost = (self.avg_entry_price * self.position_size) + (price * size)
			self.avg_entry_price = weighted_cost / new_position
			self.position_size = new_position
			self.cash -= notional + fee
		else:
			if size > self.position_size:
				raise ValueError("cannot sell more than current position in this skeleton")
			realized_for_trade = (price - self.avg_entry_price) * size
			self.realized_pnl += realized_for_trade
			self.position_size -= size
			self.cash += notional - fee
			if self.position_size == 0:
				self.avg_entry_price = 0.0

		self.total_fees += fee
		self.last_price = price
		self.update_pnl(price)
		self._persist_trade(ts, action, size, price, fee, realized_for_trade)

		return {
			"status": "executed",
			"action": action,
			"size": size,
			"price": price,
			"fee": round(fee, 8),
			"realized_pnl_trade": round(realized_for_trade, 8),
		}

	def _persist_trade(
		self,
		ts: str,
		action: str,
		size: float,
		price: float,
		fee: float,
		realized_pnl: float,
	) -> None:
		conn = self._connect()
		try:
			cur = conn.cursor()
			cur.execute(
				"""
				INSERT INTO trades (ts, action, size, price, fee, realized_pnl)
				VALUES (?, ?, ?, ?, ?, ?)
				""",
				(ts, action, size, price, fee, realized_pnl),
			)
			conn.commit()
		finally:
			conn.close()

	def update_pnl(self, market_price: Optional[float] = None) -> Dict[str, float]:
		"""Mark-to-market unrealized and total PnL.

		Input:
		- market_price: optional latest price

		Output:
		- dict with realized/unrealized/total_pnl/equity
		"""
		if market_price is not None:
			self.last_price = float(market_price)

		if self.last_price is None:
			self.unrealized_pnl = 0.0
		else:
			self.unrealized_pnl = (self.last_price - self.avg_entry_price) * self.position_size

		total_pnl = self.realized_pnl + self.unrealized_pnl - self.total_fees
		equity = self.cash + (self.position_size * (self.last_price or 0.0))

		return {
			"realized_pnl": round(self.realized_pnl, 8),
			"unrealized_pnl": round(self.unrealized_pnl, 8),
			"total_pnl": round(total_pnl, 8),
			"equity": round(equity, 8),
		}

	def get_portfolio_state(self) -> Dict[str, float]:
		"""Return current portfolio state snapshot.

		Output:
		- dict with cash, position_size, avg_entry_price, realized/unrealized PnL, fees, and equity
		"""
		pnl = self.update_pnl(self.last_price)
		return {
			"cash": round(self.cash, 8),
			"position_size": round(self.position_size, 8),
			"avg_entry_price": round(self.avg_entry_price, 8),
			"fees_paid": round(self.total_fees, 8),
			**pnl,
		}
