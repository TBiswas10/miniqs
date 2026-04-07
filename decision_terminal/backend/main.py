from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from quant_control_state import load_control_state, save_control_state

TRACE_PATH = Path(__file__).resolve().parents[2] / "logs" / "alpaca_brain_trace.jsonl"
MAX_EVENTS = 160
DB_PATH = Path(__file__).resolve().parents[2] / "logs" / "decision_terminal.db"


class StrategyToggleRequest(BaseModel):
    strategy: str
    enabled: bool


class RiskUpdateRequest(BaseModel):
    confidence_threshold: float | None = None
    max_position_size: float | None = None
    max_daily_loss: float | None = None


class TradingStateRequest(BaseModel):
    enabled: bool


class KillSwitchRequest(BaseModel):
    engage: bool

app = FastAPI(title="Decision Intelligence Terminal API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONTROL_STATE: dict[str, Any] = load_control_state()
CONTROL_LOCK = threading.Lock()
SNAPSHOT_LOCK = threading.Lock()
SNAPSHOT_CACHE: dict[str, Any] = {"payload": None, "built_at": 0.0, "trace_mtime": None}
LAST_INGEST_AT = 0.0


def _db_connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    conn = _db_connect()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            signal TEXT,
            action TEXT,
            strategy TEXT,
            confidence REAL,
            pnl REAL,
            price REAL,
            allowed INTEGER,
            reason TEXT,
            payload TEXT,
            UNIQUE(ts, strategy, action)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS control_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS counterfactuals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            strategy TEXT,
            side TEXT,
            entry_price REAL,
            simulated_exit_price REAL,
            simulated_pnl REAL,
            payload TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def _log_control_action(action: str, details: dict[str, Any]) -> None:
    conn = _db_connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO control_actions(ts, action, details) VALUES (?, ?, ?)",
        (datetime.now(timezone.utc).isoformat(), action, json.dumps(details)),
    )
    conn.commit()
    conn.close()


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _read_trace(limit: int = MAX_EVENTS) -> list[dict[str, Any]]:
    if not TRACE_PATH.exists():
        return []
    events: deque[dict[str, Any]] = deque(maxlen=limit)
    with TRACE_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                events.append(obj)
    return list(events)


def _risk_checks(risk: dict[str, Any] | None) -> list[dict[str, Any]]:
    checks = [
        {"key": "confidence", "label": "Confidence threshold", "passed": True, "reason": "Signal confidence accepted"},
        {"key": "cooldown", "label": "Cooldown window", "passed": True, "reason": "Cooldown clear"},
        {"key": "position", "label": "Position limits", "passed": True, "reason": "Position size valid"},
        {"key": "drawdown", "label": "Drawdown guard", "passed": True, "reason": "Loss guard within limit"},
    ]
    if not risk:
        return checks
    if risk.get("allowed"):
        return checks
    reason = str(risk.get("reason", "unknown")).lower()
    for check in checks:
        if check["key"] in reason:
            check["passed"] = False
            check["reason"] = str(risk.get("reason", "risk block"))
            return checks
    checks[-1]["passed"] = False
    checks[-1]["reason"] = str(risk.get("reason", "risk block"))
    return checks


def _signal_side(chosen: dict[str, Any] | None) -> str:
    action = str((chosen or {}).get("action", "HOLD")).upper()
    if action in {"BUY", "LONG"}:
        return "BUY"
    if action in {"SELL", "SHORT"}:
        return "SELL"
    return "HOLD"


def _ingest_decisions_to_db(events: list[dict[str, Any]]) -> None:
    rows: list[tuple[Any, ...]] = []
    for ev in events:
        if ev.get("kind") != "decision":
            continue
        chosen = ev.get("chosen") if isinstance(ev.get("chosen"), dict) else {}
        risk = ev.get("risk") if isinstance(ev.get("risk"), dict) else {}
        action = "BLOCKED" if risk and not risk.get("allowed") else "EXECUTED"
        signal = _signal_side(chosen)
        if signal == "HOLD":
            action = "HOLD"
        rows.append(
            (
                str(ev.get("timestamp") or ev.get("ts") or "--"),
                signal,
                action,
                str(chosen.get("strategy") or "none"),
                float(chosen.get("confidence") or 0.0),
                float(ev.get("total_pnl") or 0.0),
                float(ev.get("price") or 0.0),
                1 if risk.get("allowed") else 0,
                str(risk.get("reason") or chosen.get("reason") or ev.get("detail") or "--"),
                json.dumps(ev),
            )
        )

    if not rows:
        return

    conn = _db_connect()
    cur = conn.cursor()
    cur.executemany(
        """
        INSERT OR IGNORE INTO decisions(
            ts, signal, action, strategy, confidence, pnl, price, allowed, reason, payload
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    conn.commit()
    conn.close()


def _counterfactuals(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decision_events = [ev for ev in events if ev.get("kind") == "decision"]
    results: list[dict[str, Any]] = []
    for idx, ev in enumerate(decision_events):
        risk = ev.get("risk") if isinstance(ev.get("risk"), dict) else {}
        chosen = ev.get("chosen") if isinstance(ev.get("chosen"), dict) else {}
        if risk.get("allowed"):
            continue
        side = _signal_side(chosen)
        if side == "HOLD":
            continue
        entry = float(ev.get("price") or 0.0)
        future_idx = min(idx + 10, len(decision_events) - 1)
        exit_price = float(decision_events[future_idx].get("price") or entry)
        simulated = (exit_price - entry) if side == "BUY" else (entry - exit_price)
        results.append(
            {
                "ts": ev.get("timestamp") or ev.get("ts") or "--",
                "strategy": chosen.get("strategy", "none"),
                "side": side,
                "entry_price": entry,
                "simulated_exit_price": exit_price,
                "simulated_pnl": simulated,
                "reason_blocked": risk.get("reason", "unknown"),
            }
        )
    return results[-30:]


def _record_counterfactuals(counterfactuals: list[dict[str, Any]]) -> None:
    if not counterfactuals:
        return
    conn = _db_connect()
    cur = conn.cursor()
    cur.executemany(
        """
        INSERT INTO counterfactuals(ts, strategy, side, entry_price, simulated_exit_price, simulated_pnl, payload)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                cf["ts"],
                cf["strategy"],
                cf["side"],
                cf["entry_price"],
                cf["simulated_exit_price"],
                cf["simulated_pnl"],
                json.dumps(cf),
            )
            for cf in counterfactuals[-5:]
        ],
    )
    conn.commit()
    conn.close()


def _strategy_intelligence(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    per_strategy: dict[str, dict[str, Any]] = {}
    for row in history:
        strategy = str(row.get("strategy") or "none")
        if strategy not in per_strategy:
            per_strategy[strategy] = {
                "strategy": strategy,
                "trades": 0,
                "wins": 0,
                "total_pnl": 0.0,
                "confidence_avg": 0.0,
                "confidence_samples": 0,
                "trend": [],
            }
        s = per_strategy[strategy]
        pnl = float(row.get("pnl") or 0.0)
        conf = float(row.get("confidence") or 0.0)
        s["trades"] += 1
        s["wins"] += 1 if pnl > 0 else 0
        s["total_pnl"] += pnl
        s["confidence_samples"] += 1
        s["confidence_avg"] += conf
        s["trend"].append({"ts": row.get("ts"), "pnl": pnl, "confidence": conf})

    results = []
    for s in per_strategy.values():
        samples = max(int(s["confidence_samples"]), 1)
        results.append(
            {
                "strategy": s["strategy"],
                "trades": s["trades"],
                "win_rate": s["wins"] / max(s["trades"], 1),
                "total_pnl": s["total_pnl"],
                "confidence_avg": s["confidence_avg"] / samples,
                "trend": s["trend"][-20:],
            }
        )
    return sorted(results, key=lambda x: x["total_pnl"], reverse=True)


def _performance_analytics(history: list[dict[str, Any]]) -> dict[str, Any]:
    if not history:
        return {
            "win_rate": 0.0,
            "avg_profit": 0.0,
            "max_drawdown": 0.0,
            "sharpe_approx": 0.0,
            "equity_curve": [],
        }

    pnls = [float(row.get("pnl") or 0.0) for row in history]
    wins = sum(1 for p in pnls if p > 0)
    avg = sum(pnls) / max(len(pnls), 1)

    equity = []
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for idx, p in enumerate(pnls):
        cumulative += p
        peak = max(peak, cumulative)
        drawdown = peak - cumulative
        max_dd = max(max_dd, drawdown)
        equity.append({"idx": idx, "equity": cumulative})

    mean = avg
    variance = sum((p - mean) ** 2 for p in pnls) / max(len(pnls), 1)
    std = variance ** 0.5
    sharpe = (mean / std) * (len(pnls) ** 0.5) if std > 0 else 0.0

    return {
        "win_rate": wins / max(len(pnls), 1),
        "avg_profit": avg,
        "max_drawdown": max_dd,
        "sharpe_approx": sharpe,
        "equity_curve": equity[-60:],
    }


def _alerts_payload(history: list[dict[str, Any]], counterfactuals: list[dict[str, Any]]) -> list[dict[str, str]]:
    alerts: list[dict[str, str]] = []
    recent = history[-20:]
    blocked_count = sum(1 for row in recent if row.get("action") == "BLOCKED")
    if blocked_count >= 10:
        alerts.append({"level": "warn", "message": "High blocked-trade ratio in recent decisions."})

    recent_pnls = [float(row.get("pnl") or 0.0) for row in recent]
    if recent_pnls and min(recent_pnls) < -250:
        alerts.append({"level": "error", "message": "Large single-step loss detected."})

    if counterfactuals:
        missed = sum(float(cf.get("simulated_pnl") or 0.0) for cf in counterfactuals[-10:])
        if missed > 150:
            alerts.append({"level": "info", "message": "Counterfactual engine indicates significant missed upside."})
    return alerts


def _compute_snapshot() -> dict[str, Any]:
    global CONTROL_STATE
    global LAST_INGEST_AT

    with CONTROL_LOCK:
        CONTROL_STATE = load_control_state()
    events = _read_trace(MAX_EVENTS)

    now = time.time()
    if now - LAST_INGEST_AT >= 3.0:
        _ingest_decisions_to_db(events)
        LAST_INGEST_AT = now

    latest_decision = next((ev for ev in reversed(events) if ev.get("kind") == "decision"), None)
    latest_trade = next((ev for ev in reversed(events) if ev.get("kind") == "trade_update"), None)

    latest_connection = next((ev for ev in reversed(events) if ev.get("kind") == "connection"), None)
    reconnects = sum(
        1 for ev in events if ev.get("kind") == "connection" and "reconnect" in str(ev.get("event", "")).lower()
    )

    chosen = latest_decision.get("chosen") if isinstance(latest_decision, dict) and isinstance(latest_decision.get("chosen"), dict) else None
    risk = latest_decision.get("risk") if isinstance(latest_decision, dict) and isinstance(latest_decision.get("risk"), dict) else None

    signal = _signal_side(chosen)
    action = "BLOCKED" if risk and not risk.get("allowed") else "EXECUTE"
    if signal == "HOLD":
        action = "HOLD"

    ts_value = (latest_decision or {}).get("timestamp") or (latest_decision or {}).get("ts")
    tick_ts = _parse_ts(ts_value)
    tick_age = None
    if tick_ts is not None:
        tick_age = max((datetime.now(timezone.utc) - tick_ts).total_seconds(), 0.0)

    thought_stream = []
    for ev in events[-80:]:
        stage = str(ev.get("stage") or ev.get("kind") or "event")
        level = "info"
        if stage in {"risk_blocked", "auth_failed"}:
            level = "warn"
        if "error" in stage.lower() or "fail" in stage.lower():
            level = "error"
        thought_stream.append(
            {
                "ts": ev.get("timestamp") or ev.get("ts") or "--",
                "level": level,
                "stage": stage,
                "message": ev.get("detail") or ev.get("decision") or "update",
                "symbol": ev.get("symbol"),
            }
        )

    history = []
    for ev in [e for e in events if e.get("kind") == "decision"][-60:]:
        ev_chosen = ev.get("chosen") if isinstance(ev.get("chosen"), dict) else None
        ev_risk = ev.get("risk") if isinstance(ev.get("risk"), dict) else None
        side = _signal_side(ev_chosen)
        status = "BLOCKED" if ev_risk and not ev_risk.get("allowed") else "EXECUTED"
        if side == "HOLD":
            status = "HOLD"
        history.append(
            {
                "ts": ev.get("timestamp") or ev.get("ts") or "--",
                "symbol": ev.get("symbol", "--"),
                "signal": side,
                "action": status,
                "confidence": (ev_chosen or {}).get("confidence", 0.0),
                "strategy": (ev_chosen or {}).get("strategy", "none"),
                "pnl": float(ev.get("total_pnl") or 0.0),
                "price": ev.get("price"),
                "reason": (ev_risk or {}).get("reason") or (ev_chosen or {}).get("reason") or ev.get("detail") or "--",
                "risk_checks": _risk_checks(ev_risk),
                "raw": ev,
            }
        )

    counterfactuals = _counterfactuals(events)
    _record_counterfactuals(counterfactuals)
    strategy_intel = _strategy_intelligence(history)
    perf = _performance_analytics(history)
    pnl_spark = [{"idx": i, "pnl": float(row.get("pnl") or 0.0)} for i, row in enumerate(history[-40:])]
    open_orders = [
        {
            "id": str(ev.get("order_id") or ev.get("id") or "--"),
            "status": str(ev.get("event") or "pending"),
            "symbol": str(ev.get("symbol") or "BTC/USD"),
            "price": float(ev.get("price") or 0.0),
        }
        for ev in events[-20:]
        if ev.get("kind") in {"order", "trade_update"} and str(ev.get("event", "")).lower() not in {"fill", "filled"}
    ][-6:]

    current_ts = str((latest_decision or {}).get("timestamp") or (latest_decision or {}).get("ts") or "--")
    signal_trend = [
        {
            "idx": i,
            "signal": row.get("signal", "HOLD"),
            "confidence": float(row.get("confidence") or 0.0),
        }
        for i, row in enumerate(history[-25:])
    ]
    why_not_rows = [
        {
            "ts": row.get("ts"),
            "action": row.get("action"),
            "checks": row.get("risk_checks", []),
            "reason": row.get("reason"),
        }
        for row in history[-25:]
    ]

    alerts = _alerts_payload(history, counterfactuals)

    pipeline_status = {
        "signal": "done" if signal != "HOLD" else "idle",
        "decision": "done" if latest_decision else "idle",
        "sent": "done" if latest_trade else ("blocked" if action == "BLOCKED" else "idle"),
        "filled": "done" if latest_trade and str(latest_trade.get("event", "")).lower() in {"fill", "filled"} else "idle",
    }

    decision_object = {
        "signal": {
            "side": signal,
            "confidence": float((chosen or {}).get("confidence", 0.0) or 0.0),
            "strategy": (chosen or {}).get("strategy", "none"),
            "reason": (chosen or {}).get("reason", "no signal"),
            "timestamp": current_ts,
            "trend": signal_trend,
        },
        "checks": _risk_checks(risk),
        "decision": {
            "action": action,
            "stage": (latest_decision or {}).get("stage", "idle"),
            "reason": (risk or {}).get("reason")
            if action == "BLOCKED"
            else (chosen or {}).get("reason", "waiting for confidence"),
            "pipeline": pipeline_status,
        },
        "position": {
            "symbol": (latest_decision or {}).get("symbol", "BTC/USD"),
            "size": float((latest_decision or {}).get("position_size", 0.0) or 0.0),
            "price": float((latest_decision or {}).get("price", 0.0) or 0.0),
        },
        "account": {
            "equity": float((latest_decision or {}).get("equity", 0.0) or 0.0),
            "pnl": float((latest_decision or {}).get("total_pnl", 0.0) or 0.0),
            "executed_trades": int((latest_decision or {}).get("executed_trades", 0) or 0),
            "cash": float((latest_decision or {}).get("equity", 0.0) or 0.0) - float((latest_decision or {}).get("position_size", 0.0) or 0.0) * float((latest_decision or {}).get("price", 0.0) or 0.0),
            "open_orders": open_orders,
            "pnl_spark": pnl_spark,
        },
    }

    return {
        "decision": decision_object,
        "meta": {
            "connected": latest_connection is not None,
            "connection_event": (latest_connection or {}).get("event", "waiting"),
            "reconnects": reconnects,
            "last_tick_age_sec": tick_age,
            "controls": CONTROL_STATE,
        },
        "thought_stream": thought_stream,
        "history": history,
        "why_not_trade": why_not_rows,
        "strategy_intelligence": strategy_intel,
        "decision_inspector": {
            "full_object": latest_decision or {},
            "features": (latest_decision or {}).get("features", {}),
            "risk_checks": _risk_checks(risk),
            "reasoning": (latest_decision or {}).get("detail") or (chosen or {}).get("reason") or "--",
        },
        "counterfactuals": counterfactuals,
        "performance": perf,
        "replay": {
            "cursor": len(history) - 1,
            "length": len(history),
            "timeline": history[-100:],
        },
        "alerts": alerts,
    }


def _build_snapshot() -> dict[str, Any]:
    ttl_seconds = 1.0
    trace_mtime = TRACE_PATH.stat().st_mtime if TRACE_PATH.exists() else None
    now = time.time()

    with SNAPSHOT_LOCK:
        cached_payload = SNAPSHOT_CACHE.get("payload")
        cached_at = float(SNAPSHOT_CACHE.get("built_at") or 0.0)
        cached_trace_mtime = SNAPSHOT_CACHE.get("trace_mtime")

        if (
            cached_payload is not None
            and now - cached_at < ttl_seconds
            and cached_trace_mtime == trace_mtime
        ):
            return cached_payload

        payload = _compute_snapshot()
        SNAPSHOT_CACHE["payload"] = payload
        SNAPSHOT_CACHE["built_at"] = now
        SNAPSHOT_CACHE["trace_mtime"] = trace_mtime
        return payload


@app.get("/api/decision/snapshot")
def decision_snapshot() -> dict[str, Any]:
    return _build_snapshot()


@app.post("/api/control/trading")
def control_trading(payload: TradingStateRequest) -> dict[str, Any]:
    with CONTROL_LOCK:
        CONTROL_STATE["trading_enabled"] = payload.enabled
        if not payload.enabled:
            CONTROL_STATE["kill_switch"] = False
        save_control_state(CONTROL_STATE)
    _log_control_action("trading_toggle", payload.model_dump())
    return {"ok": True, "control": CONTROL_STATE}


@app.post("/api/control/strategy")
def control_strategy(payload: StrategyToggleRequest) -> dict[str, Any]:
    strategy = payload.strategy.strip().lower()
    with CONTROL_LOCK:
        if strategy not in CONTROL_STATE["strategies"]:
            raise HTTPException(status_code=404, detail=f"Unknown strategy: {strategy}")
        CONTROL_STATE["strategies"][strategy] = payload.enabled
        save_control_state(CONTROL_STATE)
    _log_control_action("strategy_toggle", payload.model_dump())
    return {"ok": True, "control": CONTROL_STATE}


@app.post("/api/control/risk")
def control_risk(payload: RiskUpdateRequest) -> dict[str, Any]:
    updates = payload.model_dump(exclude_none=True)
    with CONTROL_LOCK:
        for key, value in updates.items():
            CONTROL_STATE["risk"][key] = float(value)
        save_control_state(CONTROL_STATE)
    _log_control_action("risk_update", updates)
    return {"ok": True, "control": CONTROL_STATE}


@app.post("/api/control/kill-switch")
def control_kill_switch(payload: KillSwitchRequest) -> dict[str, Any]:
    with CONTROL_LOCK:
        CONTROL_STATE["kill_switch"] = payload.engage
        if payload.engage:
            CONTROL_STATE["trading_enabled"] = False
        save_control_state(CONTROL_STATE)
    _log_control_action("kill_switch", payload.model_dump())
    return {"ok": True, "control": CONTROL_STATE}


@app.websocket("/ws/decisions")
async def decision_stream(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            await ws.send_json(_build_snapshot())
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


_init_db()
