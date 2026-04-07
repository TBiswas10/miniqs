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


class KillSwitchRequest(BaseModel):
    engage: bool


class ReplayQuery(BaseModel):
    limit: int = 200
    event_type: Optional[EventType] = None
