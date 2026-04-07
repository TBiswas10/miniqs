from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

CONTROL_STATE_PATH = Path(__file__).resolve().parent / "logs" / "terminal_control_state.json"

DEFAULT_CONTROL_STATE: Dict[str, Any] = {
    "trading_enabled": True,
    "kill_switch": False,
    "strategies": {
        "mean_reversion": True,
        "momentum": True,
        "volatility_breakout": True,
    },
    "risk": {
        "confidence_threshold": 0.60,
        "max_position_size": 0.10,
        "max_daily_loss": 500.0,
    },
}


def _merge_state(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_state(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def load_control_state() -> Dict[str, Any]:
    if not CONTROL_STATE_PATH.exists():
        return json.loads(json.dumps(DEFAULT_CONTROL_STATE))
    try:
        payload = json.loads(CONTROL_STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return json.loads(json.dumps(DEFAULT_CONTROL_STATE))
        return _merge_state(json.loads(json.dumps(DEFAULT_CONTROL_STATE)), payload)
    except Exception:
        return json.loads(json.dumps(DEFAULT_CONTROL_STATE))


def save_control_state(state: Dict[str, Any]) -> Dict[str, Any]:
    CONTROL_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    normalized = _merge_state(json.loads(json.dumps(DEFAULT_CONTROL_STATE)), state)
    CONTROL_STATE_PATH.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    return normalized
