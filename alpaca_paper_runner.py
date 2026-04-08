"""Run the Mini Quant pipeline against Alpaca Paper Trading (live data + broker fills).

Prerequisites:
- Environment: ``ALPACA_API_KEY_ID`` and ``ALPACA_API_SECRET_KEY`` (paper account keys).
- Optional: ``ALPACA_SYMBOLS=SPY`` (comma-separated), ``ALPACA_MAX_TICKS=500`` for bounded runs.

Market data WebSocket: ``stream.data.alpaca.markets`` (see ``alpaca_config``).
Trading REST + order stream: ``https://paper-api.alpaca.markets`` and ``wss://paper-api.alpaca.markets/stream``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from alpaca_config import AlpacaConfig
from alpaca_data_stream import stream_alpaca_ticks
from alpaca_execution import AlpacaPaperExecutionEngine
from alpaca_http import AlpacaPaperClient
from alpaca_trading_stream import run_trading_stream_listener
from event_bus import EventBus, EventDispatcher, FillEvent, MarketEvent, OrderEvent, SignalEvent
from feature_engine import FeatureEngine
from live_dashboard import append_csv_row, append_jsonl, dashboard_row, write_snapshot
from logger import QuantLogger
from main import FeedbackLoop
from performance import PerformanceTracker
from portfolio import Portfolio
from risk_manager import check_risk
from strategies import FunctionStrategy, StrategyRegistry, generate_weighted_signals
from strategies.mean_reversion import generate_signal as mean_reversion_signal  # backward-compatible test patch target
from strategies.momentum import generate_signal as momentum_signal  # backward-compatible test patch target
from strategies.volatility_breakout import generate_signal as volatility_breakout_signal  # backward-compatible test patch target
from strategy_evaluator import emit_signal_event, evaluate_signals_v2
from quant_control_state import load_control_state

_log = logging.getLogger(__name__)

DASHBOARD_CSV_FIELDS = [
    "ts",
    "event",
    "symbol",
    "total_pnl",
    "win_rate",
    "max_drawdown",
    "sharpe_ratio",
    "equity",
    "executed_trades",
    "weights_mr",
    "weights_mo",
    "weights_vb",
]

DEFAULT_STRATEGY_NORMALIZATION = {"mean_reversion": 1.05, "momentum": 0.9, "volatility_breakout": 1.1}
DEFAULT_DOMINANCE_CAP = 0.65


def _strategy_registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(
        FunctionStrategy(
            name="mean_reversion",
            generator=lambda features, **params: mean_reversion_signal(features, entry_threshold=float(params.get("entry_threshold", 0.003))),
        )
    )
    registry.register(
        FunctionStrategy(
            name="momentum",
            generator=lambda features, **params: momentum_signal(features, momentum_threshold=float(params.get("momentum_threshold", 0.002))),
        )
    )
    registry.register(
        FunctionStrategy(
            name="volatility_breakout",
            generator=lambda features, **params: volatility_breakout_signal(features, breakout_factor=float(params.get("breakout_factor", 1.2))),
        )
    )
    return registry


def _feature_engines(config: AlpacaConfig) -> Dict[str, FeatureEngine]:
    return {
        s.upper(): FeatureEngine(
            ma_window=20,
            long_ma_window=50,
            vol_window=20,
            momentum_window=10,
            debug=False,
        )
        for s in config.symbols
    }


def _stage_message(stage: str, detail: str = "") -> str:
    messages = {
        "warmup": "warming up feature windows and waiting for enough market data",
        "signals_generated": "market data is ready and trade signals are being generated",
        "no_signal": "no trade passed the confidence filter, so the bot is holding",
        "risk_check": "a candidate trade passed signal selection and is being checked for risk",
        "risk_blocked": "a trade was blocked by the risk manager",
        "trade_submission": "a paper order is being submitted to Alpaca",
        "trade_executed": "a paper order filled and the local portfolio was updated",
        "market_data_tick": "market data is connected and the loop is processing ticks",
    }
    base = messages.get(stage, stage.replace("_", " "))
    return f"{base}{f' ({detail})' if detail else ''}"


def _emit_heartbeat(
    *,
    cfg: AlpacaConfig,
    tick_counter: int,
    stage: str,
    primary: str,
    executed_trades: int,
    state: Dict[str, float],
    metrics: Dict[str, float],
    detail: str = "",
    trace: str = "",
) -> None:
    if cfg.status_heartbeat_ticks <= 0:
        return
    if tick_counter % cfg.status_heartbeat_ticks != 0:
        return

    _log.info(
        "[alpaca_heartbeat] tick=%s stage=%s symbol=%s trades=%s equity=%.2f pnl=%.4f win_rate=%.2f sharpe=%.3f%s",
        tick_counter,
        _stage_message(stage, detail),
        primary,
        executed_trades,
        float(state.get("equity", 0.0)),
        float(metrics.get("total_pnl", 0.0)),
        float(metrics.get("win_rate", 0.0)),
        float(metrics.get("sharpe_ratio", 0.0)),
        f" detail={detail}" if detail else "",
    )
    if trace:
        _log.info("[alpaca_brain] tick=%s %s", tick_counter, trace)


def _log_trading_connection_event(logger_obj: QuantLogger, component: str, event: str, detail: str) -> None:
    logger_obj.log_connection_event(component, event, detail)
    _log.info("[%s] %s%s", component, event, f": {detail}" if detail else "")


def _write_brain_trace(cfg: AlpacaConfig, row: Dict[str, object]) -> None:
    append_jsonl(cfg.brain_trace_jsonl, row)


def _select_signal(
    *,
    mr: Any,
    mo: Any,
    vb: Any,
    confidence_threshold: float,
    profile: str,
) -> Any:
    """Resolve the final signal with ensemble evaluator defaults in one place.

    Keeping selection defaults centralized reduces merge friction when strategy
    tuning changes across branches.
    """
    return evaluate_signals_v2(
        [mr, mo, vb],
        confidence_threshold=confidence_threshold,
        profile=profile,
        strategy_normalization=DEFAULT_STRATEGY_NORMALIZATION,
        dominance_cap=DEFAULT_DOMINANCE_CAP,
    )


@dataclass
class AlpacaRuntime:
    cfg: AlpacaConfig
    logger: QuantLogger
    perf: PerformanceTracker
    feedback: FeedbackLoop
    portfolio: Portfolio
    alpaca_exec: AlpacaPaperExecutionEngine
    strategy_registry: StrategyRegistry
    engines: Dict[str, FeatureEngine]
    primary: str
    initial_equity: float
    tick_counter: int = 0
    executed_trades: int = 0
    last_trade_timestamp: Optional[str] = None


def _on_market_event(event: MarketEvent, bus: EventBus, runtime: AlpacaRuntime) -> None:
    tick = event.tick
    runtime.tick_counter += 1
    stage = "market_data_tick"
    if runtime.cfg.status_heartbeat_ticks > 0 and runtime.tick_counter % runtime.cfg.status_heartbeat_ticks == 0:
        _log.info(
            "[alpaca_runner] received tick=%s symbol=%s price=%.4f",
            runtime.tick_counter,
            tick.symbol,
            tick.price,
        )

    if tick.symbol not in runtime.engines:
        return
    snap = runtime.engines[tick.symbol].update(tick)
    if tick.symbol != runtime.primary:
        return

    runtime.portfolio.update_pnl(tick.price)
    state = runtime.portfolio.get_portfolio_state()
    runtime.perf.record_equity(float(state["equity"]))
    runtime.logger.log_portfolio_snapshot(state)
    metrics = runtime.perf.compute_metrics(latest_total_pnl=float(state["total_pnl"]))

    control_state = load_control_state()
    control_risk = control_state.get("risk", {}) if isinstance(control_state.get("risk"), dict) else {}
    dynamic_conf_threshold = float(control_risk.get("confidence_threshold", runtime.cfg.confidence_threshold))
    dynamic_max_position = float(control_risk.get("max_position_size", runtime.cfg.max_position_size))
    dynamic_max_daily_loss = float(control_risk.get("max_daily_loss", runtime.cfg.max_loss_per_session))
    strategy_switches = control_state.get("strategies", {}) if isinstance(control_state.get("strategies"), dict) else {}

    base_trace: Dict[str, object] = {
        "kind": "decision",
        "tick": runtime.tick_counter,
        "symbol": tick.symbol,
        "stage": stage,
        "timestamp": tick.timestamp.isoformat(),
        "price": float(tick.price),
        "position_size": float(state["position_size"]),
        "equity": float(state["equity"]),
        "total_pnl": float(state["total_pnl"]),
        "executed_trades": runtime.executed_trades,
        "controls": control_state,
    }

    if snap is None:
        stage = "warmup"
        _write_brain_trace(
            runtime.cfg,
            {
                **base_trace,
                "stage": stage,
                "detail": "feature_window_not_ready",
                "signals": None,
                "decision": "warmup",
            },
        )
        _emit_heartbeat(
            cfg=runtime.cfg,
            tick_counter=runtime.tick_counter,
            stage=stage,
            primary=runtime.primary,
            executed_trades=runtime.executed_trades,
            state=state,
            metrics=metrics,
            detail="feature_window_not_ready",
            trace=f"price={tick.price:.4f} feature_engine=warming_up signals=pending",
        )
        if runtime.tick_counter % 100 == 0:
            _write_dashboard(runtime.cfg, metrics, runtime.feedback, runtime.primary, runtime.executed_trades, "warmup", state)
        return

    stage = "signals_generated"
    weights = runtime.feedback.strategy_weights
    signals = generate_weighted_signals(
        features=snap,
        registry=runtime.strategy_registry,
        weights=weights,
        enabled={
            "mean_reversion": bool(strategy_switches.get("mean_reversion", True)),
            "momentum": bool(strategy_switches.get("momentum", True)),
            "volatility_breakout": bool(strategy_switches.get("volatility_breakout", True)),
        },
        params={
            "mean_reversion": {"entry_threshold": runtime.cfg.mr_threshold},
            "momentum": {"momentum_threshold": runtime.cfg.mom_threshold},
            "volatility_breakout": {"breakout_factor": runtime.cfg.vb_breakout_factor},
        },
    )
    mr = signals["mean_reversion"]
    mo = signals["momentum"]
    vb = signals["volatility_breakout"]

    runtime.logger.log_signal(mr.strategy, mr.action, mr.confidence, mr.reason)
    runtime.logger.log_signal(mo.strategy, mo.action, mo.confidence, mo.reason)
    runtime.logger.log_signal(vb.strategy, vb.action, vb.confidence, vb.reason)

    signal_trace = (
        f"price={tick.price:.4f} "
        f"mr={mr.action}:{mr.confidence:.3f}:{mr.reason} "
        f"mo={mo.action}:{mo.confidence:.3f}:{mo.reason} "
        f"vb={vb.action}:{vb.confidence:.3f}:{vb.reason}"
    )
    signal_payload = {
        "mean_reversion": {"action": mr.action, "confidence": mr.confidence, "reason": mr.reason},
        "momentum": {"action": mo.action, "confidence": mo.confidence, "reason": mo.reason},
        "volatility_breakout": {"action": vb.action, "confidence": vb.confidence, "reason": vb.reason},
    }

    chosen = _select_signal(
        mr=mr,
        mo=mo,
        vb=vb,
        confidence_threshold=dynamic_conf_threshold,
        profile=runtime.cfg.evaluation_profile,
    )
    if chosen is None:
        stage = "no_signal"
        if (
            not bool(strategy_switches.get("mean_reversion", True))
            and not bool(strategy_switches.get("momentum", True))
            and not bool(strategy_switches.get("volatility_breakout", True))
        ):
            no_signal_reason = "all_strategies_disabled"
        else:
            no_signal_reason = "confidence_below_threshold"
        _write_brain_trace(
            runtime.cfg,
            {
                **base_trace,
                "stage": stage,
                "signals": signal_payload,
                "decision": "hold",
                "chosen": None,
                "risk": None,
                "detail": no_signal_reason,
            },
        )
        _emit_heartbeat(
            cfg=runtime.cfg,
            tick_counter=runtime.tick_counter,
            stage=stage,
            primary=runtime.primary,
            executed_trades=runtime.executed_trades,
            state=state,
            metrics=metrics,
            detail=no_signal_reason,
            trace=signal_trace + " chosen=none",
        )
        if runtime.tick_counter % 50 == 0:
            _write_dashboard(runtime.cfg, metrics, runtime.feedback, runtime.primary, runtime.executed_trades, "no_signal", state)
        return

    if not bool(control_state.get("trading_enabled", True)) or bool(control_state.get("kill_switch", False)):
        stage = "trading_stopped"
        reason = "kill_switch_engaged" if bool(control_state.get("kill_switch", False)) else "trading_disabled"
        _write_brain_trace(
            runtime.cfg,
            {
                **base_trace,
                "stage": stage,
                "signals": signal_payload,
                "chosen": {
                    "strategy": chosen.strategy,
                    "action": chosen.action,
                    "confidence": chosen.confidence,
                    "reason": chosen.reason,
                },
                "risk": {"allowed": False, "reason": reason},
                "detail": reason,
            },
        )
        _emit_heartbeat(
            cfg=runtime.cfg,
            tick_counter=runtime.tick_counter,
            stage=stage,
            primary=runtime.primary,
            executed_trades=runtime.executed_trades,
            state=state,
            metrics=metrics,
            detail=reason,
            trace=signal_trace + f" control={reason}",
        )
        return

    signal_trace += f" chosen={chosen.strategy}:{chosen.action}:{chosen.confidence:.3f}:{chosen.reason}"
    trade = {
        "action": chosen.action,
        "size": runtime.cfg.trade_size,
        "confidence": chosen.confidence,
        "price": tick.price,
        "timestamp": tick.timestamp.isoformat(),
        "strategy": chosen.strategy,
        "symbol": runtime.primary,
    }
    risk_state: Dict[str, Any] = {
        "current_position": float(state["position_size"]),
        "last_trade_timestamp": runtime.last_trade_timestamp,
        "session_loss": max(0.0, -float(state["total_pnl"])),
        "max_position_size": dynamic_max_position,
        "cooldown_seconds": runtime.cfg.cooldown_seconds,
        "max_loss_per_session": dynamic_max_daily_loss,
        "daily_loss_limit": runtime.cfg.daily_loss_limit,
        "risk_per_trade": runtime.cfg.risk_per_trade,
        "confidence_threshold": dynamic_conf_threshold,
        "equity": float(state["equity"]),
        "_meta": {
            "base_trace": base_trace,
            "signal_payload": signal_payload,
            "chosen": {
                "strategy": chosen.strategy,
                "action": chosen.action,
                "confidence": chosen.confidence,
                "reason": chosen.reason,
            },
            "signal_trace": signal_trace,
            "state": state,
            "metrics": metrics,
        },
    }
    emit_signal_event(bus=bus, chosen=chosen, trade=trade, risk_state=risk_state)


def _on_signal_event(event: SignalEvent, bus: EventBus, runtime: AlpacaRuntime) -> None:
    meta = event.risk_state.get("_meta", {}) if isinstance(event.risk_state.get("_meta"), dict) else {}
    allow, risk_reason = check_risk(event.trade, event.risk_state)
    if not allow:
        stage = "risk_blocked"
        base_trace = meta.get("base_trace", {}) if isinstance(meta.get("base_trace"), dict) else {}
        signal_payload = meta.get("signal_payload", {}) if isinstance(meta.get("signal_payload"), dict) else {}
        chosen = meta.get("chosen", {}) if isinstance(meta.get("chosen"), dict) else {}
        _write_brain_trace(
            runtime.cfg,
            {
                **base_trace,
                "stage": stage,
                "signals": signal_payload,
                "chosen": chosen,
                "risk": {"allowed": False, "reason": risk_reason},
                "trade": event.trade,
            },
        )
        _emit_heartbeat(
            cfg=runtime.cfg,
            tick_counter=runtime.tick_counter,
            stage=stage,
            primary=runtime.primary,
            executed_trades=runtime.executed_trades,
            state=meta.get("state", {}),
            metrics=meta.get("metrics", {}),
            detail=risk_reason,
            trace=str(meta.get("signal_trace", "")) + f" risk=blocked:{risk_reason}",
        )
        runtime.logger.log_risk_block(risk_reason, json.dumps(event.trade, default=str))
        return

    trade_with_meta = dict(event.trade)
    trade_with_meta["_meta"] = meta
    bus.publish(OrderEvent(strategy=event.strategy, trade=trade_with_meta, reason="allowed"))


def _on_order_event(event: OrderEvent, bus: EventBus, runtime: AlpacaRuntime) -> None:
    trade = dict(event.trade)
    meta = trade.pop("_meta", None)
    try:
        result = runtime.alpaca_exec.execute_trade(trade)
    except Exception as exc:  # noqa: BLE001
        _log.exception("Alpaca execution failed: %s", exc)
        runtime.logger.log_connection_event("execution", "error", str(exc))
        base_trace = meta.get("base_trace", {}) if isinstance(meta, dict) and isinstance(meta.get("base_trace"), dict) else {}
        signal_payload = meta.get("signal_payload", {}) if isinstance(meta, dict) and isinstance(meta.get("signal_payload"), dict) else {}
        chosen = meta.get("chosen", {}) if isinstance(meta, dict) and isinstance(meta.get("chosen"), dict) else {}
        _write_brain_trace(
            runtime.cfg,
            {
                **base_trace,
                "stage": "trade_submission_failed",
                "signals": signal_payload,
                "chosen": chosen,
                "risk": {"allowed": True, "reason": event.reason},
                "trade": trade,
                "error": str(exc),
            },
        )
        return

    fill_trade = dict(trade)
    fill_trade["_meta"] = meta
    bus.publish(FillEvent(strategy=event.strategy, trade=fill_trade, result=result))


def _on_fill_event(event: FillEvent, bus: EventBus, runtime: AlpacaRuntime) -> None:
    meta = event.trade.get("_meta", {}) if isinstance(event.trade.get("_meta"), dict) else {}
    runtime.last_trade_timestamp = str(event.trade.get("timestamp", ""))
    runtime.executed_trades += 1
    runtime.logger.log_trade(event.result, strategy=event.strategy)
    runtime.perf.record_trade(float(event.result["realized_pnl_trade"]))
    runtime.perf.record_strategy_trade(event.strategy, float(event.result["realized_pnl_trade"]))

    st2 = runtime.portfolio.get_portfolio_state()
    metrics = runtime.perf.compute_metrics(latest_total_pnl=float(st2["total_pnl"]))
    _write_dashboard(runtime.cfg, metrics, runtime.feedback, runtime.primary, runtime.executed_trades, "trade", st2)

    base_trace = meta.get("base_trace", {}) if isinstance(meta.get("base_trace"), dict) else {}
    signal_payload = meta.get("signal_payload", {}) if isinstance(meta.get("signal_payload"), dict) else {}
    chosen = meta.get("chosen", {}) if isinstance(meta.get("chosen"), dict) else {}
    _write_brain_trace(
        runtime.cfg,
        {
            **base_trace,
            "stage": "trade_executed",
            "signals": signal_payload,
            "chosen": chosen,
            "risk": {"allowed": True, "reason": "allowed"},
            "executed_trades": runtime.executed_trades,
            "executed_trades_before": max(0, runtime.executed_trades - 1),
            "trade": event.result,
            "portfolio_after": st2,
        },
    )

    _emit_heartbeat(
        cfg=runtime.cfg,
        tick_counter=runtime.tick_counter,
        stage="trade_executed",
        primary=runtime.primary,
        executed_trades=runtime.executed_trades,
        state=st2,
        metrics=metrics,
        detail=f"order_id={event.result.get('alpaca_order_id', '')}",
        trace=str(meta.get("signal_trace", "")) + f" trade=executed:{event.result.get('alpaca_order_id', '')}:{event.result.get('price', 0.0):.4f}",
    )

    if runtime.executed_trades % runtime.cfg.feedback_trade_interval == 0:
        strategy_metrics = runtime.perf.strategy_metrics_for_feedback()
        if strategy_metrics:
            runtime.feedback.update(strategy_metrics, logger=runtime.logger)

    if runtime.tick_counter % 200 == 0:
        st_chk = runtime.portfolio.get_portfolio_state()
        if float(st_chk["equity"]) < 0.8 * runtime.initial_equity:
            runtime.logger.log_connection_event(
                "monitor",
                "equity_drawdown_warning",
                f"equity={st_chk['equity']} initial={runtime.initial_equity}",
            )


async def run_alpaca_paper_session(config: Optional[AlpacaConfig] = None) -> Dict[str, float]:
    """Alpaca paper: market data WS + optional trading WS + REST execution + feedback loop."""
    cfg = config or AlpacaConfig.from_env()
    Path(cfg.db_dir).mkdir(parents=True, exist_ok=True)

    _log.info(
        "[alpaca_runner] starting paper session: symbols=%s primary=%s data_feed=%s max_ticks=%s heartbeat_every=%s",
        ",".join(cfg.symbols),
        cfg.symbols[0].upper(),
        cfg.data_feed,
        cfg.max_ticks if cfg.max_ticks is not None else "unbounded",
        cfg.status_heartbeat_ticks,
    )
    _log.info(
        "[alpaca_runner] what will be performed: connect the data stream, connect the trade logic loop, warm up features, generate signals, run risk checks, submit paper orders, wait for fills, and log/report state"
    )

    _write_brain_trace(
        cfg,
        {
            "kind": "startup",
            "symbols": cfg.symbols,
            "primary": cfg.symbols[0].upper(),
            "data_feed": cfg.data_feed,
            "data_ws_url": cfg.data_ws_url,
            "trade_size": cfg.trade_size,
            "status_heartbeat_ticks": cfg.status_heartbeat_ticks,
        },
    )

    client = AlpacaPaperClient(cfg.api_key_id, cfg.api_secret_key, cfg.rest_base_url)
    initial_cash = 100_000.0
    if cfg.sync_initial_cash_from_alpaca:
        acct = client.get_account()
        initial_cash = float(acct.get("cash", initial_cash))

    portfolio = Portfolio(
        db_path=str(Path(cfg.db_dir) / "alpaca_portfolio.db"),
        initial_cash=initial_cash,
        fee_rate=cfg.portfolio_fee_rate,
    )
    alpaca_exec = AlpacaPaperExecutionEngine(
        portfolio=portfolio,
        client=client,
        paper_mode=True,
        debug=True,
        fill_timeout_seconds=cfg.order_fill_timeout_seconds,
        poll_interval=cfg.order_poll_interval_seconds,
        max_retries=cfg.execution_max_retries,
        retry_backoff_seconds=cfg.execution_retry_backoff_seconds,
    )

    logger = QuantLogger(db_path=str(Path(cfg.db_dir) / "alpaca_logs.db"))
    perf = PerformanceTracker(initial_equity=initial_cash)
    feedback = FeedbackLoop()
    engines = _feature_engines(cfg)
    primary = cfg.symbols[0].upper()
    initial_equity = initial_cash

    runtime = AlpacaRuntime(
        cfg=cfg,
        logger=logger,
        perf=perf,
        feedback=feedback,
        portfolio=portfolio,
        alpaca_exec=alpaca_exec,
        strategy_registry=_strategy_registry(),
        engines=engines,
        primary=primary,
        initial_equity=initial_equity,
    )
    bus = EventBus()
    dispatcher = EventDispatcher()
    dispatcher.register(MarketEvent, _on_market_event)
    dispatcher.register(SignalEvent, _on_signal_event)
    dispatcher.register(OrderEvent, _on_order_event)
    dispatcher.register(FillEvent, _on_fill_event)

    stop_trading_ws = asyncio.Event()

    def on_trade_msg(_stream: str, payload: Dict[str, object]) -> None:
        ev = str(payload.get("event", ""))
        logger.log_trade_update_event(ev, payload)
        if ev:
            _log.info("[alpaca_trade_update] event=%s", ev)
            _write_brain_trace(
                cfg,
                {
                    "kind": "trade_update",
                    "event": ev,
                    "payload": payload,
                },
            )

    def on_trading_connection_event(component: str, detail: str) -> None:
        _log_trading_connection_event(logger, "trading_ws", component, detail)
        if component == "connected":
            _log.info("[alpaca_runner] trade logic connected")
        elif component == "authenticated":
            _log.info("[alpaca_runner] trade logic authenticated")
        elif component == "subscribed":
            _log.info("[alpaca_runner] trade update subscription active")
        elif component == "listening":
            _log.info("[alpaca_runner] trade update loop connected")
        elif component == "auth_failed":
            _log.info("[alpaca_runner] trade logic authentication failed")
        elif component == "auth_timeout":
            _log.info("[alpaca_runner] trade logic authentication timeout")
        elif component == "reconnecting":
            _log.info("[alpaca_runner] trade updates reconnecting")
        _write_brain_trace(
            cfg,
            {
                "kind": "connection",
                "component": "trading_ws",
                "event": component,
                "detail": detail,
            },
        )

    trading_task = asyncio.create_task(
        run_trading_stream_listener(
            ws_url=cfg.trading_ws_url,
            api_key_id=cfg.api_key_id,
            api_secret_key=cfg.api_secret_key,
            on_message=on_trade_msg,
            on_connection_event=on_trading_connection_event,
            stop_event=stop_trading_ws,
        )
    )

    def on_md_event(event: str, detail: str) -> None:
        logger.log_connection_event("market_data_ws", event, detail)
        _log.info("[alpaca_data_stream] %s%s", event, f": {detail}" if detail else "")
        if event == "market_data" and detail == "connected":
            _log.info("[alpaca_runner] data stream connected")
        elif event == "market_data" and detail.startswith("subscribed"):
            _log.info("[alpaca_runner] data stream subscription active")
        elif event == "market_data_auth_failed":
            _log.info("[alpaca_runner] data stream authentication failed")
        elif event == "market_data_reconnecting":
            _log.info("[alpaca_runner] data stream reconnecting")
        _write_brain_trace(
            cfg,
            {
                "kind": "connection",
                "component": "market_data_ws",
                "event": event,
                "detail": detail,
            },
        )

    try:
        async for tick in stream_alpaca_ticks(cfg, on_connection_event=on_md_event):
            bus.publish(MarketEvent(tick=tick))
            while len(bus) > 0:
                next_event = bus.consume()
                if next_event is None:
                    break
                dispatcher.dispatch(next_event, bus, runtime)

    except KeyboardInterrupt:
        _log.info("Session interrupted by user")

    finally:
        stop_trading_ws.set()
        trading_task.cancel()
        try:
            await trading_task
        except asyncio.CancelledError:
            pass

    final_state = portfolio.get_portfolio_state()
    metrics = perf.compute_metrics(latest_total_pnl=float(final_state["total_pnl"]))
    logger.log_performance_metrics(metrics)

    return {
        "executed_trades": float(runtime.executed_trades),
        "total_pnl": float(metrics["total_pnl"]),
        "win_rate": float(metrics["win_rate"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "sharpe_ratio": float(metrics["sharpe_ratio"]),
        "mean_reversion_weight": float(runtime.feedback.strategy_weights["mean_reversion"]),
        "momentum_weight": float(runtime.feedback.strategy_weights["momentum"]),
        "volatility_breakout_weight": float(runtime.feedback.strategy_weights.get("volatility_breakout", 0.0)),
        "ticks_processed": float(runtime.tick_counter),
    }


def _write_dashboard(
    cfg: AlpacaConfig,
    metrics: Dict[str, float],
    feedback: FeedbackLoop,
    primary: str,
    executed_trades: int,
    event: str,
    state: Dict[str, float],
) -> None:
    w = feedback.strategy_weights
    row = dashboard_row(
        event=event,
        metrics=metrics,
        weights=w,
        symbol=primary,
        extra={"executed_trades": executed_trades, "equity": float(state.get("equity", 0.0))},
    )
    append_jsonl(cfg.dashboard_jsonl, row)
    write_snapshot(
        cfg.dashboard_snapshot_json,
        {
            "latest": row,
            "weights": dict(w),
        },
    )
    append_csv_row(
        cfg.dashboard_csv,
        DASHBOARD_CSV_FIELDS,
        {
            "ts": row["ts"],
            "event": event,
            "symbol": primary,
            "total_pnl": metrics.get("total_pnl", 0.0),
            "win_rate": metrics.get("win_rate", 0.0),
            "max_drawdown": metrics.get("max_drawdown", 0.0),
            "sharpe_ratio": metrics.get("sharpe_ratio", 0.0),
            "equity": float(state.get("equity", 0.0)),
            "executed_trades": executed_trades,
            "weights_mr": w.get("mean_reversion"),
            "weights_mo": w.get("momentum"),
            "weights_vb": w.get("volatility_breakout"),
        },
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        asyncio.run(run_alpaca_paper_session())
        _log.info("[alpaca_runner] paper session completed")
    except KeyboardInterrupt:
        _log.info("Alpaca paper session stopped by user")


if __name__ == "__main__":
    main()
