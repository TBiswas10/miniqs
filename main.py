"""Entry point for the mini quant trading system.

Implementation is intentionally incremental.

Feedback loop skeleton:
- Input: strategy performance metrics (from performance.py in later step)
- Output: updated strategy weights with small bounded adjustments
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from data_feed import DataFeed, Tick
from execution import ExecutionEngine
from feature_engine import FeatureEngine
from logger import QuantLogger
from performance import PerformanceTracker
from portfolio import Portfolio
from risk_manager import check_risk
from strategies.mean_reversion import generate_signal as mean_reversion_signal
from strategies.momentum import generate_signal as momentum_signal
from strategy_evaluator import evaluate_signals


@dataclass
class FeedbackLoop:
    """Incrementally adapt strategy weights from recent performance.

    Input contract for ``metrics`` (typically produced by performance.py):
    - metrics[strategy_name] = {
        "win_rate": float in [0, 1],
        "avg_trade_pnl": float,
        "max_drawdown": float >= 0
      }

    Output:
    - updated ``weights`` dict where values are normalized and bounded.
    """

    strategy_weights: Dict[str, float] = field(
        default_factory=lambda: {"mean_reversion": 0.5, "momentum": 0.5}
    )
    learning_rate: float = 0.02
    max_delta_per_step: float = 0.01
    min_weight: float = 0.1

    def update(
        self,
        metrics: Dict[str, Dict[str, float]],
        logger: Optional[QuantLogger] = None,
    ) -> Dict[str, float]:
        """Apply one conservative update step.

        Logic:
        - Build a quality score from win rate, avg pnl, and drawdown penalty.
        - Convert score into a tiny bounded weight delta.
        - Re-normalize weights after update.
        """
        reason_parts: List[str] = []
        for strategy, current_weight in list(self.strategy_weights.items()):
            m = metrics.get(strategy, {})
            win_rate = float(m.get("win_rate", 0.5))
            avg_pnl = float(m.get("avg_trade_pnl", 0.0))
            drawdown = float(m.get("max_drawdown", 0.0))

            # Positive score favors higher weight; negative score lowers it.
            score = (win_rate - 0.5) + (avg_pnl * 0.01) - (drawdown * 0.02)
            raw_delta = self.learning_rate * score
            delta = max(-self.max_delta_per_step, min(self.max_delta_per_step, raw_delta))

            new_weight = max(self.min_weight, current_weight + delta)
            self.strategy_weights[strategy] = new_weight
            reason_parts.append(
                f"{strategy}:score={score:.4f} raw_delta={raw_delta:.6f} clamped_delta={delta:.6f} -> {new_weight:.6f}"
            )

        self._normalize_weights()

        print(
            "[feedback_loop] "
            f"mean_reversion={self.strategy_weights.get('mean_reversion', 0.0):.4f} "
            f"momentum={self.strategy_weights.get('momentum', 0.0):.4f}"
        )
        if logger is not None:
            logger.log_feedback(dict(self.strategy_weights), "; ".join(reason_parts))
        return dict(self.strategy_weights)

    def _normalize_weights(self) -> None:
        total = sum(self.strategy_weights.values())
        if total <= 0:
            # Safe fallback to equal weights.
            n = max(1, len(self.strategy_weights))
            equal_weight = 1.0 / n
            for k in self.strategy_weights:
                self.strategy_weights[k] = equal_weight
            return

        for k, v in list(self.strategy_weights.items()):
            self.strategy_weights[k] = v / total


def run_feedback_simulation(num_ticks: int = 100) -> Dict[str, float]:
    """Simple demo of gradual adjustments over synthetic 100-tick metrics.

    Input:
    - num_ticks: number of update iterations

    Output:
    - final strategy weights dict
    """
    loop = FeedbackLoop()
    for tick in range(num_ticks):
        # Synthetic trend: momentum improves slightly, mean reversion weakens slightly.
        metrics = {
            "mean_reversion": {
                "win_rate": max(0.45, 0.52 - tick * 0.0003),
                "avg_trade_pnl": max(-1.0, 0.2 - tick * 0.01),
                "max_drawdown": min(5.0, 1.0 + tick * 0.01),
            },
            "momentum": {
                "win_rate": min(0.62, 0.50 + tick * 0.0005),
                "avg_trade_pnl": min(2.0, 0.1 + tick * 0.015),
                "max_drawdown": max(0.2, 1.2 - tick * 0.005),
            },
        }
        loop.update(metrics)

    return dict(loop.strategy_weights)


def run_paper_trading_session(num_ticks: int = 200, seed: int = 42) -> Dict[str, float]:
    """Run a full paper-mode integration pipeline on simulated ticks.

    Pipeline:
    data_feed -> feature_engine -> strategies -> strategy_evaluator ->
    risk_manager -> execution/portfolio -> logger/performance -> feedback loop

    Input:
    - num_ticks: number of simulated ticks
    - seed: RNG seed for deterministic behavior

    Output:
    - summary metrics dict including performance and final strategy weights
    """
    with tempfile.TemporaryDirectory() as tmp:
        db_dir = Path(tmp)
        portfolio = Portfolio(db_path=str(db_dir / "portfolio_pipeline.db"), initial_cash=100000.0)
        execution = ExecutionEngine(portfolio=portfolio, paper_mode=True, debug=False)
        logger = QuantLogger(db_path=str(db_dir / "logs_pipeline.db"))
        perf = PerformanceTracker(initial_equity=100000.0)
        feedback = FeedbackLoop()

        feed = DataFeed(symbol="SIM", mode="simulated", seed=seed, start_price=100.0)
        features = FeatureEngine(ma_window=20, long_ma_window=50, vol_window=20, momentum_window=10, debug=False)

        last_trade_timestamp = None
        executed_trades = 0

        for payload in feed.start_feed(tick_count=num_ticks):
            ts = datetime.fromisoformat(str(payload["timestamp"]))
            tick = Tick(symbol="SIM", price=float(payload["mid_price"]), timestamp=ts, volume=1.0)

            snap = features.update(tick)
            portfolio.update_pnl(tick.price)
            state = portfolio.get_portfolio_state()
            perf.record_equity(float(state["equity"]))
            logger.log_portfolio_snapshot(state)

            if snap is None:
                continue

            weights = feedback.strategy_weights
            mr = mean_reversion_signal(snap, entry_threshold=0.003)
            mo = momentum_signal(snap, momentum_threshold=0.002)

            mr = mr.__class__(
                strategy=mr.strategy,
                action=mr.action,
                confidence=min(1.0, mr.confidence * weights.get("mean_reversion", 0.5)),
                reason=mr.reason,
            )
            mo = mo.__class__(
                strategy=mo.strategy,
                action=mo.action,
                confidence=min(1.0, mo.confidence * weights.get("momentum", 0.5)),
                reason=mo.reason,
            )

            logger.log_signal(mr.strategy, mr.action, mr.confidence, mr.reason)
            logger.log_signal(mo.strategy, mo.action, mo.confidence, mo.reason)

            chosen = evaluate_signals([mr, mo], confidence_threshold=0.35)
            if chosen is None:
                continue

            trade = {
                "action": chosen.action,
                "size": 1.0,
                "confidence": chosen.confidence,
                "price": tick.price,
                "timestamp": tick.timestamp.isoformat(),
                "strategy": chosen.strategy,
            }
            risk_state = {
                "current_position": float(state["position_size"]),
                "last_trade_timestamp": last_trade_timestamp,
                "session_loss": max(0.0, -float(state["total_pnl"])),
                "max_position_size": 5.0,
                "cooldown_seconds": 1,
                "max_loss_per_session": 500.0,
            }
            allow, _ = check_risk(trade, risk_state)
            if not allow:
                continue

            result = execution.execute_trade(trade)
            last_trade_timestamp = trade["timestamp"]
            executed_trades += 1
            logger.log_trade(result, strategy=chosen.strategy)
            perf.record_trade(float(result["realized_pnl_trade"]))
            perf.record_strategy_trade(chosen.strategy, float(result["realized_pnl_trade"]))

            if executed_trades % 10 == 0:
                strategy_metrics = perf.strategy_metrics_for_feedback()
                if strategy_metrics:
                    feedback.update(strategy_metrics, logger=logger)

        final_state = portfolio.get_portfolio_state()
        metrics = perf.compute_metrics(latest_total_pnl=float(final_state["total_pnl"]))
        logger.log_performance_metrics(metrics)
        feed.stop_feed()

    summary = {
        "executed_trades": float(executed_trades),
        "total_pnl": float(metrics["total_pnl"]),
        "win_rate": float(metrics["win_rate"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "sharpe_ratio": float(metrics["sharpe_ratio"]),
        "mean_reversion_weight": float(feedback.strategy_weights["mean_reversion"]),
        "momentum_weight": float(feedback.strategy_weights["momentum"]),
    }
    return summary


def main() -> None:
    summary = run_paper_trading_session(num_ticks=200, seed=42)
    print(f"Paper session complete: {summary}")


if __name__ == "__main__":
    main()
