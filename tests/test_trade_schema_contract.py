import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import alpaca_paper_runner
import event_driven_pipeline
import main
from data_feed import Tick
from event_bus import EventBus, MarketEvent, SignalEvent
from main import FeedbackLoop
from risk_manager import RiskConfig, RiskEngine
from strategies import StrategySignal, default_strategy_registry


REQUIRED_TRADE_KEYS = {"action", "size", "confidence", "price", "strategy", "symbol"}


class TestTradeSchemaContract(unittest.TestCase):
    def test_main_emits_signal_event_with_required_trade_keys(self) -> None:
        bus = EventBus()

        portfolio = MagicMock()
        portfolio.get_portfolio_state.return_value = {
            "position_size": 0.0,
            "equity": 100000.0,
            "total_pnl": 0.0,
        }

        runtime = main.PipelineRuntime(
            portfolio=portfolio,
            execution=MagicMock(),
            logger=MagicMock(),
            perf=MagicMock(),
            feedback=FeedbackLoop(
                strategy_weights={
                    "mean_reversion": 0.4,
                    "momentum": 0.4,
                    "volatility_breakout": 0.2,
                }
            ),
            risk_engine=RiskEngine(initial_equity=100000.0, config=RiskConfig()),
            features=MagicMock(),
            regime_detector=MagicMock(),
            auto_tuner=MagicMock(),
            iteration_logger=MagicMock(),
            strategy_registry=default_strategy_registry(),
            confidence_threshold=0.35,
            run_id="contract_main",
        )
        runtime.features.update.return_value = SimpleNamespace(rolling_volatility=0.01)

        chosen = StrategySignal(strategy="momentum", action="buy", confidence=0.9, reason="contract")
        fake_signals = {
            "mean_reversion": StrategySignal("mean_reversion", "hold", 0.1, "x"),
            "momentum": chosen,
            "volatility_breakout": StrategySignal("volatility_breakout", "hold", 0.1, "x"),
        }

        tick = Tick(symbol="SIM", price=101.25, timestamp=datetime.now(timezone.utc), volume=1.0)

        with patch("main.generate_weighted_signals", return_value=fake_signals), patch(
            "main.evaluate_signals", return_value=chosen
        ):
            main._on_market_event(MarketEvent(tick=tick), bus, runtime)

        event = bus.consume()
        self.assertIsInstance(event, SignalEvent)
        assert isinstance(event, SignalEvent)
        self.assertTrue(REQUIRED_TRADE_KEYS.issubset(set(event.trade.keys())))

    def test_alpaca_runner_emits_signal_event_with_required_trade_keys(self) -> None:
        bus = EventBus()

        cfg = alpaca_paper_runner.AlpacaConfig(api_key_id="k", api_secret_key="s", symbols=["SPY"])
        runtime = alpaca_paper_runner.AlpacaRuntime(
            cfg=cfg,
            logger=MagicMock(),
            perf=MagicMock(),
            feedback=FeedbackLoop(),
            portfolio=MagicMock(),
            alpaca_exec=MagicMock(),
            strategy_registry=default_strategy_registry(),
            engines={"SPY": MagicMock()},
            primary="SPY",
            initial_equity=100000.0,
        )

        runtime.engines["SPY"].update.return_value = SimpleNamespace(rolling_volatility=0.01)
        runtime.portfolio.get_portfolio_state.return_value = {
            "position_size": 0.0,
            "equity": 100000.0,
            "total_pnl": 0.0,
            "cash": 100000.0,
        }
        runtime.perf.compute_metrics.return_value = {
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
        }

        chosen = StrategySignal(strategy="momentum", action="buy", confidence=0.9, reason="contract")
        fake_signals = {
            "mean_reversion": StrategySignal("mean_reversion", "hold", 0.1, "x"),
            "momentum": chosen,
            "volatility_breakout": StrategySignal("volatility_breakout", "hold", 0.1, "x"),
        }
        tick = Tick(symbol="SPY", price=500.0, timestamp=datetime.now(timezone.utc), volume=1.0)

        with patch("alpaca_paper_runner.generate_weighted_signals", return_value=fake_signals), patch(
            "alpaca_paper_runner.evaluate_signals", return_value=chosen
        ), patch(
            "alpaca_paper_runner.load_control_state",
            return_value={
                "trading_enabled": True,
                "kill_switch": False,
                "risk": {},
                "strategies": {
                    "mean_reversion": True,
                    "momentum": True,
                    "volatility_breakout": True,
                },
            },
        ):
            alpaca_paper_runner._on_market_event(MarketEvent(tick=tick), bus, runtime)

        event = bus.consume()
        self.assertIsInstance(event, SignalEvent)
        assert isinstance(event, SignalEvent)
        self.assertTrue(REQUIRED_TRADE_KEYS.issubset(set(event.trade.keys())))

    def test_async_event_pipeline_trade_payload_includes_symbol(self) -> None:
        pipeline = event_driven_pipeline.AsyncEventDrivenPipeline(num_ticks=1, seed=1)

        portfolio = MagicMock()
        portfolio.get_portfolio_state.return_value = {
            "position_size": 0.0,
            "equity": 100000.0,
            "total_pnl": 0.0,
        }
        perf = MagicMock()
        logger = MagicMock()
        feedback = FeedbackLoop(
            strategy_weights={
                "mean_reversion": 0.4,
                "momentum": 0.4,
                "volatility_breakout": 0.2,
            }
        )
        features = MagicMock()
        features.update.return_value = SimpleNamespace(rolling_volatility=0.01)

        chosen = StrategySignal(strategy="momentum", action="buy", confidence=0.8, reason="contract")
        fake_signals = {
            "mean_reversion": StrategySignal("mean_reversion", "hold", 0.1, "x"),
            "momentum": chosen,
            "volatility_breakout": StrategySignal("volatility_breakout", "hold", 0.1, "x"),
        }

        tick = Tick(symbol="SIM", price=100.0, timestamp=datetime.now(timezone.utc), volume=1.0)

        async def _run_worker() -> None:
            await pipeline.market_q.put(event_driven_pipeline.MarketDataEvent(tick=tick))
            await pipeline.market_q.put(event_driven_pipeline.STOP)
            with patch("event_driven_pipeline.generate_weighted_signals", return_value=fake_signals), patch(
                "event_driven_pipeline.evaluate_signals", return_value=chosen
            ):
                await pipeline._strategy_worker(
                    portfolio=portfolio,
                    perf=perf,
                    logger=logger,
                    feedback=feedback,
                    features=features,
                )

        asyncio.run(_run_worker())

        risk_event = pipeline.risk_q.get_nowait()
        self.assertIsInstance(risk_event, event_driven_pipeline.RiskInputEvent)
        assert isinstance(risk_event, event_driven_pipeline.RiskInputEvent)
        self.assertIn("symbol", risk_event.trade)
        self.assertEqual(risk_event.trade["symbol"], "SIM")


if __name__ == "__main__":
    unittest.main()
