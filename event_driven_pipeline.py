"""Event-driven paper trading pipeline.

Pipeline stages (decoupled by asyncio queues):
market data -> strategy evaluation -> risk check -> execution
"""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from data_feed import DataFeed, Tick
from execution import ExecutionEngine
from feature_engine import FeatureEngine
from logger import QuantLogger
from main import FeedbackLoop
from performance import PerformanceTracker
from portfolio import Portfolio
from risk_manager import RiskConfig, RiskEngine
from strategies import StrategyRegistry, default_strategy_registry, generate_weighted_signals
from strategy_evaluator import evaluate_signals


@dataclass(frozen=True)
class MarketDataEvent:
    tick: Tick


@dataclass(frozen=True)
class RiskInputEvent:
    trade: Dict[str, Any]
    risk_state: Dict[str, Any]
    strategy: str


@dataclass(frozen=True)
class ExecutionInputEvent:
    trade: Dict[str, Any]
    strategy: str
    risk_reason: str = "allowed"


class _StopSignal:
    pass


STOP = _StopSignal()


class AsyncEventDrivenPipeline:
    """Asynchronous stage workers connected via queues.

    Each stage can progress independently without blocking the others.
    CPU or I/O heavy checks are run with ``asyncio.to_thread``.
    """

    def __init__(
        self,
        num_ticks: int = 200,
        seed: int = 42,
        confidence_threshold: float = 0.35,
        feedback_trade_interval: int = 10,
    ) -> None:
        self.num_ticks = num_ticks
        self.seed = seed
        self.confidence_threshold = confidence_threshold
        self.feedback_trade_interval = feedback_trade_interval

        self.market_q: asyncio.Queue[MarketDataEvent | _StopSignal] = asyncio.Queue(maxsize=512)
        self.risk_q: asyncio.Queue[RiskInputEvent | _StopSignal] = asyncio.Queue(maxsize=512)
        self.exec_q: asyncio.Queue[ExecutionInputEvent | _StopSignal] = asyncio.Queue(maxsize=512)

        self.executed_trades = 0
        self.last_trade_timestamp: str | None = None
        self.risk_engine: RiskEngine | None = None
        self.strategy_registry: StrategyRegistry = default_strategy_registry()

    async def _ingestion_worker(self, feed: DataFeed) -> None:
        stream = feed.stream()
        for _ in range(self.num_ticks):
            tick = next(stream)
            await self.market_q.put(MarketDataEvent(tick=tick))
        await self.market_q.put(STOP)

    async def _strategy_worker(
        self,
        *,
        portfolio: Portfolio,
        perf: PerformanceTracker,
        logger: QuantLogger,
        feedback: FeedbackLoop,
        features: FeatureEngine,
    ) -> None:
        while True:
            event = await self.market_q.get()
            if event is STOP:
                await self.risk_q.put(STOP)
                self.market_q.task_done()
                break

            tick = event.tick
            snap = features.update(tick)
            portfolio.update_pnl(tick.price)
            state = portfolio.get_portfolio_state()
            perf.record_equity(float(state["equity"]))
            logger.log_portfolio_snapshot(state)

            if snap is not None:
                weights = feedback.strategy_weights
                signals = generate_weighted_signals(
                    features=snap,
                    registry=self.strategy_registry,
                    weights=weights,
                    enabled={
                        "mean_reversion": feedback.is_enabled("mean_reversion"),
                        "momentum": feedback.is_enabled("momentum"),
                        "volatility_breakout": feedback.is_enabled("volatility_breakout"),
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

                logger.log_signal(mr.strategy, mr.action, mr.confidence, mr.reason)
                logger.log_signal(mo.strategy, mo.action, mo.confidence, mo.reason)
                logger.log_signal(vb.strategy, vb.action, vb.confidence, vb.reason)

                chosen = evaluate_signals([mr, mo, vb], confidence_threshold=self.confidence_threshold)
                if chosen is not None:
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
                        "last_trade_timestamp": self.last_trade_timestamp,
                        "session_loss": max(0.0, -float(state["total_pnl"])),
                        "max_position_size": 5.0,
                        "cooldown_seconds": 1,
                        "max_loss_per_session": 500.0,
                        "equity": float(state["equity"]),
                        "total_pnl": float(state["total_pnl"]),
                        "market_volatility": float(snap.rolling_volatility),
                        "strategy_weight": float(weights.get(chosen.strategy, 0.0)),
                    }
                    await self.risk_q.put(
                        RiskInputEvent(
                            trade=trade,
                            risk_state=risk_state,
                            strategy=chosen.strategy,
                        )
                    )

            self.market_q.task_done()

    async def _risk_worker(self, logger: QuantLogger, feedback: FeedbackLoop) -> None:
        while True:
            event = await self.risk_q.get()
            if event is STOP:
                await self.exec_q.put(STOP)
                self.risk_q.task_done()
                break

            if self.risk_engine is None:
                raise RuntimeError("risk engine not initialized")

            allow, reason, adjusted_trade, _ = await asyncio.to_thread(
                self.risk_engine.assess_trade,
                event.trade,
                event.risk_state,
            )
            if allow:
                await self.exec_q.put(
                    ExecutionInputEvent(
                        trade=adjusted_trade,
                        strategy=event.strategy,
                        risk_reason=reason,
                    )
                )
            else:
                logger.log_risk_block(reason, str(event.trade))
                if "strategy_kill_switch" in reason:
                    feedback.strategy_enabled[event.strategy] = False
                    feedback.strategy_weights[event.strategy] = 0.0

            self.risk_q.task_done()

    async def _execution_worker(
        self,
        *,
        execution: ExecutionEngine,
        perf: PerformanceTracker,
        feedback: FeedbackLoop,
        logger: QuantLogger,
    ) -> None:
        while True:
            event = await self.exec_q.get()
            if event is STOP:
                self.exec_q.task_done()
                break

            result = await asyncio.to_thread(execution.execute_trade, event.trade)
            self.last_trade_timestamp = str(event.trade["timestamp"])
            self.executed_trades += 1

            logger.log_trade(result, strategy=event.strategy)
            perf.record_trade(float(result["realized_pnl_trade"]))
            perf.record_strategy_trade(event.strategy, float(result["realized_pnl_trade"]))

            if self.risk_engine is not None:
                state = execution.portfolio.get_portfolio_state()
                self.risk_engine.record_execution(
                    strategy=event.strategy,
                    realized_pnl_trade=float(result["realized_pnl_trade"]),
                    equity=float(state["equity"]),
                )
                if self.risk_engine.strategy_kill_switch.get(event.strategy, False):
                    feedback.strategy_enabled[event.strategy] = False
                    feedback.strategy_weights[event.strategy] = 0.0

            if self.executed_trades % self.feedback_trade_interval == 0:
                strategy_metrics = perf.strategy_metrics_for_feedback()
                if strategy_metrics:
                    feedback.update(strategy_metrics, logger=logger)

            self.exec_q.task_done()

    async def run(self) -> Dict[str, float]:
        with tempfile.TemporaryDirectory() as tmp:
            db_dir = Path(tmp)
            portfolio = Portfolio(db_path=str(db_dir / "event_portfolio.db"), initial_cash=100000.0)
            execution = ExecutionEngine(portfolio=portfolio, paper_mode=True, debug=False, realistic_simulation=True)
            logger = QuantLogger(db_path=str(db_dir / "event_logs.db"))
            perf = PerformanceTracker(initial_equity=100000.0)
            feedback = FeedbackLoop(
                strategy_weights={
                    "mean_reversion": 0.4,
                    "momentum": 0.4,
                    "volatility_breakout": 0.2,
                }
            )
            self.risk_engine = RiskEngine(
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
            feed = DataFeed(symbol="SIM", mode="simulated", seed=self.seed, start_price=100.0)
            features = FeatureEngine(ma_window=20, long_ma_window=50, vol_window=20, momentum_window=10, debug=False)

            tasks = [
                asyncio.create_task(self._ingestion_worker(feed)),
                asyncio.create_task(
                    self._strategy_worker(
                        portfolio=portfolio,
                        perf=perf,
                        logger=logger,
                        feedback=feedback,
                        features=features,
                    )
                ),
                asyncio.create_task(self._risk_worker(logger=logger, feedback=feedback)),
                asyncio.create_task(
                    self._execution_worker(
                        execution=execution,
                        perf=perf,
                        feedback=feedback,
                        logger=logger,
                    )
                ),
            ]

            await asyncio.gather(*tasks)

            final_state = portfolio.get_portfolio_state()
            metrics = perf.compute_metrics(latest_total_pnl=float(final_state["total_pnl"]))
            logger.log_performance_metrics(metrics)
            feed.stop_feed()

            return {
                "executed_trades": float(self.executed_trades),
                "total_pnl": float(metrics["total_pnl"]),
                "win_rate": float(metrics["win_rate"]),
                "max_drawdown": float(metrics["max_drawdown"]),
                "sharpe_ratio": float(metrics["sharpe_ratio"]),
                "strategy_weights": {k: float(v) for k, v in feedback.strategy_weights.items()},
            }


def run_event_driven_paper_trading_session(num_ticks: int = 200, seed: int = 42) -> Dict[str, float]:
    """Sync wrapper for the async event-driven pipeline."""
    pipeline = AsyncEventDrivenPipeline(num_ticks=num_ticks, seed=seed)
    return asyncio.run(pipeline.run())


if __name__ == "__main__":
    summary = run_event_driven_paper_trading_session(num_ticks=200, seed=42)
    print(f"Event-driven paper session complete: {summary}")
