"""Performance analytics for paper trading and backtesting."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Deque, Dict, List


@dataclass
class PerformanceTracker:
	"""Collect and compute portfolio/trade metrics."""

	initial_equity: float = 100000.0
	trade_pnls: List[float] = field(default_factory=list)
	equity_curve: List[float] = field(default_factory=list)
	strategy_trade_pnls: Dict[str, Deque[float]] = field(
		default_factory=lambda: defaultdict(lambda: deque(maxlen=50))
	)

	def record_trade(self, realized_pnl_trade: float) -> None:
		self.trade_pnls.append(float(realized_pnl_trade))

	def record_strategy_trade(self, strategy: str, realized_pnl_trade: float) -> None:
		self.strategy_trade_pnls[strategy].append(float(realized_pnl_trade))

	def record_equity(self, equity: float) -> None:
		self.equity_curve.append(float(equity))

	def compute_metrics(self, latest_total_pnl: float) -> Dict[str, float]:
		wins = sum(1 for p in self.trade_pnls if p > 0)
		trade_count = len(self.trade_pnls)
		win_rate = (wins / trade_count) if trade_count else 0.0
		avg_trade_pnl = mean(self.trade_pnls) if trade_count else 0.0

		max_drawdown = self._max_drawdown()
		sharpe_ratio = self._sharpe_ratio()

		return {
			"total_pnl": float(latest_total_pnl),
			"win_rate": float(win_rate),
			"avg_trade_pnl": float(avg_trade_pnl),
			"max_drawdown": float(max_drawdown),
			"sharpe_ratio": float(sharpe_ratio),
			"trade_count": float(trade_count),
		}

	def strategy_metrics_for_feedback(self) -> Dict[str, Dict[str, float]]:
		metrics: Dict[str, Dict[str, float]] = {}
		for strategy, pnls in self.strategy_trade_pnls.items():
			values = list(pnls)
			if not values:
				continue
			wins = sum(1 for p in values if p > 0)
			hit_rate = wins / len(values)
			avg_trade_pnl = mean(values)
			max_dd = self._max_drawdown_from_returns(values)
			std = pstdev(values) if len(values) > 1 else 0.0
			sharpe = (avg_trade_pnl / std) if std > 0 else 0.0
			metrics[strategy] = {
				"win_rate": float(hit_rate),
				"hit_rate": float(hit_rate),
				"avg_trade_pnl": float(avg_trade_pnl),
				"max_drawdown": float(max_dd),
				"sharpe_ratio": float(sharpe),
				"trade_count": float(len(values)),
			}
		return metrics

	def _max_drawdown(self) -> float:
		if not self.equity_curve:
			return 0.0
		peak = self.equity_curve[0]
		max_dd = 0.0
		for v in self.equity_curve:
			peak = max(peak, v)
			if peak > 0:
				max_dd = max(max_dd, (peak - v) / peak)
		return max_dd

	def _sharpe_ratio(self) -> float:
		if len(self.equity_curve) < 2:
			return 0.0
		returns: List[float] = []
		for i in range(1, len(self.equity_curve)):
			prev = self.equity_curve[i - 1]
			curr = self.equity_curve[i]
			if prev > 0:
				returns.append((curr / prev) - 1.0)
		if not returns:
			return 0.0
		sigma = pstdev(returns)
		if sigma == 0:
			return 0.0
		return mean(returns) / sigma

	def _max_drawdown_from_returns(self, returns: List[float]) -> float:
		equity = 1.0
		peak = 1.0
		max_dd = 0.0
		for r in returns:
			equity += r / max(1.0, abs(self.initial_equity))
			peak = max(peak, equity)
			if peak > 0:
				max_dd = max(max_dd, (peak - equity) / peak)
		return max_dd
