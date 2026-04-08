from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Dict

from risk_manager import RiskConfig
from strategies import default_strategy_registry

CONTROL_STATE_PATH = Path(__file__).resolve().parent / "logs" / "terminal_control_state.json"


def _default_strategies() -> Dict[str, bool]:
    try:
        names = list(default_strategy_registry().list_names())
    except Exception:
        names = ["mean_reversion", "momentum", "volatility_breakout"]
    return {name: True for name in names}


def _default_risk() -> Dict[str, float]:
    cfg = asdict(RiskConfig())
    return {
        "confidence_threshold": float(cfg["confidence_threshold"]),
        "max_position_size": float(cfg["max_position_size"]),
        "max_daily_loss": float(cfg["max_loss_per_session"]),
        "risk_per_trade": float(cfg["risk_per_trade"]),
        "daily_loss_limit": float(cfg["daily_loss_limit"]),
        "max_exposure": float(cfg["max_exposure"]),
        "max_concurrent_positions": float(cfg["max_concurrent_positions"]),
        "cooldown_seconds": float(cfg["cooldown_seconds"]),
        "max_loss_per_session": float(cfg["max_loss_per_session"]),
        "portfolio_drawdown_limit": float(cfg["portfolio_drawdown_limit"]),
        "per_strategy_drawdown_limit": float(cfg["per_strategy_drawdown_limit"]),
        "extreme_loss_kill_switch": float(cfg["extreme_loss_kill_switch"]),
        "strategy_kill_loss": float(cfg["strategy_kill_loss"]),
        "vol_target": float(cfg["vol_target"]),
        "vol_floor": float(cfg["vol_floor"]),
        "vol_ceiling": float(cfg["vol_ceiling"]),
        "low_vol_multiplier": float(cfg["low_vol_multiplier"]),
        "high_vol_multiplier": float(cfg["high_vol_multiplier"]),
        "min_trade_size": float(cfg["min_trade_size"]),
        "max_trade_size": float(cfg["max_trade_size"]),
    }

DEFAULT_CONTROL_STATE: Dict[str, Any] = {
    "trading_enabled": True,
    "kill_switch": False,
    "strategies": _default_strategies(),
    "risk": _default_risk(),
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
