"""Risk manager module.

Input:
- proposed trade dict: {action, size, confidence, timestamp?}
- portfolio_state dict with risk context and limits

Output:
- (allow_trade: bool, reason: str)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Tuple


def _parse_timestamp(value: Any) -> datetime:
	if isinstance(value, datetime):
		return value
	if isinstance(value, str):
		return datetime.fromisoformat(value)
	return datetime.now(timezone.utc)


@dataclass
class RiskConfig:
	base_trade_size: float = 0.0025
	risk_per_trade: float = 0.003
	daily_loss_limit: float = 300.0
	confidence_threshold: float = 0.42
	max_exposure: float = 0.75
	max_concurrent_positions: int = 1
	max_position_size: float = 0.03
	cooldown_seconds: int = 12
	max_loss_per_session: float = 300.0
	portfolio_drawdown_limit: float = 0.12
	per_strategy_drawdown_limit: float = 0.08
	extreme_loss_kill_switch: float = 900.0
	strategy_kill_loss: float = 200.0
	vol_target: float = 0.02
	vol_floor: float = 0.004
	vol_ceiling: float = 0.08
	low_vol_multiplier: float = 1.15
	high_vol_multiplier: float = 0.55
	min_trade_size: float = 0.0005
	max_trade_size: float = 0.03


@dataclass
class RiskEngine:
	"""Stateful risk engine for dynamic sizing and kill-switch controls."""

	initial_equity: float
	config: RiskConfig = field(default_factory=RiskConfig)
	global_kill_switch: bool = False
	strategy_kill_switch: Dict[str, bool] = field(default_factory=dict)
	peak_equity: float = 0.0
	strategy_peak_pnl: Dict[str, float] = field(default_factory=dict)
	strategy_live_pnl: Dict[str, float] = field(default_factory=dict)

	def __post_init__(self) -> None:
		if self.initial_equity <= 0:
			raise ValueError("initial_equity must be positive")
		if self.peak_equity <= 0:
			self.peak_equity = float(self.initial_equity)

	def assess_trade(
		self,
		trade: Dict[str, Any],
		portfolio_state: Dict[str, Any],
	) -> Tuple[bool, str, Dict[str, Any], Dict[str, Any]]:
		"""Evaluate and adapt trade risk with dynamic sizing and kill-switches."""
		action = str(trade.get("action", "hold")).lower()
		strategy = str(trade.get("strategy", "unknown"))
		adjusted_trade = dict(trade)
		gate_state = dict(portfolio_state)
		gate_state.setdefault("risk_per_trade", self.config.risk_per_trade)
		gate_state.setdefault("daily_loss_limit", self.config.daily_loss_limit)
		gate_state.setdefault("confidence_threshold", self.config.confidence_threshold)
		gate_state.setdefault("max_exposure", self.config.max_exposure)
		gate_state.setdefault("max_concurrent_positions", self.config.max_concurrent_positions)
		gate_state.setdefault("max_position_size", self.config.max_position_size)
		gate_state.setdefault("cooldown_seconds", self.config.cooldown_seconds)
		gate_state.setdefault("max_loss_per_session", self.config.max_loss_per_session)

		flags = {
			"global_kill_switch": self.global_kill_switch,
			"strategy_kill_switch": bool(self.strategy_kill_switch.get(strategy, False)),
		}

		if self.global_kill_switch:
			return False, "blocked: global kill switch engaged", adjusted_trade, flags
		if self.strategy_kill_switch.get(strategy, False):
			return False, f"blocked: strategy_kill_switch {strategy}", adjusted_trade, flags

		current_equity = float(gate_state.get("equity", self.initial_equity))
		self.peak_equity = max(self.peak_equity, current_equity)
		portfolio_dd = (self.peak_equity - current_equity) / max(self.peak_equity, 1e-9)
		gate_state.setdefault("portfolio_drawdown", portfolio_dd)
		gate_state.setdefault("portfolio_drawdown_limit", self.config.portfolio_drawdown_limit)
		if portfolio_dd >= self.config.portfolio_drawdown_limit:
			self.global_kill_switch = True
			flags["global_kill_switch"] = True
			return False, "blocked: portfolio drawdown kill switch", adjusted_trade, flags

		total_pnl = float(gate_state.get("total_pnl", 0.0))
		if total_pnl <= -abs(self.config.extreme_loss_kill_switch):
			self.global_kill_switch = True
			flags["global_kill_switch"] = True
			return False, "blocked: extreme loss kill switch", adjusted_trade, flags

		session_loss = float(gate_state.get("session_loss", max(0.0, -total_pnl)))
		daily_limit = float(gate_state.get("daily_loss_limit", self.config.daily_loss_limit))
		if daily_limit > 0 and session_loss >= daily_limit:
			self.global_kill_switch = True
			flags["global_kill_switch"] = True
			return False, "blocked: daily loss kill switch", adjusted_trade, flags

		market_vol = float(gate_state.get("market_volatility", self.config.vol_target))
		confidence = float(trade.get("confidence", 0.5))
		strategy_weight = float(gate_state.get("strategy_weight", 1.0))
		adjusted_size = self._volatility_scaled_size(
			confidence=confidence,
			market_volatility=market_vol,
			strategy_weight=strategy_weight,
		)
		adjusted_size = self._size_capped_by_risk_budget(
			raw_size=adjusted_size,
			price=float(adjusted_trade.get("price", 0.0)),
			equity=current_equity,
			risk_per_trade=float(gate_state.get("risk_per_trade", self.config.risk_per_trade)),
		)
		adjusted_trade["size"] = adjusted_size

		allow, reason = _basic_rule_checks(adjusted_trade, gate_state)
		if not allow:
			return False, reason, adjusted_trade, flags

		return True, "allowed", adjusted_trade, flags

	def _volatility_scaled_size(
		self,
		*,
		confidence: float,
		market_volatility: float,
		strategy_weight: float,
	) -> float:
		vol = min(max(market_volatility, self.config.vol_floor), self.config.vol_ceiling)
		inv_vol_scale = self.config.vol_target / max(vol, 1e-9)
		if vol <= self.config.vol_target:
			regime_mult = self.config.low_vol_multiplier
		else:
			regime_mult = self.config.high_vol_multiplier

		conf_scale = max(0.4, min(1.4, confidence))
		raw_size = (
			self.config.base_trade_size
			* inv_vol_scale
			* regime_mult
			* max(0.0, strategy_weight)
			* conf_scale
		)
		return max(self.config.min_trade_size, min(self.config.max_trade_size, raw_size))

	def _size_capped_by_risk_budget(
		self,
		*,
		raw_size: float,
		price: float,
		equity: float,
		risk_per_trade: float,
	) -> float:
		if price <= 0 or equity <= 0 or risk_per_trade <= 0:
			return raw_size
		risk_notional = equity * risk_per_trade
		max_size_by_risk = risk_notional / price
		if max_size_by_risk <= 0:
			return 0.0
		return min(raw_size, max_size_by_risk)

	def record_execution(self, strategy: str, realized_pnl_trade: float, equity: float) -> None:
		self.peak_equity = max(self.peak_equity, float(equity))
		self.strategy_live_pnl[strategy] = self.strategy_live_pnl.get(strategy, 0.0) + float(realized_pnl_trade)
		self.strategy_peak_pnl[strategy] = max(
			self.strategy_peak_pnl.get(strategy, 0.0),
			self.strategy_live_pnl[strategy],
		)

		peak = self.strategy_peak_pnl[strategy]
		live = self.strategy_live_pnl[strategy]
		strategy_dd = (peak - live) / max(abs(peak), self.initial_equity)
		if strategy_dd >= self.config.per_strategy_drawdown_limit:
			self.strategy_kill_switch[strategy] = True

		if live <= -abs(self.config.strategy_kill_loss):
			self.strategy_kill_switch[strategy] = True


def _basic_rule_checks(trade: Dict[str, Any], portfolio_state: Dict[str, Any]) -> Tuple[bool, str]:
	action = str(trade.get("action", "hold")).lower()
	size = float(trade.get("size", 0.0))
	price = float(trade.get("price", 0.0))
	confidence = float(trade.get("confidence", 0.0))
	now = _parse_timestamp(trade.get("timestamp"))

	if action not in {"buy", "sell", "hold"}:
		return False, "blocked: invalid action"

	if action == "hold" or size <= 0:
		return False, "blocked: non-actionable trade"

	current_position = float(portfolio_state.get("current_position", 0.0))
	max_position_size = float(portfolio_state.get("max_position_size", 0.0))
	open_positions_count = int(portfolio_state.get("open_positions_count", 1 if abs(current_position) > 1e-12 else 0))
	max_concurrent_positions = int(portfolio_state.get("max_concurrent_positions", 0))
	equity = float(portfolio_state.get("equity", 0.0))
	risk_per_trade = float(portfolio_state.get("risk_per_trade", 0.0))
	confidence_threshold = float(portfolio_state.get("confidence_threshold", 0.0))
	max_exposure = float(portfolio_state.get("max_exposure", 0.0))
	portfolio_drawdown = float(portfolio_state.get("portfolio_drawdown", portfolio_state.get("current_drawdown", 0.0)))
	portfolio_drawdown_limit = float(portfolio_state.get("portfolio_drawdown_limit", 0.0))
	cooldown_seconds = int(portfolio_state.get("cooldown_seconds", 0))
	max_loss_per_session = float(
		portfolio_state.get(
			"daily_loss_limit",
			portfolio_state.get("max_loss_per_session", 0.0),
		)
	)
	session_loss = float(portfolio_state.get("session_loss", 0.0))

	if confidence_threshold > 0 and confidence < confidence_threshold:
		return False, "blocked: confidence threshold not met"

	if max_loss_per_session > 0 and session_loss >= max_loss_per_session:
		return False, "blocked: daily loss kill switch"

	if portfolio_drawdown_limit > 0 and portfolio_drawdown >= portfolio_drawdown_limit:
		return False, "blocked: portfolio drawdown limit reached"

	last_trade_ts = portfolio_state.get("last_trade_timestamp")
	if last_trade_ts:
		last_ts = _parse_timestamp(last_trade_ts)
		if now - last_ts < timedelta(seconds=cooldown_seconds):
			return False, "blocked: cooldown active"

	if action == "sell" and size > current_position + 1e-12:
		return False, "blocked: cannot sell more than position"

	if action == "buy" and current_position <= 1e-12 and max_concurrent_positions > 0:
		if open_positions_count >= max_concurrent_positions:
			return False, "blocked: max concurrent positions reached"

	proposed_position = current_position + size if action == "buy" else current_position - size
	if abs(proposed_position) > max_position_size:
		return False, "blocked: max position size exceeded"

	if risk_per_trade > 0 and equity > 0 and price > 0:
		risk_notional = equity * risk_per_trade
		if size * price > risk_notional + 1e-12:
			return False, "blocked: risk per trade exceeded"

	if max_exposure > 0 and equity > 0 and price > 0:
		proposed_exposure = abs(proposed_position) * price
		if proposed_exposure > (equity * max_exposure) + 1e-12:
			return False, "blocked: max exposure exceeded"

	return True, "allowed"


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
	return _basic_rule_checks(trade, portfolio_state)

