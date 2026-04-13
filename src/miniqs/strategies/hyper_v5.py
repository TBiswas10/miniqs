"""Hyper-V5 Ultra-Sensitive Scalper.

Logic:
1. Trigger: If Price deviates from EMA9 by more than sensitivity (default 1bp).
2. RSI Filter: Avoid buying if RSI is extreme (>80) or selling if RSI is extreme (<20).
3. Confidence: Linear ramp from 0.05 to 1.0 based on distance.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.miniqs.strategies import StrategySignal

if TYPE_CHECKING:
    from src.miniqs.engine.feature import FeatureSnapshot


@dataclass(frozen=True)
class HyperV5Strategy:
    name: str = "hyper_v5"

    def generate_signal(self, features: FeatureSnapshot, **params: float) -> StrategySignal:
        ema9 = getattr(features, "ema9", 0.0)
        price = features.price
        rsi = features.rsi
        
        # Parameters
        sensitivity = params.get("sensitivity", 0.0001)  # 1 bp (0.01%)
        rsi_floor = params.get("rsi_floor", 20.0)
        rsi_ceiling = params.get("rsi_ceiling", 80.0)
        
        diff_pct = (price - ema9) / max(ema9, 1e-9)
        
        # BUY: Price is above EMA9 (Momentum) and not extremely overbought
        if diff_pct > sensitivity and rsi < rsi_ceiling:
            confidence = min(1.0, 0.1 + (diff_pct / (sensitivity * 5.0)))
            return StrategySignal(
                strategy=self.name,
                action="buy",
                confidence=round(confidence, 4),
                reason=f"Hyper-Momentum Long: price {diff_pct:.4%} above EMA9"
            )

        # SELL: Price is below EMA9 (Momentum) and not extremely oversold
        if diff_pct < -sensitivity and rsi > rsi_floor:
            confidence = min(1.0, 0.1 + (abs(diff_pct) / (sensitivity * 5.0)))
            return StrategySignal(
                strategy=self.name,
                action="sell",
                confidence=round(confidence, 4),
                reason=f"Hyper-Momentum Short: price {diff_pct:.4%} below EMA9"
            )

        return StrategySignal(
            strategy=self.name,
            action="hold",
            confidence=0.0,
            reason="Within micro-stability bounds"
        )
