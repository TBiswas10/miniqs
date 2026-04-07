"""Trading strategies package.

Shared input/output contract:
- Input: ``FeatureSnapshot`` from ``feature_engine``
- Output: ``StrategySignal`` with action and confidence
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class StrategySignal:
	"""Output signal from a strategy.

	Fields:
	- strategy: strategy name
	- action: buy/sell/hold
	- confidence: normalized score in [0.0, 1.0]
	- reason: short explanation for logs/debugging
	"""

	strategy: str
	action: str
	confidence: float
	reason: str


__all__ = ["StrategySignal"]
