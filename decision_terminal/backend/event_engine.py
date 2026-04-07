from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set, Tuple

from .event_persistence import EventStore
from .event_schemas import EventMessage


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventEngine:
    def __init__(
        self,
        *,
        trace_path: Path,
        store: EventStore,
        get_control_state: Callable[[], Dict[str, Any]],
        trigger_kill_switch: Callable[[str], Awaitable[None]],
    ) -> None:
        self.trace_path = trace_path
        self.store = store
        self.get_control_state = get_control_state
        self.trigger_kill_switch = trigger_kill_switch

        self._queue: asyncio.Queue[EventMessage] = asyncio.Queue(maxsize=2000)
        self._subscribers: Set[asyncio.Queue[EventMessage]] = set()
        self._tasks: List[asyncio.Task[Any]] = []
        self._running = False

        self._last_offset = 0
        self._last_mtime: Optional[float] = None
        self._peak_equity: Optional[float] = None
        self._session_id = datetime.now(timezone.utc).strftime("session_%Y%m%d_%H%M%S")
        self._order_last_state: Dict[str, str] = {}

        self._latest_portfolio: Dict[str, Any] = {}
        self._latest_order: Dict[str, Any] = {}
        self._latest_signal: Dict[str, Any] = {}
        self._latest_risk: Dict[str, Any] = {}

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._tasks = [
            asyncio.create_task(self._process_loop()),
            asyncio.create_task(self._trace_ingest_loop()),
        ]

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []

    async def emit(self, event: EventMessage) -> None:
        if not event.session_id:
            event.session_id = self._session_id
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            _ = self._queue.get_nowait()
            self._queue.put_nowait(event)

    def subscribe(self) -> asyncio.Queue[EventMessage]:
        q: asyncio.Queue[EventMessage] = asyncio.Queue(maxsize=300)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[EventMessage]) -> None:
        self._subscribers.discard(q)

    def latest_state(self) -> Dict[str, Any]:
        return {
            "signal": dict(self._latest_signal),
            "order": dict(self._latest_order),
            "portfolio": dict(self._latest_portfolio),
            "risk": dict(self._latest_risk),
        }

    async def _process_loop(self) -> None:
        while self._running:
            event = await self._queue.get()
            self.store.persist(event)
            self._update_latest(event)
            await self._apply_risk_guards(event)
            await self._broadcast(event)

    async def _trace_ingest_loop(self) -> None:
        while self._running:
            await self._ingest_trace_once()
            await asyncio.sleep(0.25)

    async def _ingest_trace_once(self) -> None:
        if not self.trace_path.exists():
            return

        lines, next_offset, mtime = await asyncio.to_thread(self._read_new_lines)
        self._last_offset = next_offset
        self._last_mtime = mtime

        for line in lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            for event in self._map_trace_row(row):
                await self.emit(event)

    def _read_new_lines(self) -> Tuple[List[str], int, float]:
        st = os.stat(self.trace_path)
        current_mtime = st.st_mtime

        if self._last_mtime is not None and current_mtime < self._last_mtime:
            self._last_offset = 0

        with self.trace_path.open("r", encoding="utf-8") as handle:
            handle.seek(self._last_offset)
            chunk = handle.read()
            next_offset = handle.tell()

        lines = [ln for ln in chunk.splitlines() if ln.strip()]
        return lines, next_offset, current_mtime

    def _map_trace_row(self, row: Dict[str, Any]) -> List[EventMessage]:
        kind = str(row.get("kind", "")).lower()
        ts = str(row.get("timestamp") or row.get("ts") or _now_iso())
        symbol = str(row.get("symbol") or "BTC/USD")
        events: List[EventMessage] = []

        if kind in {"tick", "market", "market_data"}:
            events.append(
                EventMessage(
                    event_type="market_data",
                    ts=ts,
                    source="trace",
                    symbol=symbol,
                    session_id=self._session_id,
                    payload={
                        "price": float(row.get("price") or row.get("mid_price") or 0.0),
                        "volume": float(row.get("volume") or 0.0),
                    },
                )
            )

        if kind == "decision":
            chosen = row.get("chosen") if isinstance(row.get("chosen"), dict) else {}
            risk = row.get("risk") if isinstance(row.get("risk"), dict) else {}
            strategy = str(chosen.get("strategy") or "none")
            side = str(chosen.get("action") or "HOLD").upper()
            confidence = float(chosen.get("confidence") or 0.0)
            reason = str(chosen.get("reason") or row.get("detail") or "")
            events.append(
                EventMessage(
                    event_type="strategy_signal",
                    ts=ts,
                    source="trace",
                    strategy_id=strategy,
                    symbol=symbol,
                    session_id=self._session_id,
                    payload={
                        "side": side,
                        "confidence": confidence,
                        "reason": reason,
                        "raw": row,
                    },
                )
            )

            equity = float(row.get("equity") or 0.0)
            total_pnl = float(row.get("total_pnl") or 0.0)
            position_size = float(row.get("position_size") or 0.0)
            drawdown = 0.0
            if self._peak_equity is None:
                self._peak_equity = equity
            self._peak_equity = max(self._peak_equity or equity, equity)
            if (self._peak_equity or 0) > 0:
                drawdown = (self._peak_equity - equity)

            events.append(
                EventMessage(
                    event_type="portfolio_update",
                    ts=ts,
                    source="trace",
                    strategy_id=strategy,
                    symbol=symbol,
                    session_id=self._session_id,
                    payload={
                        "equity": equity,
                        "total_pnl": total_pnl,
                        "position_size": position_size,
                        "price": float(row.get("price") or 0.0),
                        "cash": equity - (position_size * float(row.get("price") or 0.0)),
                        "drawdown": drawdown,
                    },
                )
            )

            if risk and not bool(risk.get("allowed", True)):
                events.append(
                    EventMessage(
                        event_type="risk_event",
                        ts=ts,
                        source="trace",
                        strategy_id=strategy,
                        symbol=symbol,
                        session_id=self._session_id,
                        payload={
                            "risk_type": "trade_block",
                            "severity": "warn",
                            "reason": str(risk.get("reason") or "risk blocked"),
                        },
                    )
                )

        if kind in {"trade_update", "order"}:
            strategy = str(row.get("strategy") or "none")
            state = str(row.get("event") or row.get("order_state") or "submitted").lower()
            expected = float(row.get("expected_price") or row.get("price") or 0.0)
            fill = float(row.get("applied_price") or row.get("fill_price") or row.get("price") or 0.0)
            order_id = str(row.get("order_id") or row.get("id") or "")
            for transition_state in self._order_transitions(order_id, state):
                events.append(
                    EventMessage(
                        event_type="order_update",
                        ts=ts,
                        source="trace",
                        strategy_id=strategy,
                        symbol=symbol,
                        session_id=self._session_id,
                        payload={
                            "order_id": order_id,
                            "state": transition_state,
                            "expected_price": expected,
                            "fill_price": fill,
                            "slippage": float(row.get("slippage") or (fill - expected)),
                            "fees": float(row.get("fee") or row.get("fees") or 0.0),
                            "size": float(row.get("filled_size") or row.get("size") or 0.0),
                            "raw": row,
                        },
                    )
                )

        if kind == "connection" and any(x in str(row.get("event", "")).lower() for x in ["fail", "drop", "disconnect"]):
            events.append(
                EventMessage(
                    event_type="risk_event",
                    ts=ts,
                    source="trace",
                    strategy_id="system",
                    symbol=symbol,
                    session_id=self._session_id,
                    payload={
                        "risk_type": "data_feed_failure",
                        "severity": "error",
                        "reason": str(row.get("detail") or row.get("event") or "data feed failure"),
                    },
                )
            )

        return events

    def _order_transitions(self, order_id: str, new_state: str) -> List[str]:
        lifecycle = ["created", "submitted", "partial", "filled", "canceled", "rejected"]
        terminal = {"filled", "canceled", "rejected"}

        if new_state not in lifecycle:
            return [new_state]

        previous = self._order_last_state.get(order_id)
        if previous in terminal:
            return [new_state]

        if previous is None:
            previous = "created"
            self._order_last_state[order_id] = previous
            if new_state == "created":
                return ["created"]

        prev_idx = lifecycle.index(previous)
        new_idx = lifecycle.index(new_state)

        if new_idx <= prev_idx:
            self._order_last_state[order_id] = new_state
            return [new_state]

        transitions = lifecycle[prev_idx + 1 : new_idx + 1]
        self._order_last_state[order_id] = new_state
        return transitions

    async def _broadcast(self, event: EventMessage) -> None:
        stale: List[asyncio.Queue[EventMessage]] = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                stale.append(q)
        for q in stale:
            self._subscribers.discard(q)

    def _update_latest(self, event: EventMessage) -> None:
        payload = {"ts": event.ts, **event.payload}
        if event.event_type == "portfolio_update":
            self._latest_portfolio = payload
        elif event.event_type == "order_update":
            self._latest_order = payload
        elif event.event_type == "strategy_signal":
            self._latest_signal = payload
        elif event.event_type == "risk_event":
            self._latest_risk = payload

    async def _apply_risk_guards(self, event: EventMessage) -> None:
        if event.event_type != "portfolio_update":
            return

        state = self.get_control_state()
        risk = state.get("risk", {})
        max_daily_loss = float(risk.get("max_daily_loss", 500.0) or 500.0)
        pnl = float(event.payload.get("total_pnl", 0.0) or 0.0)
        drawdown = float(event.payload.get("drawdown", 0.0) or 0.0)

        if pnl <= -abs(max_daily_loss):
            await self.emit(
                EventMessage(
                    event_type="risk_event",
                    source="engine",
                    strategy_id="system",
                    symbol=event.symbol,
                    session_id=self._session_id,
                    payload={
                        "risk_type": "abnormal_loss",
                        "severity": "error",
                        "reason": f"PnL breach: {pnl:.2f} <= -{abs(max_daily_loss):.2f}",
                    },
                )
            )
            await self.trigger_kill_switch("abnormal_loss")

        if self._peak_equity and drawdown >= max(0.15 * self._peak_equity, abs(max_daily_loss) * 0.5):
            await self.emit(
                EventMessage(
                    event_type="risk_event",
                    source="engine",
                    strategy_id="system",
                    symbol=event.symbol,
                    session_id=self._session_id,
                    payload={
                        "risk_type": "drawdown_breach",
                        "severity": "error",
                        "reason": f"Drawdown breach: {drawdown:.2f}",
                    },
                )
            )
            await self.trigger_kill_switch("drawdown_breach")
