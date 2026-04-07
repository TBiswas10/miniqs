from __future__ import annotations

import asyncio
import json
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .event_engine import EventEngine
from .event_persistence import EventStore
from .event_schemas import EventMessage, KillSwitchRequest, RiskUpdateRequest, StartStopRequest, StrategyToggleRequest
from quant_control_state import load_control_state, save_control_state

ROOT = Path(__file__).resolve().parents[2]
TRACE_PATH = ROOT / "logs" / "alpaca_brain_trace.jsonl"
DB_PATH = ROOT / "logs" / "decision_terminal.db"
JSONL_PATH = ROOT / "logs" / "decision_events.jsonl"

app = FastAPI(title="Quant Control and Data Engine", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONTROL_LOCK = threading.Lock()
CONTROL_STATE: Dict[str, Any] = load_control_state()

STORE = EventStore(DB_PATH, JSONL_PATH)


def _control_copy() -> Dict[str, Any]:
    with CONTROL_LOCK:
        return json.loads(json.dumps(CONTROL_STATE))


def _persist_control(mutated: Dict[str, Any]) -> Dict[str, Any]:
    global CONTROL_STATE
    with CONTROL_LOCK:
        CONTROL_STATE = save_control_state(mutated)
        return json.loads(json.dumps(CONTROL_STATE))


async def _trigger_kill_switch(reason: str) -> None:
    state = _control_copy()
    if state.get("kill_switch"):
        return
    state["kill_switch"] = True
    state["trading_enabled"] = False
    persisted = _persist_control(state)
    await ENGINE.emit(
        EventMessage(
            event_type="risk_event",
            source="control",
            strategy_id="system",
            payload={
                "risk_type": "kill_switch",
                "severity": "error",
                "reason": f"Automatic kill switch triggered: {reason}",
                "controls": persisted,
            },
        )
    )


ENGINE = EventEngine(
    trace_path=TRACE_PATH,
    store=STORE,
    get_control_state=_control_copy,
    trigger_kill_switch=_trigger_kill_switch,
)


@app.on_event("startup")
async def startup() -> None:
    await ENGINE.start()


@app.on_event("shutdown")
async def shutdown() -> None:
    await ENGINE.stop()


def _build_history(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    portfolio_events = [ev for ev in events if ev["event_type"] == "portfolio_update"]
    signal_events = [ev for ev in events if ev["event_type"] == "strategy_signal"]
    risk_events = [ev for ev in events if ev["event_type"] == "risk_event"]

    history: List[Dict[str, Any]] = []
    for sig in signal_events[-80:]:
        ts = sig["ts"]
        side = str(sig["payload"].get("side", "HOLD")).upper()
        strategy = str(sig.get("strategy_id") or sig["payload"].get("strategy", "none"))
        blocked = any(
            r["payload"].get("risk_type") == "trade_block" and str(r.get("strategy_id")) == strategy and abs((datetime.fromisoformat(r["ts"]) - datetime.fromisoformat(ts)).total_seconds()) <= 1.5
            for r in risk_events[-60:]
            if "T" in r["ts"] and "T" in ts
        ) if "T" in ts else False
        latest_pf = next((p for p in reversed(portfolio_events) if p["ts"] <= ts), portfolio_events[-1] if portfolio_events else None)
        pnl = float((latest_pf or {}).get("payload", {}).get("total_pnl", 0.0))
        history.append(
            {
                "ts": ts,
                "symbol": sig.get("symbol") or "BTC/USD",
                "signal": side,
                "action": "BLOCKED" if blocked else ("HOLD" if side == "HOLD" else "EXECUTED"),
                "strategy": strategy,
                "confidence": float(sig["payload"].get("confidence", 0.0)),
                "pnl": pnl,
                "price": float((latest_pf or {}).get("payload", {}).get("price", 0.0)),
                "reason": str(sig["payload"].get("reason", "")),
                "risk_checks": [
                    {
                        "key": "drawdown",
                        "label": "Drawdown guard",
                        "passed": not blocked,
                        "reason": "blocked by risk" if blocked else "within limits",
                    }
                ],
                "raw": sig["payload"],
            }
        )
    return history


def _strategy_intelligence(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    per = defaultdict(lambda: {"trades": 0, "wins": 0, "total_pnl": 0.0, "conf": 0.0, "trend": []})
    for row in history:
        st = per[row["strategy"]]
        st["trades"] += 1
        st["wins"] += 1 if row["pnl"] > 0 else 0
        st["total_pnl"] += float(row["pnl"])
        st["conf"] += float(row["confidence"])
        st["trend"].append({"ts": row["ts"], "pnl": float(row["pnl"]), "confidence": float(row["confidence"])})
    out = []
    for strategy, st in per.items():
        trades = max(int(st["trades"]), 1)
        out.append(
            {
                "strategy": strategy,
                "trades": int(st["trades"]),
                "win_rate": st["wins"] / trades,
                "total_pnl": st["total_pnl"],
                "confidence_avg": st["conf"] / trades,
                "trend": st["trend"][-20:],
            }
        )
    return sorted(out, key=lambda r: r["total_pnl"], reverse=True)


def _performance(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    pf = [ev for ev in events if ev["event_type"] == "portfolio_update"]
    if not pf:
        return {"win_rate": 0.0, "avg_profit": 0.0, "max_drawdown": 0.0, "sharpe_approx": 0.0, "equity_curve": []}

    pnls = [float(e["payload"].get("total_pnl", 0.0)) for e in pf[-120:]]
    eq = [float(e["payload"].get("equity", 0.0)) for e in pf[-120:]]
    wins = sum(1 for i in range(1, len(pnls)) if pnls[i] - pnls[i - 1] > 0)
    avg_profit = mean(pnls) if pnls else 0.0
    peak = 0.0
    max_dd = 0.0
    curve = []
    for idx, value in enumerate(eq):
        peak = max(peak, value)
        max_dd = max(max_dd, peak - value)
        curve.append({"idx": idx, "equity": value})

    deltas = [eq[i] - eq[i - 1] for i in range(1, len(eq))]
    sigma = pstdev(deltas) if len(deltas) > 1 else 0.0
    sharpe = (mean(deltas) / sigma) * (len(deltas) ** 0.5) if sigma > 0 else 0.0

    return {
        "win_rate": wins / max(len(pnls) - 1, 1),
        "avg_profit": avg_profit,
        "max_drawdown": max_dd,
        "sharpe_approx": sharpe,
        "equity_curve": curve[-80:],
    }


def _snapshot() -> Dict[str, Any]:
    events = STORE.recent_events(limit=500)
    history = _build_history(events)
    perf = _performance(events)
    latest = ENGINE.latest_state()

    risk_events = [ev for ev in events if ev["event_type"] == "risk_event"]
    order_events = [ev for ev in events if ev["event_type"] == "order_update"]
    latest_signal = latest.get("signal") or {}
    latest_portfolio = latest.get("portfolio") or {}
    latest_risk = latest.get("risk") or {}
    controls = _control_copy()
    control_risk = controls.get("risk", {}) if isinstance(controls.get("risk"), dict) else {}

    open_orders = []
    for order in reversed(order_events[-30:]):
        state = str(order["payload"].get("state", "")).lower()
        if state in {"filled", "canceled", "rejected"}:
            continue
        open_orders.append(
            {
                "id": str(order["payload"].get("order_id", "")),
                "status": state,
                "symbol": order.get("symbol") or "BTC/USD",
                "price": float(order["payload"].get("fill_price", order["payload"].get("expected_price", 0.0))),
            }
        )
        if len(open_orders) >= 6:
            break

    alerts = [
        {
            "level": "error" if str(ev["payload"].get("severity", "warn")) == "error" else "warn",
            "message": str(ev["payload"].get("reason", "risk event")),
        }
        for ev in risk_events[-8:]
    ]

    current_ts = str(latest_signal.get("ts") or datetime.now(timezone.utc).isoformat())
    signal_side = str(latest_signal.get("side", "HOLD")).upper()
    decision_action = "HOLD" if signal_side == "HOLD" else "EXECUTE"
    equity = float(latest_portfolio.get("equity", 0.0))
    pnl = float(latest_portfolio.get("total_pnl", 0.0))
    position_size = float(latest_portfolio.get("position_size", 0.0))
    price = float(latest_portfolio.get("price", 0.0))
    exposure_notional = abs(position_size) * price
    max_daily_loss = float(control_risk.get("max_daily_loss", 500.0))
    confidence_threshold = float(control_risk.get("confidence_threshold", 0.35))
    max_position_size = float(control_risk.get("max_position_size", 0.0))
    daily_loss_used = max(0.0, -pnl)
    daily_limit_utilization = (daily_loss_used / max_daily_loss) if max_daily_loss > 0 else 0.0
    max_exposure_notional = abs(max_position_size) * price
    exposure_utilization = (exposure_notional / max_exposure_notional) if max_exposure_notional > 0 else 0.0
    halted = bool(controls.get("kill_switch", False)) or not bool(controls.get("trading_enabled", True))

    reconnect_count = sum(
        1
        for ev in events[-200:]
        if ev.get("event_type") == "risk_event" and str(ev.get("payload", {}).get("risk_type", "")) == "data_feed_failure"
    )
    last_tick_age_sec: int | None = None
    if isinstance(latest_signal.get("ts"), str):
        try:
            tick_ts = datetime.fromisoformat(str(latest_signal.get("ts")))
            now_ts = datetime.now(timezone.utc)
            if tick_ts.tzinfo is None:
                tick_ts = tick_ts.replace(tzinfo=timezone.utc)
            last_tick_age_sec = max(0, int((now_ts - tick_ts).total_seconds()))
        except ValueError:
            last_tick_age_sec = None

    return {
        "decision": {
            "signal": {
                "side": signal_side,
                "confidence": float(latest_signal.get("confidence", 0.0)),
                "strategy": str(latest_signal.get("strategy", "none")),
                "reason": str(latest_signal.get("reason", "waiting for stream")),
                "timestamp": current_ts,
                "trend": [
                    {"idx": i, "signal": h["signal"], "confidence": float(h["confidence"])}
                    for i, h in enumerate(history[-25:])
                ],
            },
            "checks": [],
            "decision": {
                "action": decision_action,
                "stage": "live",
                "reason": str(latest_signal.get("reason", "waiting for stream")),
                "pipeline": {
                    "signal": "done" if signal_side != "HOLD" else "idle",
                    "decision": "done" if signal_side != "HOLD" else "idle",
                    "sent": "done" if order_events else "idle",
                    "filled": "done" if any(str(o["payload"].get("state", "")).lower() == "filled" for o in order_events[-20:]) else "idle",
                },
            },
            "position": {
                "symbol": "BTC/USD",
                "size": float(latest_portfolio.get("position_size", 0.0)),
                "price": float(latest_portfolio.get("price", 0.0)),
            },
            "account": {
                "equity": equity,
                "pnl": pnl,
                "executed_trades": int(sum(1 for h in history if h["action"] == "EXECUTED")),
                "cash": float(latest_portfolio.get("cash", 0.0)),
                "open_orders": open_orders,
                "pnl_spark": [
                    {"idx": i, "pnl": float(h["pnl"])}
                    for i, h in enumerate(history[-40:])
                ],
            },
        },
        "meta": {
            "connected": TRACE_PATH.exists(),
            "connection_event": "streaming" if TRACE_PATH.exists() else "waiting",
            "reconnects": reconnect_count,
            "last_tick_age_sec": last_tick_age_sec,
            "controls": controls,
        },
        "system_metrics": {
            "equity": equity,
            "pnl": pnl,
            "daily_loss_used": daily_loss_used,
            "daily_loss_limit": max_daily_loss,
            "daily_limit_utilization": daily_limit_utilization,
            "exposure_notional": exposure_notional,
            "max_exposure_notional": max_exposure_notional,
            "exposure_utilization": exposure_utilization,
            "position_size": position_size,
            "position_price": price,
            "halted": halted,
        },
        "risk_state": {
            "halted": halted,
            "kill_switch": bool(controls.get("kill_switch", False)),
            "trading_enabled": bool(controls.get("trading_enabled", True)),
            "confidence_threshold": confidence_threshold,
            "max_position_size": max_position_size,
            "daily_loss_limit": max_daily_loss,
            "latest_risk_type": str(latest_risk.get("risk_type", "")),
            "latest_risk_reason": str(latest_risk.get("reason", "")),
            "latest_risk_severity": str(latest_risk.get("severity", "info")),
        },
        "thought_stream": [
            {
                "ts": ev["ts"],
                "level": "error" if ev["event_type"] == "risk_event" and str(ev["payload"].get("severity", "warn")) == "error" else "info",
                "stage": ev["event_type"],
                "message": str(ev["payload"].get("reason", ev["payload"])),
                "symbol": ev.get("symbol"),
            }
            for ev in events[-80:]
        ],
        "history": history,
        "why_not_trade": [
            {
                "ts": ev["ts"],
                "action": "BLOCKED",
                "checks": [
                    {
                        "key": "risk",
                        "label": "Risk event",
                        "passed": False,
                        "reason": str(ev["payload"].get("reason", "risk event")),
                    }
                ],
                "reason": str(ev["payload"].get("reason", "risk event")),
            }
            for ev in risk_events[-30:]
            if str(ev["payload"].get("risk_type", "")) in {"trade_block", "abnormal_loss", "drawdown_breach", "data_feed_failure"}
        ],
        "strategy_intelligence": _strategy_intelligence(history),
        "decision_inspector": {
            "full_object": latest,
            "features": {},
            "risk_checks": [],
            "reasoning": str(latest_signal.get("reason", "waiting for stream")),
        },
        "counterfactuals": [],
        "performance": perf,
        "replay": {
            "cursor": len(history) - 1,
            "length": len(history),
            "timeline": history[-100:],
        },
        "alerts": alerts,
    }


@app.get("/api/health")
def health() -> Dict[str, bool]:
    return {"ok": True}


    @app.get("/health")
    def root_health() -> Dict[str, Any]:
        snap = _snapshot()
        system_metrics = snap.get("system_metrics", {}) if isinstance(snap.get("system_metrics"), dict) else {}
        risk_state = snap.get("risk_state", {}) if isinstance(snap.get("risk_state"), dict) else {}
        return {
            "ok": True,
            "service": "decision_terminal_backend",
            "trace_connected": bool(snap.get("meta", {}).get("connected", False)),
            "halted": bool(risk_state.get("halted", False)),
            "equity": float(system_metrics.get("equity", 0.0)),
            "pnl": float(system_metrics.get("pnl", 0.0)),
        }


@app.get("/api/decision/snapshot")
def decision_snapshot() -> Dict[str, Any]:
    return _snapshot()


@app.get("/api/events/recent")
def recent_events(limit: int = 200, event_type: str | None = None) -> Dict[str, Any]:
    return {"events": STORE.recent_events(limit=limit, event_type=event_type)}


@app.get("/api/events/replay")
def replay_events(session_id: str, limit: int = 1000) -> Dict[str, Any]:
    return {"events": STORE.replay_session(session_id=session_id, limit=limit)}


@app.post("/api/control/start")
async def start_trading() -> Dict[str, Any]:
    state = _control_copy()
    state["trading_enabled"] = True
    state["kill_switch"] = False
    persisted = _persist_control(state)
    await ENGINE.emit(
        EventMessage(
            event_type="risk_event",
            source="control",
            strategy_id="system",
            payload={"risk_type": "control", "severity": "info", "reason": "trading started", "controls": persisted},
        )
    )
    return {"ok": True, "control": persisted}


@app.post("/api/control/stop")
async def stop_trading() -> Dict[str, Any]:
    state = _control_copy()
    state["trading_enabled"] = False
    persisted = _persist_control(state)
    await ENGINE.emit(
        EventMessage(
            event_type="risk_event",
            source="control",
            strategy_id="system",
            payload={"risk_type": "control", "severity": "warn", "reason": "trading stopped", "controls": persisted},
        )
    )
    return {"ok": True, "control": persisted}


@app.post("/api/control/trading")
async def control_trading(payload: StartStopRequest) -> Dict[str, Any]:
    return await (start_trading() if payload.enabled else stop_trading())


@app.post("/api/control/strategy")
async def control_strategy(payload: StrategyToggleRequest) -> Dict[str, Any]:
    state = _control_copy()
    strategy = payload.strategy.strip().lower()
    if strategy not in state.get("strategies", {}):
        raise HTTPException(status_code=404, detail=f"Unknown strategy: {strategy}")
    state["strategies"][strategy] = payload.enabled
    persisted = _persist_control(state)
    await ENGINE.emit(
        EventMessage(
            event_type="risk_event",
            source="control",
            strategy_id=strategy,
            payload={
                "risk_type": "control",
                "severity": "info",
                "reason": f"strategy {strategy} {'enabled' if payload.enabled else 'disabled'}",
                "controls": persisted,
            },
        )
    )
    return {"ok": True, "control": persisted}


@app.post("/api/control/risk")
async def control_risk(payload: RiskUpdateRequest) -> Dict[str, Any]:
    updates = payload.model_dump(exclude_none=True)
    state = _control_copy()
    for key, value in updates.items():
        state.setdefault("risk", {})[key] = float(value)
    persisted = _persist_control(state)
    await ENGINE.emit(
        EventMessage(
            event_type="risk_event",
            source="control",
            strategy_id="system",
            payload={"risk_type": "control", "severity": "info", "reason": "risk parameters updated", "updates": updates},
        )
    )
    return {"ok": True, "control": persisted}


@app.post("/api/control/kill-switch")
async def control_kill_switch(payload: KillSwitchRequest) -> Dict[str, Any]:
    state = _control_copy()
    state["kill_switch"] = payload.engage
    if payload.engage:
        state["trading_enabled"] = False
    persisted = _persist_control(state)
    await ENGINE.emit(
        EventMessage(
            event_type="risk_event",
            source="control",
            strategy_id="system",
            payload={
                "risk_type": "kill_switch",
                "severity": "error" if payload.engage else "info",
                "reason": "kill switch engaged" if payload.engage else "kill switch released",
            },
        )
    )
    return {"ok": True, "control": persisted}


@app.post("/api/control/reset-portfolio")
async def reset_portfolio() -> Dict[str, Any]:
    state = _control_copy()
    state["portfolio_reset_requested_at"] = datetime.now(timezone.utc).isoformat()
    persisted = _persist_control(state)
    await ENGINE.emit(
        EventMessage(
            event_type="portfolio_update",
            source="control",
            strategy_id="system",
            payload={
                "equity": 0.0,
                "total_pnl": 0.0,
                "cash": 0.0,
                "position_size": 0.0,
                "drawdown": 0.0,
                "reason": "portfolio reset requested",
            },
        )
    )
    return {"ok": True, "control": persisted}


@app.websocket("/ws/events")
async def ws_events(ws: WebSocket) -> None:
    await ws.accept()
    queue = ENGINE.subscribe()
    try:
        while True:
            event = await queue.get()
            await ws.send_json(event.model_dump())
    except WebSocketDisconnect:
        ENGINE.unsubscribe(queue)


@app.websocket("/ws/decisions")
async def ws_decisions(ws: WebSocket) -> None:
    await ws.accept()
    queue = ENGINE.subscribe()
    try:
        await ws.send_json(_snapshot())
        while True:
            try:
                await asyncio.wait_for(queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                pass
            await ws.send_json(_snapshot())
    except WebSocketDisconnect:
        return
    finally:
        ENGINE.unsubscribe(queue)
