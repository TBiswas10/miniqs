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
from iteration_engine import AutoTuner, ExperimentLogger, RegimeDetector
from logger import QuantLogger
from performance import PerformanceTracker
from portfolio import Portfolio
from risk_manager import RiskConfig, RiskEngine
from strategies.mean_reversion import generate_signal as mean_reversion_signal
from strategies.momentum import generate_signal as momentum_signal
from strategies.volatility_breakout import generate_signal as volatility_breakout_signal
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
        """Apply one conservative update step.

        Logic:
        - Build a quality score from win rate, avg pnl, and drawdown penalty.
        - Convert score into a tiny bounded weight delta.
        - Re-normalize weights after update.
        """
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
            # Safe fallback to equal weights on enabled strategies.
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
        execution = ExecutionEngine(portfolio=portfolio, paper_mode=True, debug=False, realistic_simulation=True)
        logger = QuantLogger(db_path=str(db_dir / "logs_pipeline.db"))
        perf = PerformanceTracker(initial_equity=100000.0)
        feedback = FeedbackLoop(
            strategy_weights={
                "mean_reversion": 0.4,
                "momentum": 0.4,
                "volatility_breakout": 0.2,
            }
        )
        risk_engine = RiskEngine(
            initial_equity=100000.0,
            config=RiskConfig(
                base_trade_size=1.0,
                max_position_size=5.0,
                cooldown_seconds=1,
                max_loss_per_session=500.0,
                portfolio_drawdown_limit=0.12,
                per_strategy_drawdown_limit=0.08,
                extreme_loss_kill_switch=1200.0,
                strategy_kill_loss=400.0,
                vol_target=0.01,
            ),
        )
        iteration_logger = ExperimentLogger(db_path=str(db_dir / "iteration_history.db"))
        regime_detector = RegimeDetector(window=40)
        auto_tuner = AutoTuner()
        run_id = datetime.now(timezone.utc).strftime("paper_%Y%m%d_%H%M%S")
        iteration_index = 0
        last_iteration_equity = 100000.0
        recent_prices: List[float] = []

        feed = DataFeed(symbol="SIM", mode="simulated", seed=seed, start_price=100.0)
        features = FeatureEngine(ma_window=20, long_ma_window=50, vol_window=20, momentum_window=10, debug=False)

        last_trade_timestamp = None
        executed_trades = 0

        for payload in feed.start_feed(tick_count=num_ticks):
            ts = datetime.fromisoformat(str(payload["timestamp"]))
            tick = Tick(symbol="SIM", price=float(payload["mid_price"]), timestamp=ts, volume=1.0)
            recent_prices.append(tick.price)
            recent_prices = recent_prices[-200:]

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
            vb = volatility_breakout_signal(snap, breakout_factor=1.2)

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
            vb = vb.__class__(
                strategy=vb.strategy,
                action=vb.action,
                confidence=min(1.0, vb.confidence * weights.get("volatility_breakout", 0.2)),
                reason=vb.reason,
            )

            if not feedback.is_enabled("mean_reversion"):
                mr = mr.__class__(strategy=mr.strategy, action="hold", confidence=0.0, reason="auto_disabled")
            if not feedback.is_enabled("momentum"):
                mo = mo.__class__(strategy=mo.strategy, action="hold", confidence=0.0, reason="auto_disabled")
            if not feedback.is_enabled("volatility_breakout"):
                vb = vb.__class__(strategy=vb.strategy, action="hold", confidence=0.0, reason="auto_disabled")

            logger.log_signal(mr.strategy, mr.action, mr.confidence, mr.reason)
            logger.log_signal(mo.strategy, mo.action, mo.confidence, mo.reason)
            logger.log_signal(vb.strategy, vb.action, vb.confidence, vb.reason)

            chosen = evaluate_signals([mr, mo, vb], confidence_threshold=0.35)
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
                "equity": float(state["equity"]),
                "total_pnl": float(state["total_pnl"]),
                "market_volatility": float(snap.rolling_volatility),
                "strategy_weight": float(weights.get(chosen.strategy, 0.0)),
            }
            allow, reason, adjusted_trade, _ = risk_engine.assess_trade(trade, risk_state)
            if not allow:
                if "strategy_kill_switch" in reason:
                    feedback.strategy_enabled[chosen.strategy] = False
                    feedback.strategy_weights[chosen.strategy] = 0.0
                continue

            result = execution.execute_trade(adjusted_trade)
            last_trade_timestamp = adjusted_trade["timestamp"]
            executed_trades += 1
            logger.log_trade(result, strategy=chosen.strategy)
            perf.record_trade(float(result["realized_pnl_trade"]))
            perf.record_strategy_trade(chosen.strategy, float(result["realized_pnl_trade"]))

            post_state = portfolio.get_portfolio_state()
            risk_engine.record_execution(
                strategy=chosen.strategy,
                realized_pnl_trade=float(result["realized_pnl_trade"]),
                equity=float(post_state["equity"]),
            )
            if risk_engine.strategy_kill_switch.get(chosen.strategy, False):
                feedback.strategy_enabled[chosen.strategy] = False
                feedback.strategy_weights[chosen.strategy] = 0.0

            if executed_trades % 10 == 0:
                strategy_metrics = perf.strategy_metrics_for_feedback()
                if strategy_metrics:
                    feedback.update(strategy_metrics, logger=logger)

            if executed_trades > 0 and executed_trades % 20 == 0 and recent_prices:
                market = regime_detector.detect(recent_prices)
                iter_state = portfolio.get_portfolio_state()
                strategy_metrics = perf.strategy_metrics_for_feedback()
                outcomes = {
                    "equity_delta": float(iter_state["equity"]) - last_iteration_equity,
                    "drawdown": float(perf.compute_metrics(float(iter_state["total_pnl"]))["max_drawdown"]),
                    "total_pnl": float(iter_state["total_pnl"]),
                }
                rec = auto_tuner.recommend(
                    current_weights=feedback.strategy_weights,
                    risk_params={
                        "base_trade_size": risk_engine.config.base_trade_size,
                        "max_position_size": risk_engine.config.max_position_size,
                        "cooldown_seconds": risk_engine.config.cooldown_seconds,
                    },
                    market_conditions=market,
                    outcomes=outcomes,
                    strategy_metrics=strategy_metrics,
                )
                feedback.strategy_weights = dict(rec["strategy_weights"])
                for strategy, weight in feedback.strategy_weights.items():
                    feedback.strategy_enabled[strategy] = bool(weight > 0.0)

                risk_params = dict(rec["risk_params"])
                risk_engine.config.base_trade_size = float(risk_params["base_trade_size"])
                risk_engine.config.max_position_size = float(risk_params["max_position_size"])
                risk_engine.config.cooldown_seconds = int(risk_params["cooldown_seconds"])

                iteration_logger.log_experiment(
                    run_id=run_id,
                    iteration=iteration_index,
                    parameter_set={
                        "weights": feedback.strategy_weights,
                        "base_trade_size": risk_engine.config.base_trade_size,
                        "max_position_size": risk_engine.config.max_position_size,
                        "cooldown_seconds": risk_engine.config.cooldown_seconds,
                    },
                    market_conditions=rec["market_conditions"],
                    outcomes=outcomes,
                    recommendations=rec,
                )
                iteration_index += 1
                last_iteration_equity = float(iter_state["equity"])

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
        "volatility_breakout_weight": float(feedback.strategy_weights.get("volatility_breakout", 0.0)),
        "iteration_updates": float(iteration_index),
        "adaptive_base_trade_size": float(risk_engine.config.base_trade_size),
        "adaptive_max_position_size": float(risk_engine.config.max_position_size),
        "adaptive_cooldown_seconds": float(risk_engine.config.cooldown_seconds),
    }
    return summary


def main() -> None:
    summary = run_paper_trading_session(num_ticks=200, seed=42)
    print(f"Paper session complete: {summary}")


if __name__ == "__main__":
    main()
