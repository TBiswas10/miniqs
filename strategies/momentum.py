"""Momentum strategy.

Input:
- FeatureSnapshot

Output:
- StrategySignal(action, confidence, reason)
"""

from __future__ import annotations

from feature_engine import FeatureSnapshot
from strategies import StrategySignal


def generate_signal(features: FeatureSnapshot, momentum_threshold: float = 0.002) -> StrategySignal:
    """Generate momentum signal.

    Logic:
    - Positive momentum above threshold -> buy.
    - Negative momentum below -threshold -> sell.
    - Otherwise hold.
    """
    mom = features.momentum
    strength = min(1.0, abs(mom) / max(momentum_threshold, 1e-9))

    if mom >= momentum_threshold:
        return StrategySignal(
            strategy="momentum",
            action="buy",
            confidence=round(strength, 4),
            reason=f"positive momentum {mom:.4%}",
        )

    if mom <= -momentum_threshold:
        return StrategySignal(
            strategy="momentum",
            action="sell",
            confidence=round(strength, 4),
            reason=f"negative momentum {mom:.4%}",
        )

    return StrategySignal(
        strategy="momentum",
        action="hold",
        confidence=round(1.0 - strength, 4),
        reason="momentum below threshold",
    )
