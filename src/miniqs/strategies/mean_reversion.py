"""Range-aware mean reversion strategy.

Input:
- FeatureSnapshot

Output:
- StrategySignal(action, confidence, reason)
"""

from __future__ import annotations

from dataclasses import dataclass

from src.miniqs.engine.feature_engine import FeatureSnapshot
from src.miniqs.strategies import StrategySignal


def _effective_volatility(features: FeatureSnapshot) -> float:
    """Return volatility in comparable units for gating.

    `FeatureEngine` currently emits `rolling_volatility` as absolute price range,
    but strategy thresholds are configured in return-space (e.g. 0.03 == 3%).
    For large-priced assets, normalize obvious absolute ranges by current price.
    """
    raw_vol = float(features.rolling_volatility)
    price = max(float(features.price), 1e-9)
    if raw_vol > 1.0:
        return raw_vol / price
    return raw_vol


def generate_signal(
    features: FeatureSnapshot,
    entry_threshold: float = 0.003,
    max_trend_momentum: float = 0.004,
    max_volatility: float = 0.03,
    max_spread: float = 0.0015,
    min_order_imbalance: float = -0.2,
    max_order_imbalance: float = 0.2,
    rsi_oversold: float = 35.0,
    rsi_overbought: float = 65.0,
) -> StrategySignal:
    """Generate mean-reversion signal with simple regime gating.

    Logic:
    - Mean reversion is most reliable in range-bound / lower-volatility regimes.
    - If momentum is too directional or volatility is too high, hold.
    - RSI filter: Only buy if oversold (< 35), only sell if overbought (> 65).
    - Otherwise, fade deviations from the rolling mean.
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

    if abs(features.momentum) > max(max_trend_momentum, 1e-9):
        return StrategySignal(
            strategy="mean_reversion",
            action="hold",
            confidence=0.0,
            reason=f"trend filter active momentum={features.momentum:.4%}",
        )

    effective_volatility = _effective_volatility(features)
    if effective_volatility > max_volatility:
        return StrategySignal(
            strategy="mean_reversion",
            action="hold",
            confidence=0.0,
            reason=f"volatility filter active vol={effective_volatility:.4f}",
        )

    spread = float(getattr(features, "spread", 0.0))
    if spread > max(max_spread, 0.0):
        return StrategySignal(
            strategy="mean_reversion",
            action="hold",
            confidence=0.0,
            reason=f"spread filter active spread={spread:.4%}",
        )

    order_imbalance = float(getattr(features, "order_imbalance", 0.0))
    if order_imbalance < min_order_imbalance or order_imbalance > max_order_imbalance:
        return StrategySignal(
            strategy="mean_reversion",
            action="hold",
            confidence=0.0,
            reason=f"imbalance filter active imbalance={order_imbalance:.4f}",
        )

    current_rsi = float(getattr(features, "rsi", 50.0))

    if deviation >= entry_threshold:
        if current_rsi < rsi_overbought:
            return StrategySignal(
                strategy="mean_reversion",
                action="hold",
                confidence=0.0,
                reason=f"rsi not overbought enough ({current_rsi:.1f} < {rsi_overbought})",
            )
        return StrategySignal(
            strategy="mean_reversion",
            action="sell",
            confidence=round(strength, 4),
            reason=f"price above mean by {deviation:.4%} and RSI={current_rsi:.1f}",
        )

    if deviation <= -entry_threshold:
        if current_rsi > rsi_oversold:
            return StrategySignal(
                strategy="mean_reversion",
                action="hold",
                confidence=0.0,
                reason=f"rsi not oversold enough ({current_rsi:.1f} > {rsi_oversold})",
            )
        return StrategySignal(
            strategy="mean_reversion",
            action="buy",
            confidence=round(strength, 4),
            reason=f"price below mean by {abs(deviation):.4%} and RSI={current_rsi:.1f}",
        )

    return StrategySignal(
        strategy="mean_reversion",
        action="hold",
        confidence=round(1.0 - strength, 4),
        reason="deviation below threshold",
    )


@dataclass(frozen=True)
class MeanReversionStrategy:
    name: str = "mean_reversion"

    def generate_signal(self, features: FeatureSnapshot, **params: float) -> StrategySignal:
        return generate_signal(
            features,
            entry_threshold=float(params.get("entry_threshold", 0.003)),
            max_trend_momentum=float(params.get("max_trend_momentum", 0.004)),
            max_volatility=float(params.get("max_volatility", 0.03)),
            max_spread=float(params.get("max_spread", 0.0015)),
            min_order_imbalance=float(params.get("min_order_imbalance", -0.2)),
            max_order_imbalance=float(params.get("max_order_imbalance", 0.2)),
            rsi_oversold=float(params.get("rsi_oversold", 35.0)),
            rsi_overbought=float(params.get("rsi_overbought", 65.0)),
        )
