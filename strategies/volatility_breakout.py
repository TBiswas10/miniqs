"""Volatility expansion breakout strategy.

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
    breakout_factor: float = 1.2,
    min_volatility: float = 0.005,
) -> StrategySignal:
    """Generate breakout signal on momentum expansion relative to volatility.

    Logic:
    - Ignore very low-volatility chop.
    - Require momentum to exceed a volatility-scaled threshold.
    - Require price to already be on the breakout side of the rolling mean.
    """
    if features.rolling_mean <= 0:
        return StrategySignal(
            strategy="volatility_breakout",
            action="hold",
            confidence=0.0,
            reason="invalid rolling mean",
        )

    vol = max(features.rolling_volatility, 1e-6)
    if vol < min_volatility:
        return StrategySignal(
            strategy="volatility_breakout",
            action="hold",
            confidence=0.0,
            reason=f"volatility below expansion floor {vol:.4f}",
        )

    threshold = breakout_factor * vol
    mom = features.momentum
    trend = (features.price - features.rolling_mean) / features.rolling_mean
    strength = min(1.0, abs(mom) / max(threshold, 1e-9))

    if mom >= threshold and trend >= 0:
        return StrategySignal(
            strategy="volatility_breakout",
            action="buy",
            confidence=round(strength, 4),
            reason=f"upside volatility expansion momentum={mom:.4%}",
        )

    if mom <= -threshold and trend <= 0:
        return StrategySignal(
            strategy="volatility_breakout",
            action="sell",
            confidence=round(strength, 4),
            reason=f"downside volatility expansion momentum={mom:.4%}",
        )

    return StrategySignal(
        strategy="volatility_breakout",
        action="hold",
        confidence=round(1.0 - strength, 4),
        reason="expansion threshold not met",
    )


@dataclass(frozen=True)
class VolatilityBreakoutStrategy:
    name: str = "volatility_breakout"

    def generate_signal(self, features: FeatureSnapshot, **params: float) -> StrategySignal:
        return generate_signal(
            features,
            breakout_factor=float(params.get("breakout_factor", 1.2)),
            min_volatility=float(params.get("min_volatility", 0.005)),
        )
