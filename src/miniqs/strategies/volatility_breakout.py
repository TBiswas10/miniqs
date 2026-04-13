"""Volatility expansion breakout strategy.

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
    breakout_factor: float = 1.2,
    min_volatility: float = 0.005,
    min_volatility_expansion: float = 1.1,
    max_spread: float = 0.002,
    min_volume_confirmation: float = 1.0,
    use_atr_threshold: bool = True,
) -> StrategySignal:
    """Generate breakout signal on momentum expansion relative to volatility and ATR.

    Logic:
    - Ignore very low-volatility chop.
    - Require momentum to exceed a volatility-scaled threshold.
    - ATR adjustment: ATR provides a smoother volatility measure for thresholding.
    - Require price to already be on the breakout side of the rolling mean.
    """
    if features.rolling_mean <= 0:
        return StrategySignal(
            strategy="volatility_breakout",
            action="hold",
            confidence=0.0,
            reason="invalid rolling mean",
        )

    return_volatility = float(getattr(features, "return_volatility", features.rolling_volatility))
    baseline_return_volatility = float(
        getattr(features, "baseline_return_volatility", min_volatility)
    )

    vol = max(return_volatility, 1e-6)
    if vol < min_volatility:
        return StrategySignal(
            strategy="volatility_breakout",
            action="hold",
            confidence=0.0,
            reason=f"return volatility below expansion floor {vol:.4f}",
        )

    expansion = vol / max(baseline_return_volatility, 1e-9)
    if expansion < min_volatility_expansion:
        return StrategySignal(
            strategy="volatility_breakout",
            action="hold",
            confidence=0.0,
            reason=f"volatility expansion too weak ratio={expansion:.3f}",
        )

    spread = float(getattr(features, "spread", 0.0))
    if spread > max(max_spread, 0.0):
        return StrategySignal(
            strategy="volatility_breakout",
            action="hold",
            confidence=0.0,
            reason=f"spread too wide spread={spread:.4%}",
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
            strategy="volatility_breakout",
            action="hold",
            confidence=0.0,
            reason=f"volume confirmation too weak {volume_confirmation:.3f}",
        )

    # ATR adjustment to threshold
    atr = float(getattr(features, "atr", 0.0))
    price = max(float(features.price), 1e-9)
    atr_ratio = atr / price if price > 0 else 0.0
    
    # Threshold is scaled by breakout_factor and volatility,
    # optionally incorporating ATR for smoother thresholds.
    effective_vol = (0.5 * vol + 0.5 * atr_ratio) if (use_atr_threshold and atr_ratio > 0) else vol
    threshold = breakout_factor * max(effective_vol, 1e-6)
    
    mom = features.momentum
    trend = (features.price - features.rolling_mean) / features.rolling_mean
    strength = min(1.0, abs(mom) / max(threshold, 1e-9))

    if mom >= threshold and trend >= 0:
        return StrategySignal(
            strategy="volatility_breakout",
            action="buy",
            confidence=round(strength, 4),
            reason=f"upside volatility expansion momentum={mom:.4%} threshold={threshold:.4%}",
        )

    if mom <= -threshold and trend <= 0:
        return StrategySignal(
            strategy="volatility_breakout",
            action="sell",
            confidence=round(strength, 4),
            reason=f"downside volatility expansion momentum={mom:.4%} threshold={threshold:.4%}",
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
            min_volatility_expansion=float(params.get("min_volatility_expansion", 1.1)),
            max_spread=float(params.get("max_spread", 0.002)),
            min_volume_confirmation=float(params.get("min_volume_confirmation", 1.0)),
            use_atr_threshold=bool(params.get("use_atr_threshold", True)),
        )
