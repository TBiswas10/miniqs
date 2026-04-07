"""Trading strategies package.

Shared input/output contract:
- Input: ``FeatureSnapshot`` from ``feature_engine``
- Output: ``StrategySignal`` with action and confidence
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Dict, Iterable, Mapping, MutableMapping, Protocol

if TYPE_CHECKING:
	from feature_engine import FeatureSnapshot


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


class Strategy(Protocol):
	"""Common strategy contract for hot-swappable strategy modules."""

	name: str

	def generate_signal(self, features: "FeatureSnapshot", **params: float) -> StrategySignal:
		...


@dataclass(frozen=True)
class FunctionStrategy:
	"""Adapter to expose function-based strategies via the common interface."""

	name: str
	generator: Callable[["FeatureSnapshot"], StrategySignal]

	def generate_signal(self, features: "FeatureSnapshot", **params: float) -> StrategySignal:
		# The wrapped generator may accept optional keyword params.
		return self.generator(features, **params)


class StrategyRegistry:
	"""Runtime registry to enable hot-swapping strategy implementations."""

	def __init__(self) -> None:
		self._strategies: MutableMapping[str, Strategy] = {}

	def register(self, strategy: Strategy) -> None:
		self._strategies[str(strategy.name).strip().lower()] = strategy

	def get(self, name: str) -> Strategy:
		key = str(name).strip().lower()
		if key not in self._strategies:
			raise KeyError(f"strategy not registered: {name}")
		return self._strategies[key]

	def list_names(self) -> Iterable[str]:
		return tuple(self._strategies.keys())

	def swap(self, name: str, replacement: Strategy) -> None:
		key = str(name).strip().lower()
		if key != str(replacement.name).strip().lower():
			raise ValueError("replacement strategy name must match target key")
		self._strategies[key] = replacement


def default_strategy_registry() -> StrategyRegistry:
	"""Build default registry from built-in strategies."""
	from strategies.mean_reversion import MeanReversionStrategy
	from strategies.momentum import MomentumStrategy
	from strategies.volatility_breakout import VolatilityBreakoutStrategy

	registry = StrategyRegistry()
	registry.register(MeanReversionStrategy())
	registry.register(MomentumStrategy())
	registry.register(VolatilityBreakoutStrategy())
	return registry


def generate_weighted_signals(
	*,
	features: "FeatureSnapshot",
	registry: StrategyRegistry,
	weights: Mapping[str, float],
	enabled: Mapping[str, bool],
	params: Mapping[str, Mapping[str, float]],
) -> Dict[str, StrategySignal]:
	"""Run enabled strategies through a common interface and apply iteration weights."""
	out: Dict[str, StrategySignal] = {}
	for name in registry.list_names():
		strategy = registry.get(name)
		raw = strategy.generate_signal(features, **dict(params.get(name, {})))
		if not bool(enabled.get(name, True)):
			out[name] = raw.__class__(strategy=raw.strategy, action="hold", confidence=0.0, reason="strategy_disabled")
			continue
		out[name] = raw.__class__(
			strategy=raw.strategy,
			action=raw.action,
			confidence=min(1.0, raw.confidence * float(weights.get(name, 0.0))),
			reason=raw.reason,
		)
	return out


__all__ = [
	"StrategySignal",
	"Strategy",
	"FunctionStrategy",
	"StrategyRegistry",
	"default_strategy_registry",
	"generate_weighted_signals",
]
