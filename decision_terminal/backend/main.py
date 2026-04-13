from __future__ import annotations

import asyncio
import json
import threading
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.miniqs.config.asset import resolve_asset_config
from .event_engine import EventEngine
from .event_persistence import EventStore
from .event_schemas import AssetUpdateRequest, EventMessage, KillSwitchRequest, ReplayForkRequest, RiskUpdateRequest, StartStopRequest, StrategyToggleRequest
from src.miniqs.risk.quant_control_state import load_control_state, save_control_state
from src.miniqs.strategies import default_strategy_registry

ROOT = Path(__file__).resolve().parents[2]
TRACE_PATH = ROOT / "logs" / "alpaca_brain_trace.jsonl"
DB_PATH = ROOT / "logs" / "decision_terminal.db"
JSONL_PATH = ROOT / "logs" / "decision_events.jsonl"

@asynccontextmanager
async def lifespan(_app: FastAPI):
    if os.getenv("RESET_STORAGE", "true").lower() == "true":
        STORE.clear_all()
        print("[backend] Dashboard storage reset completed.")
        
    await ENGINE.start()
    try:
        yield
    finally:
        await ENGINE.stop()


app = FastAPI(title="Quant Control and Data Engine", version="2.0.0", lifespan=lifespan)
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
SUPPORTED_STRATEGIES = tuple(default_strategy_registry().list_names())
INT_RISK_FIELDS = {"cooldown_seconds", "max_concurrent_positions"}
SUPPORTED_RISK_FIELDS = tuple(RiskUpdateRequest.model_fields.keys())


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


def _build_history(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    portfolio_events = [ev for ev in events if ev["event_type"] == "portfolio_update"]
    signal_events = [ev for ev in events if ev["event_type"] == "strategy_signal"]
    risk_events = [ev for ev in events if ev["event_type"] == "risk_event"]

    history: List[Dict[str, Any]] = []
    for sig in signal_events[-80:]:
        ts = sig["ts"]
        side = str(sig["payload"].get("side", "HOLD")).upper()
        strategy = str(sig.get("strategy_id") or sig["payload"].get("strategy", "pending"))
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


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _latest_decision_row(latest_signal: Dict[str, Any]) -> Dict[str, Any]:
    raw = latest_signal.get("raw") if isinstance(latest_signal.get("raw"), dict) else {}
    if isinstance(raw.get("raw"), dict):
        return dict(raw.get("raw") or {})
    return {}


def _strategy_health(history: List[Dict[str, Any]], strategy_names: List[str], window: int = 80) -> Dict[str, Dict[str, Any]]:
    rows = history[-window:]
    total = max(len(rows), 1)
    pnl_values = [float(row.get("pnl", 0.0)) for row in rows]
    pnl_min = min(pnl_values) if pnl_values else 0.0
    pnl_max = max(pnl_values) if pnl_values else 0.0

    out: Dict[str, Dict[str, Any]] = {}
    for strategy in strategy_names:
        mine = [row for row in rows if str(row.get("strategy", "")) == strategy]
        executed = [row for row in mine if str(row.get("action", "")).upper() == "EXECUTED"]
        wins = [row for row in executed if float(row.get("pnl", 0.0)) > 0.0]

        participation_rate = len(mine) / total
        avg_confidence = mean(float(row.get("confidence", 0.0)) for row in mine) if mine else 0.0
        recent_hit_rate = (len(wins) / max(len(executed), 1)) if mine else 0.0
        strategy_pnl = sum(float(row.get("pnl", 0.0)) for row in mine)
        if pnl_max > pnl_min:
            contribution_score = (strategy_pnl - pnl_min) / (pnl_max - pnl_min)
        else:
            contribution_score = 0.5 if mine else 0.0

        health_score = _clamp01(
            (0.30 * _clamp01(participation_rate * 3.0))
            + (0.25 * _clamp01(avg_confidence))
            + (0.25 * _clamp01(recent_hit_rate))
            + (0.20 * _clamp01(contribution_score))
        )
        if participation_rate < 0.05 and avg_confidence < 0.15:
            status = "inactive"
        elif health_score >= 0.60:
            status = "healthy"
        else:
            status = "degrading"

        out[strategy] = {
            "participation_rate": round(_clamp01(participation_rate), 6),
            "avg_confidence": round(_clamp01(avg_confidence), 6),
            "recent_hit_rate": round(_clamp01(recent_hit_rate), 6),
            "contribution_score": round(_clamp01(contribution_score), 6),
            "health_score": round(health_score, 6),
            "status": status,
        }
    return out


def _confidence_decomposition(
    latest_signal: Dict[str, Any],
    decision_row: Dict[str, Any],
    strategy_health: Dict[str, Dict[str, Any]],
) -> Dict[str, float]:
    signals = decision_row.get("src.miniqs.signals") if isinstance(decision_row.get("src.miniqs.signals"), dict) else {}
    signal_strength = _clamp01(max((float(v.get("confidence", 0.0)) for v in signals.values() if isinstance(v, dict)), default=float(latest_signal.get("confidence", 0.0))))

    actionable = [
        payload
        for payload in signals.values()
        if isinstance(payload, dict) and str(payload.get("action", "")).lower() in {"buy", "sell"}
    ]
    if not actionable:
        agreement = 0.0
    else:
        buy_votes = sum(1 for payload in actionable if str(payload.get("action", "")).lower() == "buy")
        sell_votes = len(actionable) - buy_votes
        agreement = max(buy_votes, sell_votes) / max(len(actionable), 1)

    stage = str(decision_row.get("stage", "")).lower()
    detail = str(decision_row.get("detail", "")).lower()
    regime_fit = 0.70
    if stage in {"warmup", "no_signal"}:
        regime_fit = 0.20
    if "volatility" in detail or "feature_window_not_ready" in detail:
        regime_fit = min(regime_fit, 0.15)
    if isinstance(decision_row.get("chosen"), dict):
        regime_fit = max(regime_fit, 0.75)

    strategy = str(latest_signal.get("strategy") or "pending")
    historical_edge = float(strategy_health.get(strategy, {}).get("health_score", 0.0))

    final = _clamp01((0.35 * signal_strength) + (0.20 * _clamp01(agreement)) + (0.20 * _clamp01(regime_fit)) + (0.25 * _clamp01(historical_edge)))
    return {
        "signal_strength": round(_clamp01(signal_strength), 6),
        "agreement": round(_clamp01(agreement), 6),
        "regime_fit": round(_clamp01(regime_fit), 6),
        "historical_edge": round(_clamp01(historical_edge), 6),
        "final": round(final, 6),
    }


def _risk_debug(
    confidence: Dict[str, float],
    portfolio: Dict[str, Any],
    control_risk: Dict[str, Any],
) -> Dict[str, Dict[str, Any]]:
    conf_value = float(confidence.get("final", 0.0))
    conf_threshold = float(control_risk.get("confidence_threshold", 0.35))
    pos_current = abs(float(portfolio.get("position_size", 0.0) or 0.0))
    pos_max = max(float(control_risk.get("max_position_size", 0.0) or 0.0), 0.0)
    drawdown = float(portfolio.get("drawdown", 0.0) or 0.0)
    equity = max(float(portfolio.get("equity", 0.0) or 0.0), 0.0)
    drawdown_limit_ratio = float(control_risk.get("portfolio_drawdown_limit", 0.12) or 0.12)
    max_dd = max(equity * max(drawdown_limit_ratio, 0.0), 1e-9)

    return {
        "confidence_gate": {
            "value": round(conf_value, 6),
            "threshold": round(conf_threshold, 6),
            "passed": conf_value >= conf_threshold,
            "delta": round(conf_value - conf_threshold, 6),
        },
        "position_limit": {
            "current": round(pos_current, 6),
            "max": round(pos_max, 6),
            "passed": pos_current <= pos_max if pos_max > 0 else True,
            "delta": round((pos_max - pos_current) if pos_max > 0 else 0.0, 6),
        },
        "drawdown_guard": {
            "current_dd": round(drawdown, 6),
            "max_dd": round(max_dd, 6),
            "passed": drawdown <= max_dd,
            "delta": round(max_dd - drawdown, 6),
        },
    }


def _hold_reasons(confidence: Dict[str, float], risk_debug: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    conf_gate = risk_debug.get("confidence_gate", {})
    pos_gate = risk_debug.get("position_limit", {})
    dd_gate = risk_debug.get("drawdown_guard", {})

    risk_fail = 0.0
    if not bool(conf_gate.get("passed", True)):
        risk_fail = max(risk_fail, abs(float(conf_gate.get("delta", 0.0))))
    if not bool(pos_gate.get("passed", True)):
        denom = max(float(pos_gate.get("max", 0.0) or 0.0), 1.0)
        risk_fail = max(risk_fail, abs(float(pos_gate.get("delta", 0.0))) / denom)
    if not bool(dd_gate.get("passed", True)):
        denom = max(float(dd_gate.get("max_dd", 0.0) or 0.0), 1.0)
        risk_fail = max(risk_fail, abs(float(dd_gate.get("delta", 0.0))) / denom)

    ranked = [
        {"reason": "low confidence", "impact": _clamp01(float(conf_gate.get("threshold", 0.0)) - float(conf_gate.get("value", 0.0)))},
        {"reason": "strategy disagreement", "impact": _clamp01(1.0 - float(confidence.get("agreement", 0.0)))},
        {"reason": "regime mismatch", "impact": _clamp01(1.0 - float(confidence.get("regime_fit", 0.0)))},
        {"reason": "src.miniqs.risk gate failure", "impact": _clamp01(risk_fail)},
    ]
    ranked.sort(key=lambda row: float(row["impact"]), reverse=True)
    return [{"reason": row["reason"], "impact": round(float(row["impact"]), 6)} for row in ranked[:3]]


def _build_why_not_trade(
    history: List[Dict[str, Any]],
    controls: Dict[str, Any],
    control_risk: Dict[str, Any],
    strategy_health: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in history[-40:]:
        if str(row.get("action", "")).upper() != "HOLD":
            continue
        decision_row = {}
        raw_payload = row.get("raw") if isinstance(row.get("raw"), dict) else {}
        if isinstance(raw_payload.get("raw"), dict):
            decision_row = dict(raw_payload.get("raw") or {})

        synthetic_signal = {
            "strategy": row.get("strategy"),
            "side": row.get("signal"),
            "confidence": row.get("confidence"),
            "reason": row.get("reason"),
        }
        confidence = _confidence_decomposition(synthetic_signal, decision_row, strategy_health)
        portfolio_state = {
            "position_size": decision_row.get("position_size", 0.0),
            "drawdown": decision_row.get("drawdown", 0.0),
            "equity": decision_row.get("equity", 0.0),
        }
        debug = _risk_debug(confidence, portfolio_state, control_risk)
        reasons = _hold_reasons(confidence, debug)
        checks = [
            {
                "key": reason["reason"].replace(" ", "_"),
                "label": reason["reason"].title(),
                "passed": float(reason["impact"]) < 0.20,
                "reason": f"impact={float(reason['impact']):.3f}",
            }
            for reason in reasons
        ]
        out.append(
            {
                "ts": str(row.get("ts", "")),
                "action": "HOLD",
                "checks": checks,
                "reason": reasons[0]["reason"] if reasons else str(row.get("reason", "hold")),
            }
        )

    if not out:
        out.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "action": "HOLD",
                "checks": [
                    {"key": "low_confidence", "label": "Low Confidence", "passed": False, "reason": "impact=1.000"},
                    {"key": "strategy_disagreement", "label": "Strategy Disagreement", "passed": False, "reason": "impact=1.000"},
                    {"key": "regime_mismatch", "label": "Regime Mismatch", "passed": False, "reason": "impact=1.000"},
                ],
                "reason": "no_actionable_signal",
            }
        )
    return out[-30:]


def _counterfactual_replay(
    timeline: List[Dict[str, Any]],
    controls: Dict[str, Any],
    input_prices: List[float] | None = None,
    config_override: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    override = config_override or {}
    override_risk = override.get("src.miniqs.risk") if isinstance(override.get("src.miniqs.risk"), dict) else {}
    override_weights = override.get("strategy_weights") if isinstance(override.get("strategy_weights"), dict) else {}
    threshold = float(override.get("confidence_threshold", override_risk.get("confidence_threshold", controls.get("src.miniqs.risk", {}).get("confidence_threshold", 0.35))))
    max_pos = float(override_risk.get("max_position_size", controls.get("src.miniqs.risk", {}).get("max_position_size", 1.0)))

    prices = [float(row.get("price", 0.0)) for row in timeline]
    if input_prices:
        capped = [float(v) for v in input_prices[: len(prices)]]
        prices = capped + prices[len(capped) :]

    position = 0.0
    pnl_counterfactual = 0.0
    pnl_original = float(timeline[-1].get("pnl", 0.0)) if timeline else 0.0
    changed = 0
    original_decisions: List[str] = []
    counterfactual_decisions: List[str] = []

    for idx, row in enumerate(timeline):
        price = prices[idx] if idx < len(prices) else float(row.get("price", 0.0))
        if idx > 0:
            pnl_counterfactual += position * (price - prices[idx - 1])

        original_action = str(row.get("action", "HOLD")).upper()
        original_decisions.append(original_action)
        raw_payload = row.get("raw") if isinstance(row.get("raw"), dict) else {}
        decision_row = raw_payload.get("raw") if isinstance(raw_payload.get("raw"), dict) else {}
        signals = decision_row.get("src.miniqs.signals") if isinstance(decision_row.get("src.miniqs.signals"), dict) else {}

        buy_score = 0.0
        sell_score = 0.0
        buy_candidates: List[tuple[str, float]] = []
        sell_candidates: List[tuple[str, float]] = []
        for strategy, payload in signals.items():
            if not isinstance(payload, dict):
                continue
            side = str(payload.get("action", "hold")).lower()
            conf = float(payload.get("confidence", 0.0))
            weight = float(override_weights.get(strategy, 1.0))
            weighted_conf = max(0.0, conf * weight)
            if side == "buy":
                buy_score += weighted_conf
                buy_candidates.append((str(strategy), weighted_conf))
            elif side == "sell":
                sell_score += weighted_conf
                sell_candidates.append((str(strategy), weighted_conf))

        if max(buy_score, sell_score) < threshold:
            cf_action = "HOLD"
        else:
            if buy_score >= sell_score:
                cf_action = "BUY"
                if max_pos > 0 and position >= max_pos:
                    cf_action = "HOLD"
                elif cf_action == "BUY":
                    position += 1.0
            else:
                cf_action = "SELL"
                if max_pos > 0 and abs(position) >= max_pos:
                    cf_action = "HOLD"
                elif cf_action == "SELL":
                    position -= 1.0

        cf_public_action = "EXECUTE" if cf_action in {"BUY", "SELL"} else "HOLD"
        counterfactual_decisions.append(cf_public_action)
        if cf_public_action != original_action:
            changed += 1

    return {
        "original_decisions": original_decisions,
        "counterfactual_decisions": counterfactual_decisions,
        "counterfactual_result": {
            "changed_actions": int(changed),
            "pnl_original": round(float(pnl_original), 6),
            "pnl_counterfactual": round(float(pnl_counterfactual), 6),
            "delta": round(float(pnl_counterfactual - pnl_original), 6),
        },
    }


def _build_decision_inspector(
    latest_signal: Dict[str, Any],
    latest_risk: Dict[str, Any],
    controls: Dict[str, Any],
    control_risk: Dict[str, Any],
    confidence: Dict[str, float],
    hold_reasons: List[Dict[str, Any]],
    risk_debug: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    decision_row = _latest_decision_row(latest_signal)
    features: Dict[str, Any] = {
        "signal_context": {
            "strategy": str(latest_signal.get("strategy", "pending")),
            "side": str(latest_signal.get("side", "HOLD")).upper(),
            "confidence": confidence,
            "reason": str(latest_signal.get("reason", "waiting for stream")),
        },
        "hold_reasons": hold_reasons,
        "risk_debug": risk_debug,
    }

    if decision_row:
        for key in (
            "tick",
            "stage",
            "timestamp",
            "price",
            "position_size",
            "equity",
            "total_pnl",
            "executed_trades",
            "decision",
            "detail",
        ):
            if key in decision_row:
                features[key] = decision_row.get(key)
        for nested_key in ("src.miniqs.signals", "chosen", "evaluator", "src.miniqs.risk"):
            nested = decision_row.get(nested_key)
            if isinstance(nested, dict):
                features[nested_key] = nested

    checks: List[Dict[str, Any]] = []
    for gate_name, gate in risk_debug.items():
        checks.append(
            {
                "key": gate_name,
                "label": gate_name.replace("_", " ").title(),
                "passed": bool(gate.get("passed", False)),
                "reason": f"delta={float(gate.get('delta', 0.0)):.6f}",
            }
        )

    latest_risk_type = str(latest_risk.get("risk_type", "")).strip()
    if latest_risk_type:
        checks.append(
            {
                "key": "latest_risk_event",
                "label": "Latest Risk Event",
                "passed": str(latest_risk.get("severity", "info")).lower() not in {"warn", "error"},
                "reason": f"{latest_risk_type}: {str(latest_risk.get('reason', ''))}",
            }
        )

    if not checks:
        checks = [{"key": "no_checks", "label": "No Checks", "passed": False, "reason": "system initializing"}]

    return {
        "full_object": latest_signal,
        "features": features,
        "risk_checks": checks,
        "reasoning": str(latest_signal.get("reason", "waiting for stream")),
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
    latest_risk = latest.get("src.miniqs.risk") or {}
    controls = _control_copy()
    control_risk = controls.get("src.miniqs.risk", {}) if isinstance(controls.get("src.miniqs.risk"), dict) else {}
    control_asset = controls.get("asset", {}) if isinstance(controls.get("asset"), dict) else {}
    active_symbol = str(control_asset.get("symbol") or "BTC/USD")
    synced_strategy_registry = [name for name in SUPPORTED_STRATEGIES]
    control_strategies = controls.get("src.miniqs.strategies", {}) if isinstance(controls.get("src.miniqs.strategies"), dict) else {}
    missing_strategy_controls = [name for name in synced_strategy_registry if name not in control_strategies]

    open_orders = []
    for order in reversed(order_events[-30:]):
        state = str(order["payload"].get("state", "")).lower()
        if state in {"filled", "canceled", "rejected"}:
            continue
        open_orders.append(
            {
                "id": str(order["payload"].get("order_id", "")),
                "status": state,
                "symbol": order.get("symbol") or active_symbol,
                "price": float(order["payload"].get("fill_price", order["payload"].get("expected_price", 0.0))),
            }
        )
        if len(open_orders) >= 6:
            break

    alerts = [
        {
            "level": "error" if str(ev["payload"].get("severity", "warn")) == "error" else "warn",
            "message": str(ev["payload"].get("reason", "src.miniqs.risk event")),
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

    strategy_health = _strategy_health(history, synced_strategy_registry, window=80)
    decision_row = _latest_decision_row(latest_signal)
    confidence_breakdown = _confidence_decomposition(latest_signal, decision_row, strategy_health)
    risk_debug = _risk_debug(confidence_breakdown, latest_portfolio, control_risk)
    hold_reasons = _hold_reasons(confidence_breakdown, risk_debug)
    why_not_trade = _build_why_not_trade(history, controls, control_risk, strategy_health)
    replay_timeline = history[-100:]
    counterfactual_bundle = _counterfactual_replay(replay_timeline, controls)
    decision_reason = str(latest_signal.get("reason", "waiting for stream"))
    if signal_side == "HOLD" and hold_reasons:
        decision_reason = f"{decision_reason} | primary blocker: {hold_reasons[0]['reason']}"

    return {
        "decision": {
            "signal": {
                "side": signal_side,
                "confidence": confidence_breakdown,
                "strategy": str(latest_signal.get("strategy", "pending")),
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
                "reason": decision_reason,
                "pipeline": {
                    "signal": "done" if signal_side != "HOLD" else "idle",
                    "decision": "done" if signal_side != "HOLD" else "idle",
                    "sent": "done" if order_events else "idle",
                    "filled": "done" if any(str(o["payload"].get("state", "")).lower() == "filled" for o in order_events[-20:]) else "idle",
                },
            },
            "position": {
                "symbol": active_symbol,
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
            "asset": control_asset,
            "app_contract": {
                "strategy_registry": synced_strategy_registry,
                "risk_parameters": list(SUPPORTED_RISK_FIELDS),
                "missing_strategy_controls": missing_strategy_controls,
            },
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
            "risk_per_trade": float(control_risk.get("risk_per_trade", 0.01)),
            "max_exposure": float(control_risk.get("max_exposure", 1.0)),
            "cooldown_seconds": int(control_risk.get("cooldown_seconds", 5)),
            "portfolio_drawdown_limit": float(control_risk.get("portfolio_drawdown_limit", 0.12)),
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
        "why_not_trade": why_not_trade,
        "hold_reasons": hold_reasons,
        "strategy_intelligence": _strategy_intelligence(history),
        "strategy_health": strategy_health,
        "risk_debug": risk_debug,
        "decision_inspector": _build_decision_inspector(
            latest_signal,
            latest_risk,
            controls,
            control_risk,
            confidence_breakdown,
            hold_reasons,
            risk_debug,
        ),
        "counterfactuals": [],
        "counterfactual_result": counterfactual_bundle.get("counterfactual_result", {}),
        "performance": perf,
        "replay": {
            "cursor": len(history) - 1,
            "length": len(replay_timeline),
            "timeline": replay_timeline,
        },
        "alerts": alerts,
        "health_report": latest.get("health_report", {}).get("report", "No report available yet. Station is currently optimizing...")
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


@app.post("/api/replay/counterfactual")
def replay_counterfactual(payload: ReplayForkRequest) -> Dict[str, Any]:
    snap = _snapshot()
    replay_data = snap.get("replay", {}) if isinstance(snap.get("replay"), dict) else {}
    timeline = replay_data.get("timeline", []) if isinstance(replay_data.get("timeline"), list) else []
    controls = snap.get("meta", {}).get("controls", {}) if isinstance(snap.get("meta"), dict) else {}
    return _counterfactual_replay(
        timeline=[row for row in timeline if isinstance(row, dict)],
        controls=controls if isinstance(controls, dict) else {},
        input_prices=payload.input_prices,
        config_override=payload.config_override,
    )


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
    if strategy not in SUPPORTED_STRATEGIES:
        raise HTTPException(status_code=404, detail=f"Unknown strategy: {strategy}")
    state.setdefault("src.miniqs.strategies", {})
    for strategy_name in SUPPORTED_STRATEGIES:
        state["src.miniqs.strategies"].setdefault(strategy_name, True)
    state["src.miniqs.strategies"][strategy] = payload.enabled
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


@app.post("/api/control/asset")
async def control_asset(payload: AssetUpdateRequest) -> Dict[str, Any]:
    state = _control_copy()
    resolved = resolve_asset_config(
        symbol=payload.symbol,
        asset_type=payload.asset_type,
        market_hours=payload.market_hours,
        trading_fees=payload.trading_fees,
    )
    state["asset"] = {
        "symbol": resolved.symbol,
        "asset_type": resolved.asset_type,
        "market_hours": (
            {
                "open": resolved.market_hours.open,
                "close": resolved.market_hours.close,
                "timezone": resolved.market_hours.timezone,
            }
            if resolved.market_hours
            else None
        ),
        "trading_fees": resolved.trading_fees,
    }
    state["portfolio_reset_requested_at"] = datetime.now(timezone.utc).isoformat()
    persisted = _persist_control(state)
    await ENGINE.emit(
        EventMessage(
            event_type="risk_event",
            source="control",
            strategy_id="system",
            symbol=resolved.symbol,
            payload={
                "risk_type": "control",
                "severity": "info",
                "reason": f"asset switched to {resolved.symbol} ({resolved.asset_type})",
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
        if key not in SUPPORTED_RISK_FIELDS:
            raise HTTPException(status_code=400, detail=f"Unsupported risk parameter: {key}")
        state.setdefault("src.miniqs.risk", {})[key] = int(value) if key in INT_RISK_FIELDS else float(value)
    persisted = _persist_control(state)
    await ENGINE.emit(
        EventMessage(
            event_type="risk_event",
            source="control",
            strategy_id="system",
            payload={"risk_type": "control", "severity": "info", "reason": "src.miniqs.risk parameters updated", "updates": updates},
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
