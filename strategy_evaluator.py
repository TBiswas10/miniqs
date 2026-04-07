"""Strategy evaluator module.

Input:
- signals_list: list of StrategySignal objects from strategy modules

Output:
- single chosen StrategySignal with highest confidence
- None when no actionable signal meets threshold
"""

from __future__ import annotations

from typing import List, Optional

from strategies import StrategySignal


def evaluate_signals(
	signals_list: List[StrategySignal],
	confidence_threshold: float = 0.6,
) -> Optional[StrategySignal]:
	"""Choose highest-confidence actionable signal or return None.

	Input:
	- signals_list: strategy outputs with action/confidence metadata
	- confidence_threshold: minimum required confidence in [0, 1]

	Output:
	- StrategySignal if a buy/sell signal passes threshold
	- None when list is empty, only holds exist, or confidence is too low
	"""
	if not 0.0 <= confidence_threshold <= 1.0:
		raise ValueError("confidence_threshold must be between 0.0 and 1.0")

	actionable = [s for s in signals_list if s.action in {"buy", "sell"}]
	if not actionable:
		return None

	best = max(actionable, key=lambda s: s.confidence)
	if best.confidence < confidence_threshold:
		return None

	return best
