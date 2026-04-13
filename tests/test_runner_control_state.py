from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from src.miniqs.runners import paper as runner
from src.miniqs.config.alpaca import AlpacaConfig
from src.miniqs.data.data_feed import Tick
from src.miniqs.engine.event_bus import EventBus, OrderEvent
from src.miniqs.strategies import StrategySignal


class _StubFeatureEngine:
    def update(self, _tick: Tick) -> object:
        return object()


async def _single_tick_stream(cfg: AlpacaConfig, on_connection_event=None):
    if on_connection_event is not None:
        on_connection_event("market_data", "connected")
    yield Tick(
        symbol=cfg.symbols[0].upper(),
        price=100.0,
        timestamp=datetime.now(timezone.utc),
        volume=1.0,
    )


async def _noop_trading_listener(*_args, **_kwargs):
    return None


class TestRunnerControlState(unittest.TestCase):
    def test_runner_passes_trading_api_version_to_alpaca_client(self) -> None:
        traces = []
        captured = {}

        class FakeClient:
            def __init__(self, key_id, secret, base_url, trading_api_version="v2"):
                captured["key_id"] = key_id
                captured["secret"] = secret
                captured["base_url"] = base_url
                captured["trading_api_version"] = trading_api_version

            def get_account(self):
                return {"cash": 100000.0}

        class FakeExecutionEngine:
            def __init__(self, *args, **kwargs):
                self.calls = 0

            def execute_trade(self, trade):
                self.calls += 1
                return {
                    "action": trade["action"],
                    "size": trade["size"],
                    "price": trade["price"],
                    "timestamp": trade["timestamp"],
                    "alpaca_order_id": "test-order-id",
                    "realized_pnl_trade": 0.0,
                }

        cfg = AlpacaConfig(
            api_key_id="key",
            api_secret_key="secret",
            trading_api_version="v2",
            symbols=["BTC/USD"],
            sync_initial_cash_from_alpaca=False,
            db_dir=tempfile.mkdtemp(prefix="runner_version_test_"),
            status_heartbeat_ticks=0,
        )

        with patch("src.miniqs.runners.paper._feature_engines", return_value={"BTC/USD": _StubFeatureEngine()}), patch(
            "src.miniqs.runners.paper.stream_alpaca_ticks",
            side_effect=lambda *_args, **_kwargs: _single_tick_stream(cfg, _kwargs.get("on_connection_event")),
        ), patch(
            "src.miniqs.runners.paper.generate_weighted_signals",
            return_value={
                "mean_reversion": StrategySignal("mean_reversion", "buy", 0.9, "test_signal"),
                "momentum": StrategySignal("momentum", "buy", 0.8, "test_signal"),
                "volatility_breakout": StrategySignal("volatility_breakout", "buy", 0.7, "test_signal"),
            },
        ), patch("src.miniqs.runners.paper.run_trading_stream_listener", side_effect=_noop_trading_listener), patch(
            "src.miniqs.runners.paper.load_control_state",
            return_value={
                "trading_enabled": False,
                "kill_switch": False,
                "src.miniqs.strategies": {"mean_reversion": True, "momentum": True, "volatility_breakout": True},
                "src.miniqs.risk": {"confidence_threshold": 0.35, "max_position_size": 5.0, "max_daily_loss": 500.0},
            },
        ), patch("src.miniqs.runners.paper.AlpacaPaperClient", new=FakeClient), patch(
            "src.miniqs.runners.paper.AlpacaPaperExecutionEngine", new=FakeExecutionEngine
        ), patch("src.miniqs.runners.paper._write_dashboard", return_value=None), patch(
            "src.miniqs.runners.paper._emit_heartbeat", return_value=None
        ), patch("src.miniqs.runners.paper._write_brain_trace", side_effect=lambda _cfg, row: traces.append(row)):
            asyncio.run(runner.run_alpaca_paper_session(cfg))

        self.assertEqual(captured["trading_api_version"], "v2")

    def test_trading_disabled_blocks_execution(self) -> None:
        created_exec_instances = []
        traces = []

        class FakeExecutionEngine:
            def __init__(self, *args, **kwargs):
                self.calls = 0
                created_exec_instances.append(self)

            def execute_trade(self, trade):
                self.calls += 1
                return {
                    "action": trade["action"],
                    "size": trade["size"],
                    "price": trade["price"],
                    "timestamp": trade["timestamp"],
                    "alpaca_order_id": "test-order-id",
                    "realized_pnl_trade": 0.0,
                }

        control_state = {
            "trading_enabled": False,
            "kill_switch": False,
            "src.miniqs.strategies": {"mean_reversion": True, "momentum": True, "volatility_breakout": True},
            "src.miniqs.risk": {
                "confidence_threshold": 0.35,
                "max_position_size": 5.0,
                "max_daily_loss": 500.0,
            },
        }

        cfg = AlpacaConfig(
            api_key_id="key",
            api_secret_key="secret",
            symbols=["SPY"],
            sync_initial_cash_from_alpaca=False,
            db_dir=tempfile.mkdtemp(prefix="runner_control_test_"),
            status_heartbeat_ticks=0,
        )

        with patch("src.miniqs.runners.paper._feature_engines", return_value={"SPY": _StubFeatureEngine()}), patch(
            "src.miniqs.runners.paper.stream_alpaca_ticks",
            side_effect=lambda *_args, **_kwargs: _single_tick_stream(cfg, _kwargs.get("on_connection_event")),
        ), patch(
            "src.miniqs.runners.paper.generate_weighted_signals",
            return_value={
                "mean_reversion": StrategySignal("mean_reversion", "buy", 0.9, "test_signal"),
                "momentum": StrategySignal("momentum", "buy", 0.8, "test_signal"),
                "volatility_breakout": StrategySignal("volatility_breakout", "buy", 0.7, "test_signal"),
            },
        ), patch("src.miniqs.runners.paper.run_trading_stream_listener", side_effect=_noop_trading_listener), patch(
            "src.miniqs.runners.paper.load_control_state", return_value=control_state
        ), patch("src.miniqs.runners.paper.AlpacaPaperExecutionEngine", new=FakeExecutionEngine), patch(
            "src.miniqs.runners.paper._write_dashboard", return_value=None
        ), patch("src.miniqs.runners.paper._emit_heartbeat", return_value=None), patch(
            "src.miniqs.runners.paper._write_brain_trace", side_effect=lambda _cfg, row: traces.append(row)
        ):
            summary = asyncio.run(runner.run_alpaca_paper_session(cfg))

        self.assertEqual(summary["ticks_processed"], 1.0)
        self.assertEqual(summary["executed_trades"], 0.0)
        self.assertTrue(created_exec_instances)
        self.assertEqual(created_exec_instances[0].calls, 0)

        stopped_rows = [r for r in traces if r.get("stage") == "trading_stopped"]
        self.assertTrue(stopped_rows)
        self.assertEqual(stopped_rows[0].get("detail"), "trading_disabled")
        evaluator = stopped_rows[0].get("evaluator", {})
        self.assertIsInstance(evaluator, dict)
        self.assertIn("buy_score", evaluator)
        self.assertIn("sell_score", evaluator)
        self.assertIn("normalized_contributions", evaluator)
        chosen = stopped_rows[0].get("chosen", {})
        self.assertEqual(chosen.get("action"), "buy")
        self.assertGreaterEqual(float(evaluator.get("buy_score", 0.0)), float(evaluator.get("sell_score", 0.0)))

    def test_no_signal_row_includes_evaluator_telemetry(self) -> None:
        traces = []

        class FakeExecutionEngine:
            def __init__(self, *args, **kwargs):
                self.calls = 0

            def execute_trade(self, trade):
                self.calls += 1
                return {
                    "action": trade["action"],
                    "size": trade["size"],
                    "price": trade["price"],
                    "timestamp": trade["timestamp"],
                    "alpaca_order_id": "test-order-id",
                    "realized_pnl_trade": 0.0,
                }

        control_state = {
            "trading_enabled": True,
            "kill_switch": False,
            "src.miniqs.strategies": {"mean_reversion": True, "momentum": True, "volatility_breakout": True},
            "src.miniqs.risk": {
                "confidence_threshold": 0.95,
            },
        }

        cfg = AlpacaConfig(
            api_key_id="key",
            api_secret_key="secret",
            symbols=["SPY"],
            sync_initial_cash_from_alpaca=False,
            db_dir=tempfile.mkdtemp(prefix="runner_control_test_no_signal_"),
            status_heartbeat_ticks=0,
        )

        with patch("src.miniqs.runners.paper._feature_engines", return_value={"SPY": _StubFeatureEngine()}), patch(
            "src.miniqs.runners.paper.stream_alpaca_ticks",
            side_effect=lambda *_args, **_kwargs: _single_tick_stream(cfg, _kwargs.get("on_connection_event")),
        ), patch(
            "src.miniqs.runners.paper.generate_weighted_signals",
            return_value={
                "mean_reversion": StrategySignal("mean_reversion", "buy", 0.4, "test_signal"),
                "momentum": StrategySignal("momentum", "sell", 0.3, "test_signal"),
                "volatility_breakout": StrategySignal("volatility_breakout", "buy", 0.25, "test_signal"),
            },
        ), patch("src.miniqs.runners.paper.run_trading_stream_listener", side_effect=_noop_trading_listener), patch(
            "src.miniqs.runners.paper.load_control_state", return_value=control_state
        ), patch("src.miniqs.runners.paper.AlpacaPaperExecutionEngine", new=FakeExecutionEngine), patch(
            "src.miniqs.runners.paper._write_dashboard", return_value=None
        ), patch("src.miniqs.runners.paper._emit_heartbeat", return_value=None), patch(
            "src.miniqs.runners.paper._write_brain_trace", side_effect=lambda _cfg, row: traces.append(row)
        ):
            summary = asyncio.run(runner.run_alpaca_paper_session(cfg))

        self.assertEqual(summary["executed_trades"], 0.0)
        no_signal_rows = [r for r in traces if r.get("stage") == "no_signal"]
        self.assertTrue(no_signal_rows)
        row = no_signal_rows[0]
        self.assertIsNone(row.get("chosen"))
        evaluator = row.get("evaluator", {})
        self.assertIsInstance(evaluator, dict)
        self.assertIn("buy_score", evaluator)
        self.assertIn("sell_score", evaluator)
        self.assertIn("normalized_contributions", evaluator)
        self.assertIn("applied_threshold", evaluator)
        self.assertIn("applied_profile", evaluator)

    def test_order_event_pre_submit_market_hours_guard_blocks_outside_session(self) -> None:
        class FakeExecutionEngine:
            def __init__(self):
                self.calls = 0

            def execute_trade(self, _trade):
                self.calls += 1
                return {
                    "action": "buy",
                    "size": 1.0,
                    "price": 100.0,
                    "timestamp": "2026-01-04T15:00:00+00:00",
                    "alpaca_order_id": "test-order-id",
                    "realized_pnl_trade": 0.0,
                }

        runtime = runner.AlpacaRuntime(
            cfg=AlpacaConfig(api_key_id="k", api_secret_key="s", symbols=["SPY"], sync_initial_cash_from_alpaca=False),
            logger=unittest.mock.MagicMock(),
            perf=unittest.mock.MagicMock(),
            feedback=runner.FeedbackLoop(),
            portfolio=unittest.mock.MagicMock(),
            alpaca_exec=FakeExecutionEngine(),
            strategy_registry=runner.default_strategy_registry(),
            engines={"SPY": _StubFeatureEngine()},
            primary="SPY",
            asset={"symbol": "SPY", "asset_type": "equity", "market_hours": {"open": "09:30", "close": "16:00", "timezone": "America/New_York"}, "trading_fees": 0.0001},
            initial_equity=100000.0,
        )

        with patch("src.miniqs.runners.paper.load_control_state", return_value={
            "trading_enabled": True,
            "kill_switch": False,
            "asset": {"symbol": "SPY", "asset_type": "equity", "market_hours": {"open": "09:30", "close": "16:00", "timezone": "America/New_York"}, "trading_fees": 0.0001},
        }):
            runner._on_order_event(
                OrderEvent(strategy="momentum", trade={"action": "buy", "size": 1.0, "price": 100.0, "timestamp": "2026-01-04T15:00:00+00:00", "symbol": "SPY"}),
                EventBus(),
                runtime,
            )

        self.assertEqual(runtime.alpaca_exec.calls, 0)

    def test_order_event_failure_burst_engages_kill_switch(self) -> None:
        class FakeExecutionEngine:
            def execute_trade(self, _trade):
                raise RuntimeError("forced failure")

        runtime = runner.AlpacaRuntime(
            cfg=AlpacaConfig(api_key_id="k", api_secret_key="s", symbols=["BTC/USD"], sync_initial_cash_from_alpaca=False),
            logger=unittest.mock.MagicMock(),
            perf=unittest.mock.MagicMock(),
            feedback=runner.FeedbackLoop(),
            portfolio=unittest.mock.MagicMock(),
            alpaca_exec=FakeExecutionEngine(),
            strategy_registry=runner.default_strategy_registry(),
            engines={"BTC/USD": _StubFeatureEngine()},
            primary="BTC/USD",
            asset={"symbol": "BTC/USD", "asset_type": "crypto", "market_hours": None, "trading_fees": 0.001},
            initial_equity=100000.0,
        )

        with patch("src.miniqs.runners.paper.load_control_state", return_value={"trading_enabled": True, "kill_switch": False, "asset": {"symbol": "BTC/USD", "asset_type": "crypto", "market_hours": None, "trading_fees": 0.001}}), patch(
            "src.miniqs.runners.paper.save_control_state", side_effect=lambda s: s
        ) as save_state:
            for _ in range(3):
                runner._on_order_event(
                    OrderEvent(strategy="momentum", trade={"action": "buy", "size": 0.01, "price": 100.0, "timestamp": "2026-01-05T15:00:00+00:00", "symbol": "BTC/USD"}),
                    EventBus(),
                    runtime,
                )

        self.assertGreaterEqual(runtime.order_error_count, 3)
        self.assertTrue(save_state.called)


if __name__ == "__main__":
    unittest.main()
