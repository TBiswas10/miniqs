"""Execution module for paper trading.

Input:
- trade dict from strategy/risk pipeline: {action, size, price, timestamp?}

Output:
- execution result dict from portfolio
"""

from __future__ import annotations

from typing import Any, Dict

from execution_simulator import ExecutionSimulationConfig, ExecutionSimulator
from portfolio import Portfolio


class ExecutionEngine:
	"""Routes approved trades to a paper portfolio."""

	def __init__(
		self,
		portfolio: Portfolio,
		paper_mode: bool = True,
		debug: bool = True,
		realistic_simulation: bool = False,
		simulation_config: ExecutionSimulationConfig | None = None,
		simulation_seed: int = 42,
	) -> None:
		self.portfolio = portfolio
		self.paper_mode = paper_mode
		self.debug = debug
		self.realistic_simulation = realistic_simulation
		self.simulator = ExecutionSimulator(config=simulation_config, seed=simulation_seed)

	def execute_trade(self, trade: Dict[str, Any]) -> Dict[str, Any]:
		"""Execute a trade in paper mode.

		Input:
		- trade dict with action/size/price/timestamp

		Output:
		- result dict from Portfolio.execute_trade
		"""
		if not self.paper_mode:
			raise PermissionError("Live execution disabled in this mini system")

		execution_report: Dict[str, Any] | None = None
		trade_to_apply = dict(trade)
		action = str(trade.get("action", "")).lower()

		if self.realistic_simulation:
			execution_report = self.simulator.simulate(trade)
			filled_size = float(execution_report.get("filled_size", 0.0))
			if filled_size <= 0:
				return {
					"status": str(execution_report.get("final_state", "rejected")),
					"action": action,
					"size": 0.0,
					"price": float(trade.get("price", 0.0)),
					"fee": 0.0,
					"realized_pnl_trade": 0.0,
					"order_state": str(execution_report.get("final_state", "rejected")),
					"order_state_path": [str(p.get("state")) for p in execution_report.get("path", [])],
					"filled_size": filled_size,
					"remaining_size": float(execution_report.get("remaining_size", 0.0)),
				}

			trade_to_apply["size"] = filled_size
			trade_to_apply["price"] = float(execution_report.get("avg_fill_price", trade.get("price", 0.0)))

		result = self.portfolio.execute_trade(trade_to_apply)
		if execution_report is not None:
			result["order_state"] = str(execution_report.get("final_state", "filled"))
			result["order_state_path"] = [str(p.get("state")) for p in execution_report.get("path", [])]
			result["filled_size"] = float(execution_report.get("filled_size", result.get("size", 0.0)))
			result["remaining_size"] = float(execution_report.get("remaining_size", 0.0))
			result["execution_fills"] = execution_report.get("fills", [])
			result["requested_size"] = float(trade.get("size", result.get("size", 0.0)))
			result["applied_price"] = float(trade_to_apply.get("price", result.get("price", 0.0)))

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
