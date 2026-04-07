"""Central event bus and dispatch primitives for event-driven pipelines."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, DefaultDict, Dict, Generic, List, Optional, Type, TypeVar

from data_feed import Tick


@dataclass(frozen=True)
class MarketEvent:
    tick: Tick


@dataclass(frozen=True)
class SignalEvent:
    strategy: str
    trade: Dict[str, Any]
    risk_state: Dict[str, Any]


@dataclass(frozen=True)
class OrderEvent:
    strategy: str
    trade: Dict[str, Any]
    reason: str = "approved"


@dataclass(frozen=True)
class FillEvent:
    strategy: str
    trade: Dict[str, Any]
    result: Dict[str, Any]


@dataclass(frozen=True)
class IterationEvent:
    run_id: str
    iteration: int
    current_weights: Dict[str, float]
    risk_params: Dict[str, float]
    market_conditions: Dict[str, Any]
    outcomes: Dict[str, float]
    strategy_metrics: Dict[str, Dict[str, float]]
    iteration_equity: float


@dataclass(frozen=True)
class ExperimentLogEvent:
    run_id: str
    iteration: int
    parameter_set: Dict[str, Any]
    market_conditions: Dict[str, Any]
    outcomes: Dict[str, Any]
    recommendations: Dict[str, Any]
    iteration_equity: float


Event = MarketEvent | SignalEvent | OrderEvent | FillEvent | IterationEvent | ExperimentLogEvent

E = TypeVar("E", bound=Event)
Handler = Callable[[Event, "EventBus", Any], None]


class EventBus:
    """Simple in-memory FIFO event bus."""

    def __init__(self) -> None:
        self._queue: Deque[Event] = deque()

    def publish(self, event: Event) -> None:
        self._queue.append(event)

    def consume(self) -> Optional[Event]:
        if not self._queue:
            return None
        return self._queue.popleft()

    def __len__(self) -> int:
        return len(self._queue)


class EventDispatcher:
    """Routes events to registered handlers by concrete event type."""

    def __init__(self) -> None:
        self._handlers: DefaultDict[Type[Event], List[Handler]] = defaultdict(list)

    def register(self, event_type: Type[E], handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def dispatch(self, event: Event, bus: EventBus, context: Any) -> None:
        for handler in self._handlers.get(type(event), []):
            handler(event, bus, context)
