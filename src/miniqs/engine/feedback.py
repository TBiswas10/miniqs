"""Adaptive feedback loop for strategy weight tuning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from src.miniqs.utils.logger import QuantLogger


@dataclass
class FeedbackLoop:
    """Incrementally adapt strategy weights from recent performance.

    Logic:
    - Build a quality score from win rate, avg pnl, and drawdown penalty.
    - Convert score into a tiny bounded weight delta.
    - Re-normalize weights after update.
    """

    strategy_weights: Dict[str, float] = field(
        default_factory=lambda: {"mean_reversion": 0.4, "momentum": 0.4, "volatility_breakout": 0.2}
    )
    learning_rate: float = 0.02
    max_delta_per_step: float = 0.01
    min_weight: float = 0.05
    disable_min_trades: float = 8.0
    disable_hit_rate: float = 0.35
    disable_sharpe: float = -0.15
    reenable_hit_rate: float = 0.5
    reenable_sharpe: float = 0.05
    strategy_enabled: Dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.strategy_enabled:
            self.strategy_enabled = {name: True for name in self.strategy_weights}

    def update(
        self,
        metrics: Dict[str, Dict[str, float]],
        logger: Optional[QuantLogger] = None,
    ) -> Dict[str, float]:
        """Apply one conservative update step."""
        reason_parts: List[str] = []
        for strategy, current_weight in list(self.strategy_weights.items()):
            m = metrics.get(strategy, {})
            win_rate = float(m.get("hit_rate", m.get("win_rate", 0.5)))
            avg_pnl = float(m.get("avg_trade_pnl", 0.0))
            drawdown = float(m.get("max_drawdown", 0.0))
            sharpe = float(m.get("sharpe_ratio", 0.0))
            trade_count = float(m.get("trade_count", 0.0))

            if self.strategy_enabled.get(strategy, True):
                if trade_count >= self.disable_min_trades and (
                    win_rate < self.disable_hit_rate or sharpe < self.disable_sharpe
                ):
                    self.strategy_enabled[strategy] = False
                    self.strategy_weights[strategy] = 0.0
                    reason_parts.append(
                        f"{strategy}:auto-disabled hit_rate={win_rate:.3f} sharpe={sharpe:.3f} trades={trade_count:.0f}"
                    )
                    continue
            else:
                if trade_count >= self.disable_min_trades and (
                    win_rate >= self.reenable_hit_rate and sharpe >= self.reenable_sharpe
                ):
                    self.strategy_enabled[strategy] = True
                    self.strategy_weights[strategy] = max(self.strategy_weights.get(strategy, 0.0), self.min_weight)
                    reason_parts.append(
                        f"{strategy}:re-enabled hit_rate={win_rate:.3f} sharpe={sharpe:.3f} trades={trade_count:.0f}"
                    )
                else:
                    self.strategy_weights[strategy] = 0.0
                    continue

            # Positive score favors higher weight; negative score lowers it.
            score = (win_rate - 0.5) + (avg_pnl * 0.01) + (sharpe * 0.08) - (drawdown * 0.02)
            raw_delta = self.learning_rate * score
            delta = max(-self.max_delta_per_step, min(self.max_delta_per_step, raw_delta))

            new_weight = max(self.min_weight, current_weight + delta)
            self.strategy_weights[strategy] = new_weight
            reason_parts.append(
                f"{strategy}:score={score:.4f} raw_delta={raw_delta:.6f} clamped_delta={delta:.6f} -> {new_weight:.6f}"
            )

        self._normalize_weights()

        weight_summary = " ".join(
            f"{name}={value:.4f}" for name, value in sorted(self.strategy_weights.items())
        )
        print(f"[feedback_loop] {weight_summary}")
        if logger is not None:
            logger.log_feedback(dict(self.strategy_weights), "; ".join(reason_parts))
        return dict(self.strategy_weights)

    def _normalize_weights(self) -> None:
        enabled_strategies = [s for s, enabled in self.strategy_enabled.items() if enabled]
        for strategy, enabled in self.strategy_enabled.items():
            if not enabled:
                self.strategy_weights[strategy] = 0.0

        total = sum(self.strategy_weights.get(s, 0.0) for s in enabled_strategies)
        if total <= 0:
            if not enabled_strategies:
                self.strategy_enabled = {name: True for name in self.strategy_weights}
                enabled_strategies = list(self.strategy_weights.keys())
            n = max(1, len(enabled_strategies))
            equal_weight = 1.0 / n
            for k in enabled_strategies:
                self.strategy_weights[k] = equal_weight
            return

        for k in enabled_strategies:
            v = self.strategy_weights.get(k, 0.0)
            self.strategy_weights[k] = v / total

    def is_enabled(self, strategy: str) -> bool:
        return bool(self.strategy_enabled.get(strategy, True))
