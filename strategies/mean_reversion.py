"""Mean reversion strategy.

Input:
- FeatureSnapshot

Output:
- StrategySignal(action, confidence, reason)
"""

from __future__ import annotations

from feature_engine import FeatureSnapshot
from strategies import StrategySignal


def generate_signal(features: FeatureSnapshot, entry_threshold: float = 0.003) -> StrategySignal:
    """Generate mean-reversion signal.

    Logic:
    - Compare price vs rolling mean.
    - If price is sufficiently above mean -> sell.
    - If price is sufficiently below mean -> buy.
    - Otherwise hold.
    """
    if features.rolling_mean <= 0:
        return StrategySignal(
            strategy="mean_reversion",
            action="hold",
            confidence=0.0,
            reason="invalid rolling mean",
        )

    deviation = (features.price - features.rolling_mean) / features.rolling_mean
    strength = min(1.0, abs(deviation) / max(entry_threshold, 1e-9))

    if deviation >= entry_threshold:
        return StrategySignal(
            strategy="mean_reversion",
            action="sell",
            confidence=round(strength, 4),
            reason=f"price above mean by {deviation:.4%}",
        )

    if deviation <= -entry_threshold:
        return StrategySignal(
            strategy="mean_reversion",
            action="buy",
            confidence=round(strength, 4),
            reason=f"price below mean by {abs(deviation):.4%}",
        )

    return StrategySignal(
        strategy="mean_reversion",
        action="hold",
        confidence=round(1.0 - strength, 4),
        reason="deviation below threshold",
    )
