#!/usr/bin/env python3
import sys
import asyncio
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch
sys.path.insert(0, r'c:\Users\tirth\Desktop\Coding\miniqs')

from src.miniqs.runners import paper as runner
from src.miniqs.config.alpaca import AlpacaConfig
from src.miniqs.data.data_feed import Tick
from src.miniqs.strategies import StrategySignal

class _StubFeatureEngine:
    def update(self, _tick: Tick) -> object:
        return object()

async def _single_tick_stream(cfg: AlpacaConfig, on_connection_event=None):
    if on_connection_event is not None:
        on_connection_event("market_data", "connected")
    print("Yielding single tick...")
    yield Tick(
        symbol=cfg.symbols[0].upper(),
        price=100.0,
        timestamp=datetime.now(timezone.utc),
        volume=1.0,
    )
    print("Generator finished")

async def _noop_trading_listener(*_args, **_kwargs):
    print("Noop listener called")
    return None

print("Starting test...")

cfg = AlpacaConfig(
    api_key_id="key",
    api_secret_key="secret",
    trading_api_version="v2",
    symbols=["BTC/USD"],
    sync_initial_cash_from_alpaca=False,
    db_dir=tempfile.mkdtemp(prefix="runner_version_test_"),
    status_heartbeat_ticks=0,
)

print(f"Config created, db_dir={cfg.db_dir}")

patches = [
    patch("src.miniqs.runners.paper._feature_engines", return_value={"BTC/USD": _StubFeatureEngine()}),
    patch(
        "src.miniqs.data.stream.stream_alpaca_ticks",
        side_effect=lambda *_args, **_kwargs: _single_tick_stream(cfg, _kwargs.get("on_connection_event")),
    ),
    patch("src.miniqs.runners.paper.run_trading_stream_listener", side_effect=_noop_trading_listener),
    patch(
        "src.miniqs.signals.strategies.mean_reversion_signal",
        return_value=StrategySignal("mean_reversion", "buy", 0.9, "test_signal"),
    ),
    patch(
        "src.miniqs.signals.strategies.momentum_signal",
        return_value=StrategySignal("momentum", "buy", 0.8, "test_signal"),
    ),
    patch(
        "src.miniqs.signals.strategies.volatility_breakout_signal",
        return_value=StrategySignal("volatility_breakout", "buy", 0.7, "test_signal"),
    ),
    patch("src.miniqs.runners.paper.load_control_state", return_value={
        "trading_enabled": False,
        "kill_switch": False,
        "src.miniqs.strategies": {"mean_reversion": True, "momentum": True, "volatility_breakout": True},
        "src.miniqs.risk": {"confidence_threshold": 0.35, "max_position_size": 5.0, "max_daily_loss": 500.0},
    }),
    patch("src.miniqs.runners.paper.AlpacaPaperClient", new=type("FakeClient", (), {
        "__init__": lambda self, *args, **kwargs: None,
        "get_account": lambda self: {"cash": 100000.0},
    })),
    patch("src.miniqs.execution.paper.AlpacaPaperExecutionEngine", new=type("FakeExecutionEngine", (), {
        "__init__": lambda self, *args, **kwargs: None,
        "execute_trade": lambda self, trade: {
            "action": trade["action"],
            "size": trade["size"],
            "price": trade["price"],
            "timestamp": trade["timestamp"],
            "alpaca_order_id": "test-order-id",
            "realized_pnl_trade": 0.0,
        },
    })),
    patch("src.miniqs.runners.paper._write_dashboard", return_value=None),
    patch("src.miniqs.runners.paper._emit_heartbeat", return_value=None),
    patch("src.miniqs.runners.paper._write_brain_trace", return_value=None),
]

print("Applying patches...")
with patches[0]:
    with patches[1]:
        with patches[2]:
            with patches[3]:
                with patches[4]:
                    with patches[5]:
                        with patches[6]:
                            with patches[7]:
                                with patches[8]:
                                    with patches[9]:
                                        with patches[10]:
                                            with patches[11]:
                                                print("Running async session...")
                                                try:
                                                    result = asyncio.run(runner.run_alpaca_paper_session(cfg))
                                                    print(f"Result: {result}")
                                                except Exception as e:
                                                    print(f"Error: {e}")
                                                    import traceback
                                                    traceback.print_exc()

print("Done!")
