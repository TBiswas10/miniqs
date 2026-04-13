"""Trend-Robust Scalping Strategy.

Logic:
1. Trend Filter: Only Buy if EMA9 > EMA21. Only Sell if EMA9 < EMA21.
2. Trigger:
   - Buy if price is below Mean and RSI < oversold_threshold.
   - Sell if price is above Mean and RSI > overbought_threshold.
3. Confidence scaling based on distance from Mean.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.miniqs.strategies import StrategySignal

if TYPE_CHECKING:
    from src.miniqs.engine.feature import FeatureSnapshot


@dataclass(frozen=True)
class TrendRobustStrategy:
    name: str = "trend_robust"

    def generate_signal(self, features: FeatureSnapshot, **params: float) -> StrategySignal:
        ema9 = getattr(features, "ema9", 0.0)
        ema21 = getattr(features, "ema21", 0.0)
        price = features.price
        mean = features.rolling_mean
        rsi = features.rsi
        
        # Parameters
        oversold = params.get("rsi_oversold", 45.0)
        overbought = params.get("rsi_overbought", 55.0)
        min_trend_gap = params.get("min_trend_gap", 0.0001) # 1 bp gap for trend confirmation
        
        trend_up = (ema9 - ema21) / max(ema21, 1e-9) > min_trend_gap
        trend_down = (ema21 - ema9) / max(ema9, 1e-9) > min_trend_gap
        
        # Mean Distance
        dist_pct = (price - mean) / max(mean, 1e-9)
        
        # BUY Logic: Uptrend + Pullback (price < mean & RSI low)
        if trend_up and dist_pct < -0.0001 and rsi < oversold:
            confidence = min(1.0, abs(dist_pct) * 1000.0) # Scale confidence by dip depth
            return StrategySignal(
                strategy=self.name,
                action="buy",
                confidence=round(confidence, 4),
                reason=f"Uptrend pullback: price {dist_pct:.2%} below mean, RSI {rsi:.1f}"
            )
            
        # SELL Logic: Downtrend + Over-extension (price > mean & RSI high)
        if trend_down and dist_pct > 0.0001 and rsi > overbought:
            confidence = min(1.0, abs(dist_pct) * 1000.0)
            return StrategySignal(
                strategy=self.name,
                action="sell",
                confidence=round(confidence, 4),
                reason=f"Downtrend extension: price {dist_pct:.2%} above mean, RSI {rsi:.1f}"
            )

        return StrategySignal(
            strategy=self.name,
            action="hold",
            confidence=0.0,
            reason="No clear trend-aligned micro-setup"
        )
