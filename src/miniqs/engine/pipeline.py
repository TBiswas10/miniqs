"""Main orchestrated pipeline for trading sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, cast
from datetime import datetime, timezone

from src.miniqs.engine.event_bus import (
    EventBus,
    MarketEvent,
    SignalEvent,
    OrderEvent,
    FillEvent,
    IterationEvent,
    ExperimentLogEvent,
    HealthReportEvent,
)
from src.miniqs.risk.portfolio import Portfolio
from src.miniqs.execution import ExecutionEngine
from src.miniqs.utils.logger import QuantLogger
from src.miniqs.utils.performance import PerformanceTracker
from src.miniqs.engine.feedback import FeedbackLoop
from src.miniqs.risk.engine import RiskEngine
from src.miniqs.engine.feature import FeatureEngine
from src.miniqs.engine.iteration import AutoTuner, ExperimentLogger, RegimeDetector
from src.miniqs.agents.alpha_copilot import AlphaCopilot
from src.miniqs.signals.strategies import StrategyRegistry, generate_weighted_signals
from src.miniqs.signals.evaluator import emit_signal_event, evaluate_signals_v2


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
    copilot: AlphaCopilot
    recent_prices: List[float] = field(default_factory=list)
    iteration_index: int = 0
    last_iteration_equity: float = 100000.0
    last_trade_timestamp: Optional[str] = None
    executed_trades: int = 0
    last_report_ts: Optional[datetime] = None
    report_interval_seconds: float = 1800.0  # 30 minutes (Hyper-Scalp)


def on_market_event(event: MarketEvent, bus: EventBus, runtime: PipelineRuntime) -> None:
    tick = event.tick
    runtime.recent_prices.append(float(tick.price))
    runtime.recent_prices = runtime.recent_prices[-200:]

    snap = runtime.features.update(tick)
    runtime.portfolio.update_pnl(tick.price)
    state = runtime.portfolio.get_portfolio_state()
    runtime.perf.record_equity(float(state["equity"]))
    runtime.logger.log_portfolio_snapshot(state)

    # Periodic Health Report logic
    now_ts = tick.timestamp
    if runtime.last_report_ts is None:
        runtime.last_report_ts = now_ts
    
    if (now_ts - runtime.last_report_ts).total_seconds() >= runtime.report_interval_seconds:
        report = runtime.copilot.generate_daily_report()
        bus.publish(HealthReportEvent(run_id=runtime.run_id, report=report))
        runtime.last_report_ts = now_ts
        runtime.logger.log_ws_event("pipeline", "Station health report generated and published.")
        
        # Aggressive maintenance for 10-day run
        runtime.logger.purge_old_data(hours=24)
        runtime.logger.vacuum()

    if snap is None:
        return

    weights = runtime.feedback.strategy_weights
    signals = generate_weighted_signals(
        features=snap,
        registry=runtime.strategy_registry,
        weights=weights,
        enabled={name: runtime.feedback.is_enabled(name) for name in weights},
        params={
            "mean_reversion": {"entry_threshold": 0.0005, "rsi_oversold": 45.0, "rsi_overbought": 55.0},
            "momentum": {"momentum_threshold": 0.0002, "macd_confirmation": False},
            "volatility_breakout": {"breakout_factor": 1.1, "use_atr_threshold": False},
            "trend_robust": {"rsi_oversold": 45.0, "rsi_overbought": 55.0, "min_trend_gap": 0.0001},
            "hyper_v5": {"sensitivity": 0.0001, "rsi_floor": 20.0, "rsi_ceiling": 80.0},
        },
    )
    
    for signal in signals.values():
        runtime.logger.log_signal(signal.strategy, signal.action, signal.confidence, signal.reason)

    chosen = evaluate_signals_v2(
        list(signals.values()),
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
        "rsi": float(getattr(snap, "rsi", 50.0)),
        "macd": float(getattr(snap, "macd", 0.0)),
    }
    emit_signal_event(bus=bus, chosen=chosen, trade=trade, risk_state=risk_state)


def on_signal_event(event: SignalEvent, bus: EventBus, runtime: PipelineRuntime) -> None:
    allow, reason, adjusted_trade, _ = runtime.risk_engine.assess_trade(event.trade, event.risk_state)
    if not allow:
        runtime.logger.log_risk_block(reason, str(event.trade))
        if "strategy_kill_switch" in reason:
            runtime.feedback.strategy_enabled[event.strategy] = False
            runtime.feedback.strategy_weights[event.strategy] = 0.0
        return
    bus.publish(OrderEvent(strategy=event.strategy, trade=adjusted_trade, reason=reason))


def on_order_event(event: OrderEvent, bus: EventBus, runtime: PipelineRuntime) -> None:
    result = runtime.execution.execute_trade(event.trade)
    bus.publish(FillEvent(strategy=event.strategy, trade=event.trade, result=result))


def on_fill_event(event: FillEvent, bus: EventBus, runtime: PipelineRuntime) -> None:
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
        latest_feats = runtime.features.get_latest_features() or {}
        market = runtime.regime_detector.detect(
            runtime.recent_prices,
            rsi=float(latest_feats.get("rsi", 50.0)),
            macd=float(latest_feats.get("macd", 0.0)),
            macd_signal=float(latest_feats.get("macd_signal", 0.0)),
        )
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


def on_iteration_event(event: IterationEvent, bus: EventBus, runtime: PipelineRuntime) -> None:
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


def on_experiment_log_event(event: ExperimentLogEvent, bus: EventBus, runtime: PipelineRuntime) -> None:
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
