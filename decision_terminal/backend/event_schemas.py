from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field

EventType = Literal[
    "market_data",
    "strategy_signal",
    "risk_event",
    "order_update",
    "portfolio_update",
]


class EventMessage(BaseModel):
    event_type: EventType
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "engine"
    strategy_id: Optional[str] = None
    symbol: Optional[str] = None
    session_id: str = "default"
    payload: Dict[str, Any] = Field(default_factory=dict)


class StartStopRequest(BaseModel):
    enabled: bool


class StrategyToggleRequest(BaseModel):
    strategy: str
    enabled: bool


class RiskUpdateRequest(BaseModel):
    confidence_threshold: float | None = None
    max_position_size: float | None = None
    max_daily_loss: float | None = None
    risk_per_trade: float | None = None
    daily_loss_limit: float | None = None
    max_exposure: float | None = None
    max_concurrent_positions: int | None = None
    cooldown_seconds: int | None = None
    max_loss_per_session: float | None = None
    portfolio_drawdown_limit: float | None = None
    per_strategy_drawdown_limit: float | None = None
    extreme_loss_kill_switch: float | None = None
    strategy_kill_loss: float | None = None
    vol_target: float | None = None
    vol_floor: float | None = None
    vol_ceiling: float | None = None
    low_vol_multiplier: float | None = None
    high_vol_multiplier: float | None = None
    min_trade_size: float | None = None
    max_trade_size: float | None = None


class KillSwitchRequest(BaseModel):
    engage: bool


class ReplayQuery(BaseModel):
    limit: int = 200
    event_type: Optional[EventType] = None


class ReplayForkRequest(BaseModel):
    input_prices: list[float] | None = None
    config_override: Dict[str, Any] = Field(default_factory=dict)
