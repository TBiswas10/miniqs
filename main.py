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
from typing import Any, Dict, List, Optional, cast

from data_feed import DataFeed, Tick
from event_bus import (
    EventBus,
    EventDispatcher,
    ExperimentLogEvent,
    FillEvent,
    IterationEvent,
    MarketEvent,
    OrderEvent,
    SignalEvent,
)
from execution import ExecutionEngine
from feature_engine import FeatureEngine
from iteration_engine import AutoTuner, ExperimentLogger, RegimeDetector
from logger import QuantLogger
from performance import PerformanceTracker
from portfolio import Portfolio
from risk_manager import RiskConfig, RiskEngine
from strategies import StrategyRegistry, default_strategy_registry, generate_weighted_signals
from strategy_evaluator import emit_signal_event, evaluate_signals_v2


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


@dataclass
class PipelineRuntime:
    portfolio: Portfolio
    execution: ExecutionEngine
    logger: QuantLogger
    perf: PerformanceTracker
    feedback: FeedbackLoop
    risk_engine: RiskEngine
    features: FeatureEngine
    regime_detector: RegimeDetector
    auto_tuner: AutoTuner
    iteration_logger: ExperimentLogger
    strategy_registry: StrategyRegistry
    confidence_threshold: float
    run_id: str
    recent_prices: List[float] = field(default_factory=list)
    iteration_index: int = 0
    last_iteration_equity: float = 100000.0
    last_trade_timestamp: Optional[str] = None
    executed_trades: int = 0


def _on_market_event(event: MarketEvent, bus: EventBus, runtime: PipelineRuntime) -> None:
    tick = event.tick
    runtime.recent_prices.append(float(tick.price))
    runtime.recent_prices = runtime.recent_prices[-200:]

    snap = runtime.features.update(tick)
    runtime.portfolio.update_pnl(tick.price)
    state = runtime.portfolio.get_portfolio_state()
    runtime.perf.record_equity(float(state["equity"]))
    runtime.logger.log_portfolio_snapshot(state)

    if snap is None:
        return

    weights = runtime.feedback.strategy_weights
    signals = generate_weighted_signals(
        features=snap,
        registry=runtime.strategy_registry,
        weights=weights,
        enabled={
            "mean_reversion": runtime.feedback.is_enabled("mean_reversion"),
            "momentum": runtime.feedback.is_enabled("momentum"),
            "volatility_breakout": runtime.feedback.is_enabled("volatility_breakout"),
        },
        params={
            "mean_reversion": {"entry_threshold": 0.003},
            "momentum": {"momentum_threshold": 0.002},
            "volatility_breakout": {"breakout_factor": 1.2},
        },
    )
    mr = signals["mean_reversion"]
    mo = signals["momentum"]
    vb = signals["volatility_breakout"]

    runtime.logger.log_signal(mr.strategy, mr.action, mr.confidence, mr.reason)
    runtime.logger.log_signal(mo.strategy, mo.action, mo.confidence, mo.reason)
    runtime.logger.log_signal(vb.strategy, vb.action, vb.confidence, vb.reason)

    chosen = evaluate_signals_v2(
        [mr, mo, vb],
        confidence_threshold=runtime.confidence_threshold,
        profile="default",
        strategy_normalization={"mean_reversion": 1.05, "momentum": 0.9, "volatility_breakout": 1.1},
        dominance_cap=0.65,
    )
    if chosen is None:
        return

    trade = {
        "action": chosen.action,
        "size": 1.0,
        "confidence": chosen.confidence,
        "price": tick.price,
        "timestamp": tick.timestamp.isoformat(),
        "strategy": chosen.strategy,
        "symbol": tick.symbol,
    }
    risk_state = {
        "current_position": float(state["position_size"]),
        "last_trade_timestamp": runtime.last_trade_timestamp,
        "session_loss": max(0.0, -float(state["total_pnl"])),
        "max_position_size": float(runtime.risk_engine.config.max_position_size),
        "cooldown_seconds": int(runtime.risk_engine.config.cooldown_seconds),
        "max_loss_per_session": float(runtime.risk_engine.config.max_loss_per_session),
        "equity": float(state["equity"]),
        "total_pnl": float(state["total_pnl"]),
        "market_volatility": float(snap.rolling_volatility),
        "strategy_weight": float(weights.get(chosen.strategy, 0.0)),
    }
    emit_signal_event(bus=bus, chosen=chosen, trade=trade, risk_state=risk_state)


def _on_signal_event(event: SignalEvent, bus: EventBus, runtime: PipelineRuntime) -> None:
    allow, reason, adjusted_trade, _ = runtime.risk_engine.assess_trade(event.trade, event.risk_state)
    if not allow:
        runtime.logger.log_risk_block(reason, str(event.trade))
        if "strategy_kill_switch" in reason:
            runtime.feedback.strategy_enabled[event.strategy] = False
            runtime.feedback.strategy_weights[event.strategy] = 0.0
        return
    bus.publish(OrderEvent(strategy=event.strategy, trade=adjusted_trade, reason=reason))


def _on_order_event(event: OrderEvent, bus: EventBus, runtime: PipelineRuntime) -> None:
    result = runtime.execution.execute_trade(event.trade)
    bus.publish(FillEvent(strategy=event.strategy, trade=event.trade, result=result))


def _on_fill_event(event: FillEvent, bus: EventBus, runtime: PipelineRuntime) -> None:
    runtime.last_trade_timestamp = str(event.trade["timestamp"])
    runtime.executed_trades += 1
    runtime.logger.log_trade(cast(Dict[str, float], event.result), strategy=event.strategy)
    runtime.perf.record_trade(float(event.result["realized_pnl_trade"]))
    runtime.perf.record_strategy_trade(event.strategy, float(event.result["realized_pnl_trade"]))

    post_state = runtime.portfolio.get_portfolio_state()
    runtime.risk_engine.record_execution(
        strategy=event.strategy,
        realized_pnl_trade=float(event.result["realized_pnl_trade"]),
        equity=float(post_state["equity"]),
    )
    if runtime.risk_engine.strategy_kill_switch.get(event.strategy, False):
        runtime.feedback.strategy_enabled[event.strategy] = False
        runtime.feedback.strategy_weights[event.strategy] = 0.0

    if runtime.executed_trades % 10 == 0:
        strategy_metrics = runtime.perf.strategy_metrics_for_feedback()
        if strategy_metrics:
            runtime.feedback.update(strategy_metrics, logger=runtime.logger)

    if runtime.executed_trades > 0 and runtime.executed_trades % 20 == 0 and runtime.recent_prices:
        market = runtime.regime_detector.detect(runtime.recent_prices)
        iter_state = runtime.portfolio.get_portfolio_state()
        strategy_metrics = runtime.perf.strategy_metrics_for_feedback()
        outcomes = {
            "equity_delta": float(iter_state["equity"]) - runtime.last_iteration_equity,
            "drawdown": float(runtime.perf.compute_metrics(float(iter_state["total_pnl"]))["max_drawdown"]),
            "total_pnl": float(iter_state["total_pnl"]),
        }
        bus.publish(
            IterationEvent(
                run_id=runtime.run_id,
                iteration=runtime.iteration_index,
                current_weights=dict(runtime.feedback.strategy_weights),
                risk_params={
                    "base_trade_size": float(runtime.risk_engine.config.base_trade_size),
                    "max_position_size": float(runtime.risk_engine.config.max_position_size),
                    "cooldown_seconds": float(runtime.risk_engine.config.cooldown_seconds),
                },
                market_conditions={
                    "regime": market.regime,
                    "realized_volatility": float(market.realized_volatility),
                    "trend_slope": float(market.trend_slope),
                    "momentum": float(market.momentum),
                },
                outcomes=outcomes,
                strategy_metrics={k: dict(v) for k, v in strategy_metrics.items()},
                iteration_equity=float(iter_state["equity"]),
            )
        )


def _on_iteration_event(event: IterationEvent, bus: EventBus, runtime: PipelineRuntime) -> None:
    market = runtime.regime_detector.detect(runtime.recent_prices)
    rec = runtime.auto_tuner.recommend(
        current_weights=event.current_weights,
        risk_params=event.risk_params,
        market_conditions=market,
        outcomes=event.outcomes,
        strategy_metrics=event.strategy_metrics,
    )

    runtime.feedback.strategy_weights = dict(rec["strategy_weights"])
    for strategy, weight in runtime.feedback.strategy_weights.items():
        runtime.feedback.strategy_enabled[strategy] = bool(weight > 0.0)

    risk_params = dict(rec["risk_params"])
    runtime.risk_engine.config.base_trade_size = float(risk_params["base_trade_size"])
    runtime.risk_engine.config.max_position_size = float(risk_params["max_position_size"])
    runtime.risk_engine.config.cooldown_seconds = int(risk_params["cooldown_seconds"])

    bus.publish(
        ExperimentLogEvent(
            run_id=event.run_id,
            iteration=event.iteration,
            parameter_set={
                "weights": dict(runtime.feedback.strategy_weights),
                "base_trade_size": float(runtime.risk_engine.config.base_trade_size),
                "max_position_size": float(runtime.risk_engine.config.max_position_size),
                "cooldown_seconds": int(runtime.risk_engine.config.cooldown_seconds),
            },
            market_conditions=dict(rec["market_conditions"]),
            outcomes=dict(event.outcomes),
            recommendations=dict(rec),
            iteration_equity=float(event.iteration_equity),
        )
    )


def _on_experiment_log_event(event: ExperimentLogEvent, bus: EventBus, runtime: PipelineRuntime) -> None:
    runtime.iteration_logger.log_experiment(
        run_id=event.run_id,
        iteration=event.iteration,
        parameter_set=event.parameter_set,
        market_conditions=event.market_conditions,
        outcomes=event.outcomes,
        recommendations=event.recommendations,
    )
    runtime.iteration_index += 1
    runtime.last_iteration_equity = float(event.iteration_equity)


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
        features = FeatureEngine(ma_window=20, long_ma_window=50, vol_window=20, momentum_window=10, debug=False)
        iteration_logger = ExperimentLogger(db_path=str(db_dir / "iteration_history.db"))
        runtime = PipelineRuntime(
            portfolio=portfolio,
            execution=execution,
            logger=logger,
            perf=perf,
            feedback=feedback,
            risk_engine=risk_engine,
            features=features,
            regime_detector=RegimeDetector(window=40),
            auto_tuner=AutoTuner(),
            iteration_logger=iteration_logger,
            strategy_registry=default_strategy_registry(),
            confidence_threshold=0.35,
            run_id=datetime.now(timezone.utc).strftime("paper_%Y%m%d_%H%M%S"),
            last_iteration_equity=100000.0,
        )

        bus = EventBus()
        dispatcher = EventDispatcher()
        dispatcher.register(MarketEvent, _on_market_event)
        dispatcher.register(SignalEvent, _on_signal_event)
        dispatcher.register(OrderEvent, _on_order_event)
        dispatcher.register(FillEvent, _on_fill_event)
        dispatcher.register(IterationEvent, _on_iteration_event)
        dispatcher.register(ExperimentLogEvent, _on_experiment_log_event)

        feed = DataFeed(symbol="SIM", mode="simulated", seed=seed, start_price=100.0)

        for payload in feed.start_feed(tick_count=num_ticks):
            ts = datetime.fromisoformat(str(payload["timestamp"]))
            tick = Tick(symbol="SIM", price=float(payload["mid_price"]), timestamp=ts, volume=1.0)
            bus.publish(MarketEvent(tick=tick))

            while len(bus) > 0:
                next_event = bus.consume()
                if next_event is None:
                    break
                dispatcher.dispatch(next_event, bus, runtime)

        final_state = runtime.portfolio.get_portfolio_state()
        metrics = runtime.perf.compute_metrics(latest_total_pnl=float(final_state["total_pnl"]))
        runtime.logger.log_performance_metrics(metrics)
        feed.stop_feed()

    summary = {
        "executed_trades": float(runtime.executed_trades),
        "total_pnl": float(metrics["total_pnl"]),
        "win_rate": float(metrics["win_rate"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "sharpe_ratio": float(metrics["sharpe_ratio"]),
        "strategy_weights": {k: float(v) for k, v in runtime.feedback.strategy_weights.items()},
        "iteration_updates": float(runtime.iteration_index),
        "adaptive_base_trade_size": float(runtime.risk_engine.config.base_trade_size),
        "adaptive_max_position_size": float(runtime.risk_engine.config.max_position_size),
        "adaptive_cooldown_seconds": float(runtime.risk_engine.config.cooldown_seconds),
    }
    return summary


def main() -> None:
    summary = run_paper_trading_session(num_ticks=200, seed=42)
    print(f"Paper session complete: {summary}")


if __name__ == "__main__":
    main()
