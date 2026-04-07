"""Volatility breakout strategy.

Input:
- FeatureSnapshot

Output:
- StrategySignal(action, confidence, reason)
"""

from __future__ import annotations

from feature_engine import FeatureSnapshot
from strategies import StrategySignal


def generate_signal(features: FeatureSnapshot, breakout_factor: float = 1.2) -> StrategySignal:
    """Generate breakout signal using momentum relative to rolling volatility.

    Logic:
    - Large positive momentum vs volatility -> buy breakout.
    - Large negative momentum vs volatility -> sell breakdown.
    - Otherwise hold.
    """
    vol = max(features.rolling_volatility, 1e-6)
    threshold = breakout_factor * vol
    mom = features.momentum
    strength = min(1.0, abs(mom) / max(threshold, 1e-9))

    if mom >= threshold:
        return StrategySignal(
            strategy="volatility_breakout",
            action="buy",
            confidence=round(strength, 4),
            reason=f"momentum breakout above {threshold:.4%}",
        )

    if mom <= -threshold:
        return StrategySignal(
            strategy="volatility_breakout",
            action="sell",
            confidence=round(strength, 4),
            reason=f"momentum breakdown below {-threshold:.4%}",
        )

    return StrategySignal(
        strategy="volatility_breakout",
        action="hold",
        confidence=round(1.0 - strength, 4),
        reason="momentum within volatility band",
    )
