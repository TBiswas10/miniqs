"""Cleaned entry point for the BTC quant trading system."""

from __future__ import annotations

import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

# Ensure src is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.miniqs.data.data_feed import DataFeed, Tick
from src.miniqs.engine.event_bus import (
    EventBus,
    EventDispatcher,
    ExperimentLogEvent,
    FillEvent,
    IterationEvent,
    MarketEvent,
    OrderEvent,
    SignalEvent,
)
from src.miniqs.execution import ExecutionEngine
from src.miniqs.engine.feature import FeatureEngine
from src.miniqs.engine.feedback import FeedbackLoop
from src.miniqs.engine.pipeline import (
    PipelineRuntime,
    on_market_event,
    on_signal_event,
    on_order_event,
    on_fill_event,
    on_iteration_event,
    on_experiment_log_event,
)
from src.miniqs.engine.iteration import AutoTuner, ExperimentLogger, RegimeDetector
from src.miniqs.agents.alpha_copilot import AlphaCopilot
from src.miniqs.utils.logger import QuantLogger
from src.miniqs.utils.performance import PerformanceTracker
from src.miniqs.risk.portfolio import Portfolio
from src.miniqs.risk.engine import RiskConfig, RiskEngine
from src.miniqs.signals.strategies import default_strategy_registry


MODE = os.getenv("MODE", "paper").strip().lower()


def run_btc_trading_session(num_ticks: int = 200, seed: int = 42) -> Dict[str, float]:
    """Run a specialized BTC integration pipeline on simulated or real data."""
    ROOT = Path(__file__).resolve().parents[1]
    db_dir = ROOT / "logs"
    db_dir.mkdir(exist_ok=True)
    
    portfolio = Portfolio(db_path=str(db_dir / "portfolio_btc.db"), initial_cash=100000.0)
    execution = ExecutionEngine(portfolio=portfolio, paper_mode=True, debug=False, realistic_simulation=True)
    logger = QuantLogger(db_path=str(db_dir / "logs_btc.db"))
    iteration_logger = ExperimentLogger(db_path=str(db_dir / "iteration_btc.db"))

    # Startup Reset per User Feedback (Full Clean Slate)
    portfolio.clear_all()
    logger.clear_all()
    iteration_logger.clear_all()
    print("[session] Station cleared: Portfolio, Logs, and Experiments reset.")
    
    perf = PerformanceTracker(initial_equity=100000.0)
    
    feedback = FeedbackLoop(
        strategy_weights={"mean_reversion": 0.4, "momentum": 0.4, "volatility_breakout": 0.2}
    )
    risk_engine = RiskEngine(
        initial_equity=100000.0,
        config=RiskConfig(
            base_trade_size=0.1,
            max_position_size=1.0,
            cooldown_seconds=0,
            max_loss_per_session=100000.0,
            portfolio_drawdown_limit=0.95,
        ),
    )
    features = FeatureEngine(debug=False)
    copilot = AlphaCopilot()
    
    runtime = PipelineRuntime(
        portfolio=portfolio,
        execution=execution,
        logger=logger,
        perf=perf,
        feedback=feedback,
        risk_engine=risk_engine,
        features=features,
        regime_detector=RegimeDetector(),
        auto_tuner=AutoTuner(),
        iteration_logger=iteration_logger,
        strategy_registry=default_strategy_registry(),
        confidence_threshold=0.05,
        run_id=datetime.now(timezone.utc).strftime("btc_%Y%m%d_%H%M%S"),
        copilot=copilot,
        last_iteration_equity=100000.0,
    )

    bus = EventBus()
    dispatcher = EventDispatcher()
    dispatcher.register(MarketEvent, on_market_event)
    dispatcher.register(SignalEvent, on_signal_event)
    dispatcher.register(OrderEvent, on_order_event)
    dispatcher.register(FillEvent, on_fill_event)
    dispatcher.register(IterationEvent, on_iteration_event)
    dispatcher.register(ExperimentLogEvent, on_experiment_log_event)

    # Note: Specialized BTC simulation with realistic pricing
    feed = DataFeed(symbol="BTC/USD", mode="simulated", seed=seed, start_price=65000.0)

    print(f"[session] starting specialized BTC simulation mode={MODE} runtime={runtime.run_id}")

    for payload in feed.start_feed(tick_count=num_ticks):
        ts = datetime.fromisoformat(str(payload["timestamp"]))
        tick = Tick(symbol="BTC/USD", price=float(payload["mid_price"]), timestamp=ts, volume=1.0)
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
        "total_pnl": float(metrics.get("total_pnl", 0.0)),
        "win_rate": float(metrics.get("win_rate", 0.0)),
        "max_drawdown": float(metrics.get("max_drawdown", 0.0)),
        "sharpe_ratio": float(metrics.get("sharpe_ratio", 0.0)),
        "strategy_weights": {k: float(v) for k, v in runtime.feedback.strategy_weights.items()},
    }
    return summary


def main() -> None:
    if MODE in {"paper", "sim"}:
        summary = run_btc_trading_session(num_ticks=200, seed=42)
        print(f"BTC session complete: {summary}")
        return
    if MODE == "broker-paper":
        import asyncio
        from src.miniqs.runners.paper import run_alpaca_paper_session
        summary = asyncio.run(run_alpaca_paper_session())
        print(f"Broker BTC session complete: {summary}")
        return
    if MODE == "live":
        print("Live BTC mode is locked for safety. Use broker-paper for now.")
        return
    raise ValueError(f"Unsupported MODE={MODE!r}")


if __name__ == "__main__":
    main()
