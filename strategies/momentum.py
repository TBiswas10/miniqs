"""Trend-following momentum strategy.

Input:
- FeatureSnapshot

Output:
- StrategySignal(action, confidence, reason)
"""

from __future__ import annotations

from dataclasses import dataclass

from feature_engine import FeatureSnapshot
from strategies import StrategySignal


def generate_signal(
    features: FeatureSnapshot,
    momentum_threshold: float = 0.002,
    trend_threshold: float = 0.001,
) -> StrategySignal:
    """Generate trend-following signal.

    Logic:
    - Require directional momentum.
    - Require price location relative to mean to confirm trend direction.
    - Hold when momentum and trend context disagree.
    """
    if features.rolling_mean <= 0:
        return StrategySignal(
            strategy="momentum",
            action="hold",
            confidence=0.0,
            reason="invalid rolling mean",
        )

    mom = features.momentum
    trend = (features.price - features.rolling_mean) / features.rolling_mean

    mom_strength = abs(mom) / max(momentum_threshold, 1e-9)
    trend_strength = abs(trend) / max(trend_threshold, 1e-9)
    strength = min(1.0, 0.7 * mom_strength + 0.3 * trend_strength)

    if mom >= momentum_threshold and trend >= -trend_threshold:
        return StrategySignal(
            strategy="momentum",
            action="buy",
            confidence=round(strength, 4),
            reason=f"uptrend confirmed momentum={mom:.4%} trend={trend:.4%}",
        )

    if mom <= -momentum_threshold and trend <= trend_threshold:
        return StrategySignal(
            strategy="momentum",
            action="sell",
            confidence=round(strength, 4),
            reason=f"downtrend confirmed momentum={mom:.4%} trend={trend:.4%}",
        )

    return StrategySignal(
        strategy="momentum",
        action="hold",
        confidence=round(max(0.0, 1.0 - min(1.0, mom_strength)), 4),
        reason="trend and momentum not aligned",
    )


@dataclass(frozen=True)
class MomentumStrategy:
    name: str = "momentum"

    def generate_signal(self, features: FeatureSnapshot, **params: float) -> StrategySignal:
        return generate_signal(
            features,
            momentum_threshold=float(params.get("momentum_threshold", 0.002)),
            trend_threshold=float(params.get("trend_threshold", 0.001)),
        )
