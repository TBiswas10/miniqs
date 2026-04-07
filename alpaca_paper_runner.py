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
from pathlib import Path
from typing import Dict, Optional

from alpaca_config import AlpacaConfig
from alpaca_data_stream import stream_alpaca_ticks
from alpaca_execution import AlpacaPaperExecutionEngine
from alpaca_http import AlpacaPaperClient
from alpaca_trading_stream import run_trading_stream_listener
from feature_engine import FeatureEngine
from live_dashboard import append_csv_row, append_jsonl, dashboard_row, write_snapshot
from logger import QuantLogger
from main import FeedbackLoop
from performance import PerformanceTracker
from portfolio import Portfolio
from risk_manager import check_risk
from strategies.mean_reversion import generate_signal as mean_reversion_signal
from strategies.momentum import generate_signal as momentum_signal
from strategy_evaluator import evaluate_signals

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
]


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


def _log_trading_connection_event(logger_obj: QuantLogger, component: str, event: str, detail: str) -> None:
    logger_obj.log_connection_event(component, event, detail)
    _log.info("[%s] %s%s", component, event, f": {detail}" if detail else "")


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
    )

    logger = QuantLogger(db_path=str(Path(cfg.db_dir) / "alpaca_logs.db"))
    perf = PerformanceTracker(initial_equity=initial_cash)
    feedback = FeedbackLoop()
    engines = _feature_engines(cfg)
    primary = cfg.symbols[0].upper()

    last_trade_timestamp = None
    executed_trades = 0
    tick_counter = 0
    initial_equity = initial_cash

    stop_trading_ws = asyncio.Event()

    def on_trade_msg(_stream: str, payload: Dict[str, object]) -> None:
        ev = str(payload.get("event", ""))
        logger.log_trade_update_event(ev, payload)
        if ev:
            _log.info("[alpaca_trade_update] event=%s", ev)

    def on_trading_connection_event(component: str, detail: str) -> None:
        _log_trading_connection_event(logger, "trading_ws", component, detail)
        if component == "connected":
            _log.info("[alpaca_runner] trade logic connected")
        elif component == "listening":
            _log.info("[alpaca_runner] trade update loop connected")
        elif component == "auth_failed":
            _log.info("[alpaca_runner] trade logic authentication failed")

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
        elif event == "market_data_reconnecting":
            _log.info("[alpaca_runner] data stream reconnecting")

    try:
        async for tick in stream_alpaca_ticks(cfg, on_connection_event=on_md_event):
            tick_counter += 1
            stage = "market_data_tick"
            if cfg.status_heartbeat_ticks > 0 and tick_counter % cfg.status_heartbeat_ticks == 0:
                _log.info("[alpaca_runner] received tick=%s symbol=%s price=%.4f", tick_counter, tick.symbol, tick.price)
            if tick.symbol not in engines:
                continue
            snap = engines[tick.symbol].update(tick)
            if tick.symbol != primary:
                continue

            portfolio.update_pnl(tick.price)
            state = portfolio.get_portfolio_state()
            perf.record_equity(float(state["equity"]))
            logger.log_portfolio_snapshot(state)

            metrics = perf.compute_metrics(latest_total_pnl=float(state["total_pnl"]))

            if snap is None:
                stage = "warmup"
                _emit_heartbeat(
                    cfg=cfg,
                    tick_counter=tick_counter,
                    stage=stage,
                    primary=primary,
                    executed_trades=executed_trades,
                    state=state,
                    metrics=metrics,
                    detail="feature_window_not_ready",
                )
                if tick_counter % 100 == 0:
                    _write_dashboard(cfg, metrics, feedback, primary, executed_trades, "warmup", state)
                continue

            stage = "signals_generated"
            weights = feedback.strategy_weights
            mr = mean_reversion_signal(snap, entry_threshold=cfg.mr_threshold)
            mo = momentum_signal(snap, momentum_threshold=cfg.mom_threshold)
            mr = mr.__class__(
                strategy=mr.strategy,
                action=mr.action,
                confidence=min(1.0, mr.confidence * weights.get("mean_reversion", 0.5)),
                reason=mr.reason,
            )
            mo = mo.__class__(
                strategy=mo.strategy,
                action=mo.action,
                confidence=min(1.0, mo.confidence * weights.get("momentum", 0.5)),
                reason=mo.reason,
            )

            logger.log_signal(mr.strategy, mr.action, mr.confidence, mr.reason)
            logger.log_signal(mo.strategy, mo.action, mo.confidence, mo.reason)

            chosen = evaluate_signals([mr, mo], confidence_threshold=cfg.confidence_threshold)
            if chosen is None:
                stage = "no_signal"
                _emit_heartbeat(
                    cfg=cfg,
                    tick_counter=tick_counter,
                    stage=stage,
                    primary=primary,
                    executed_trades=executed_trades,
                    state=state,
                    metrics=metrics,
                    detail="confidence_below_threshold",
                )
                if tick_counter % 50 == 0:
                    _write_dashboard(cfg, metrics, feedback, primary, executed_trades, "no_signal", state)
                continue

            stage = "risk_check"
            trade = {
                "action": chosen.action,
                "size": cfg.trade_size,
                "confidence": chosen.confidence,
                "price": tick.price,
                "timestamp": tick.timestamp.isoformat(),
                "strategy": chosen.strategy,
                "symbol": primary,
            }
            risk_state = {
                "current_position": float(state["position_size"]),
                "last_trade_timestamp": last_trade_timestamp,
                "session_loss": max(0.0, -float(state["total_pnl"])),
                "max_position_size": cfg.max_position_size,
                "cooldown_seconds": cfg.cooldown_seconds,
                "max_loss_per_session": cfg.max_loss_per_session,
            }
            allow, risk_reason = check_risk(trade, risk_state)
            if not allow:
                stage = "risk_blocked"
                _emit_heartbeat(
                    cfg=cfg,
                    tick_counter=tick_counter,
                    stage=stage,
                    primary=primary,
                    executed_trades=executed_trades,
                    state=state,
                    metrics=metrics,
                    detail=risk_reason,
                )
                logger.log_risk_block(risk_reason, json.dumps(trade, default=str))
                continue

            try:
                stage = "trade_submission"
                result = alpaca_exec.execute_trade(trade)
            except Exception as exc:  # noqa: BLE001
                _log.exception("Alpaca execution failed: %s", exc)
                logger.log_connection_event("execution", "error", str(exc))
                continue

            stage = "trade_executed"
            last_trade_timestamp = trade["timestamp"]
            executed_trades += 1
            logger.log_trade(result, strategy=chosen.strategy)
            perf.record_trade(float(result["realized_pnl_trade"]))
            perf.record_strategy_trade(chosen.strategy, float(result["realized_pnl_trade"]))

            st2 = portfolio.get_portfolio_state()
            metrics = perf.compute_metrics(latest_total_pnl=float(st2["total_pnl"]))
            _write_dashboard(cfg, metrics, feedback, primary, executed_trades, "trade", st2)

            _emit_heartbeat(
                cfg=cfg,
                tick_counter=tick_counter,
                stage=stage,
                primary=primary,
                executed_trades=executed_trades,
                state=st2,
                metrics=metrics,
                detail=f"order_id={result.get('alpaca_order_id', '')}",
            )

            if executed_trades % cfg.feedback_trade_interval == 0:
                strategy_metrics = perf.strategy_metrics_for_feedback()
                if strategy_metrics:
                    feedback.update(strategy_metrics, logger=logger)

            if tick_counter % 200 == 0:
                _st_chk = portfolio.get_portfolio_state()
                if float(_st_chk["equity"]) < 0.8 * initial_equity:
                    logger.log_connection_event(
                        "monitor",
                        "equity_drawdown_warning",
                        f"equity={_st_chk['equity']} initial={initial_equity}",
                    )

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
        "executed_trades": float(executed_trades),
        "total_pnl": float(metrics["total_pnl"]),
        "win_rate": float(metrics["win_rate"]),
        "max_drawdown": float(metrics["max_drawdown"]),
        "sharpe_ratio": float(metrics["sharpe_ratio"]),
        "mean_reversion_weight": float(feedback.strategy_weights["mean_reversion"]),
        "momentum_weight": float(feedback.strategy_weights["momentum"]),
        "ticks_processed": float(tick_counter),
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
        },
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        asyncio.run(run_alpaca_paper_session())
    except KeyboardInterrupt:
        _log.info("Alpaca paper session stopped by user")


if __name__ == "__main__":
    main()
