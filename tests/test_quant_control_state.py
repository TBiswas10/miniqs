from __future__ import annotations

import tempfile
from pathlib import Path

from src.miniqs.risk import quant_control_state as control_state


def test_control_state_save_and_load_round_trip() -> None:
    original_path = control_state.CONTROL_STATE_PATH
    with tempfile.TemporaryDirectory() as tmp:
        control_state.CONTROL_STATE_PATH = Path(tmp) / "terminal_control_state.json"
        try:
            saved = control_state.save_control_state(
                {
                    "trading_enabled": False,
                    "asset": {"symbol": "SPY", "asset_type": "equity", "market_hours": {"open": "09:30", "close": "16:00", "timezone": "America/New_York"}, "trading_fees": 0.0001},
                }
            )
            loaded = control_state.load_control_state()
        finally:
            control_state.CONTROL_STATE_PATH = original_path

    assert saved["asset"]["symbol"] == "SPY"
    assert loaded["asset"]["symbol"] == "SPY"
    assert loaded["trading_enabled"] is False