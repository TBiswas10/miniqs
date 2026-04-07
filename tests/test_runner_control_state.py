from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import alpaca_paper_runner as runner
from alpaca_config import AlpacaConfig
from data_feed import Tick
from strategies import StrategySignal


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
            "strategies": {"mean_reversion": True, "momentum": True, "volatility_breakout": True},
            "risk": {
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

        with patch("alpaca_paper_runner._feature_engines", return_value={"SPY": _StubFeatureEngine()}), patch(
            "alpaca_paper_runner.stream_alpaca_ticks",
            side_effect=lambda *_args, **_kwargs: _single_tick_stream(cfg, _kwargs.get("on_connection_event")),
        ), patch("alpaca_paper_runner.run_trading_stream_listener", side_effect=_noop_trading_listener), patch(
            "alpaca_paper_runner.mean_reversion_signal",
            return_value=StrategySignal("mean_reversion", "buy", 0.9, "test_signal"),
        ), patch(
            "alpaca_paper_runner.momentum_signal",
            return_value=StrategySignal("momentum", "buy", 0.8, "test_signal"),
        ), patch(
            "alpaca_paper_runner.volatility_breakout_signal",
            return_value=StrategySignal("volatility_breakout", "buy", 0.7, "test_signal"),
        ), patch("alpaca_paper_runner.load_control_state", return_value=control_state), patch(
            "alpaca_paper_runner.AlpacaPaperExecutionEngine", new=FakeExecutionEngine
        ), patch("alpaca_paper_runner._write_dashboard", return_value=None), patch(
            "alpaca_paper_runner._emit_heartbeat", return_value=None
        ), patch(
            "alpaca_paper_runner._write_brain_trace", side_effect=lambda _cfg, row: traces.append(row)
        ):
            summary = asyncio.run(runner.run_alpaca_paper_session(cfg))

        self.assertEqual(summary["ticks_processed"], 1.0)
        self.assertEqual(summary["executed_trades"], 0.0)
        self.assertTrue(created_exec_instances)
        self.assertEqual(created_exec_instances[0].calls, 0)

        stopped_rows = [r for r in traces if r.get("stage") == "trading_stopped"]
        self.assertTrue(stopped_rows)
        self.assertEqual(stopped_rows[0].get("detail"), "trading_disabled")


if __name__ == "__main__":
    unittest.main()
