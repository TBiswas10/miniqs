"""Execution module for paper trading.

Input:
- trade dict from strategy/risk pipeline: {action, size, price, timestamp?}

Output:
- execution result dict from portfolio
"""

from __future__ import annotations

from typing import Any, Dict

from portfolio import Portfolio


class ExecutionEngine:
	"""Routes approved trades to a paper portfolio."""

	def __init__(self, portfolio: Portfolio, paper_mode: bool = True, debug: bool = True) -> None:
		self.portfolio = portfolio
		self.paper_mode = paper_mode
		self.debug = debug

	def execute_trade(self, trade: Dict[str, Any]) -> Dict[str, Any]:
		"""Execute a trade in paper mode.

		Input:
		- trade dict with action/size/price/timestamp

		Output:
		- result dict from Portfolio.execute_trade
		"""
		if not self.paper_mode:
			raise PermissionError("Live execution disabled in this mini system")

		result = self.portfolio.execute_trade(trade)
		if self.debug:
			print(
				f"[execution] action={result['action']} size={result['size']}"
				f" price={result['price']} fee={result['fee']}"
			)
		return result


def execute_trade(trade: Dict[str, Any], portfolio: Portfolio) -> Dict[str, Any]:
	"""Convenience function matching requested API shape.

	Input:
	- trade dict
	- portfolio instance

	Output:
	- execution result dict
	"""
	engine = ExecutionEngine(portfolio=portfolio, paper_mode=True, debug=True)
	return engine.execute_trade(trade)
