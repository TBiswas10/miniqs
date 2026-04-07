"""Risk manager module.

Input:
- proposed trade dict: {action, size, confidence, timestamp?}
- portfolio_state dict with risk context and limits

Output:
- (allow_trade: bool, reason: str)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Tuple


def _parse_timestamp(value: Any) -> datetime:
	if isinstance(value, datetime):
		return value
	if isinstance(value, str):
		return datetime.fromisoformat(value)
	return datetime.now(timezone.utc)


def check_risk(trade: Dict[str, Any], portfolio_state: Dict[str, Any]) -> Tuple[bool, str]:
	"""Validate a proposed trade against core risk constraints.

	Input:
	- trade: {
		"action": "buy" | "sell" | "hold",
		"size": float,
		"confidence": float,
		"timestamp": datetime | iso-string (optional)
	  }
	- portfolio_state: {
		"current_position": float,
		"last_trade_timestamp": datetime | iso-string | None,
		"session_loss": float,
		"max_position_size": float,
		"cooldown_seconds": int,
		"max_loss_per_session": float
	  }

	Output:
	- (True, "allowed") if trade is allowed
	- (False, "...") with block reason if rule is violated
	"""
	action = str(trade.get("action", "hold")).lower()
	size = float(trade.get("size", 0.0))
	now = _parse_timestamp(trade.get("timestamp"))

	if action not in {"buy", "sell", "hold"}:
		return False, "blocked: invalid action"

	if action == "hold" or size <= 0:
		return False, "blocked: non-actionable trade"

	current_position = float(portfolio_state.get("current_position", 0.0))
	max_position_size = float(portfolio_state.get("max_position_size", 0.0))
	cooldown_seconds = int(portfolio_state.get("cooldown_seconds", 0))
	max_loss_per_session = float(portfolio_state.get("max_loss_per_session", 0.0))
	session_loss = float(portfolio_state.get("session_loss", 0.0))

	if max_loss_per_session > 0 and session_loss >= max_loss_per_session:
		return False, "blocked: max session loss reached"

	last_trade_ts = portfolio_state.get("last_trade_timestamp")
	if last_trade_ts:
		last_ts = _parse_timestamp(last_trade_ts)
		if now - last_ts < timedelta(seconds=cooldown_seconds):
			return False, "blocked: cooldown active"

	if action == "sell" and size > current_position + 1e-12:
		return False, "blocked: cannot sell more than position"

	proposed_position = current_position + size if action == "buy" else current_position - size
	if abs(proposed_position) > max_position_size:
		return False, "blocked: max position size exceeded"

	return True, "allowed"
