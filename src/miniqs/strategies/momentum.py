"""Trend-following momentum strategy.

Input:
- FeatureSnapshot

Output:
- StrategySignal(action, confidence, reason)
"""

from __future__ import annotations

from dataclasses import dataclass

from src.miniqs.engine.feature_engine import FeatureSnapshot
from src.miniqs.strategies import StrategySignal


def generate_signal(
    features: FeatureSnapshot,
    momentum_threshold: float = 0.002,
    trend_threshold: float = 0.001,
    min_trend_persistence: float = 0.55,
    min_volume_confirmation: float = 1.0,
    macd_confirmation: bool = True,
) -> StrategySignal:
    """Generate trend-following signal.

    Logic:
    - Require directional momentum.
    - Require price location relative to mean to confirm trend direction.
    - MACD confirmation: MACD should align with signal line direction.
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

    default_persistence = 1.0 if (mom == 0.0 or trend == 0.0 or (mom > 0 and trend > 0) or (mom < 0 and trend < 0)) else 0.0
    trend_persistence = float(getattr(features, "trend_persistence", default_persistence))
    if trend_persistence < min_trend_persistence:
        return StrategySignal(
            strategy="momentum",
            action="hold",
            confidence=0.0,
            reason=f"trend persistence too weak {trend_persistence:.3f}",
        )

    volume_confirmation = float(
        getattr(
            features,
            "volume_confirmation",
            getattr(features, "relative_volume", 1.0),
        )
    )
    if volume_confirmation < min_volume_confirmation:
        return StrategySignal(
            strategy="momentum",
            action="hold",
            confidence=0.0,
            reason=f"volume confirmation too weak {volume_confirmation:.3f}",
        )

    # MACD confirmation
    macd = float(getattr(features, "macd", 0.0))
    macd_s = float(getattr(features, "macd_signal", 0.0))
    macd_confirmed_up = macd > macd_s if macd_confirmation else True
    macd_confirmed_down = macd < macd_s if macd_confirmation else True

    if mom >= momentum_threshold and trend >= -trend_threshold:
        if not macd_confirmed_up:
            return StrategySignal(
                strategy="momentum",
                action="hold",
                confidence=0.0,
                reason=f"macd not confirming uptrend ({macd:.4f} <= {macd_s:.4f})",
            )
        return StrategySignal(
            strategy="momentum",
            action="buy",
            confidence=round(strength, 4),
            reason=f"uptrend confirmed momentum={mom:.4%} trend={trend:.4%} MACD={macd:.4f}",
        )

    if mom <= -momentum_threshold and trend <= trend_threshold:
        if not macd_confirmed_down:
            return StrategySignal(
                strategy="momentum",
                action="hold",
                confidence=0.0,
                reason=f"macd not confirming downtrend ({macd:.4f} >= {macd_s:.4f})",
            )
        return StrategySignal(
            strategy="momentum",
            action="sell",
            confidence=round(strength, 4),
            reason=f"downtrend confirmed momentum={mom:.4%} trend={trend:.4%} MACD={macd:.4f}",
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
            min_trend_persistence=float(params.get("min_trend_persistence", 0.55)),
            min_volume_confirmation=float(params.get("min_volume_confirmation", 1.0)),
            macd_confirmation=bool(params.get("macd_confirmation", True)),
        )
