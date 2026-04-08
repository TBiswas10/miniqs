"""Alpaca Paper Trading configuration (REST + WebSocket URLs, throttles, symbols).

Market data uses Alpaca's **Data API** WebSocket (``stream.data.alpaca.markets``).
Order lifecycle and fills use the **Trading** WebSocket (``paper-api.alpaca.markets/stream``).
REST orders use ``https://paper-api.alpaca.markets`` — paper only.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_structured_file(path: Path) -> Dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "YAML config requested but PyYAML is not installed. Use JSON or install PyYAML."
            ) from exc
        payload = yaml.safe_load(raw)
        return payload if isinstance(payload, dict) else {}
    raise ValueError(f"Unsupported config extension: {path.suffix}")


# Auto-load local `.env` for convenience.
# This keeps the rest of the codebase focused on reading from `os.environ`.
try:  # pragma: no cover
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(dotenv_path=Path(".env"), override=False)
except Exception:
    # If python-dotenv isn't installed (or no .env exists), we just fall back
    # to normal environment-variable behavior.
    pass


@dataclass
class AlpacaConfig:
    """Load from environment (recommended) or pass explicitly."""

    api_key_id: str
    api_secret_key: str
    rest_base_url: str = "https://paper-api.alpaca.markets"
    # Market data (required for live quotes/trades — not the same host as paper REST)
    data_ws_url: str = "wss://stream.data.alpaca.markets/v2/iex"
    data_feed: str = "iex"
    # Trading / account stream (order updates) — paper
    trading_ws_url: str = "wss://paper-api.alpaca.markets/stream"
    symbols: List[str] = field(default_factory=lambda: ["SPY"])
    subscribe_trades: bool = True
    subscribe_quotes: bool = True
    subscribe_bars: bool = False
    # Process at most one tick per symbol per interval (limits strategy CPU & API noise)
    min_tick_interval_seconds: float = 0.15
    # WebSocket reconnect backoff (seconds)
    reconnect_initial_seconds: float = 1.0
    reconnect_max_seconds: float = 60.0
    # Periodic console/log confirmation for the live runner
    status_heartbeat_ticks: int = 50
    # Session limits (passed through to risk_manager)
    max_position_size: float = 5.0
    cooldown_seconds: int = 5
    max_loss_per_session: float = 500.0
    trade_size: float = 1.0
    risk_per_trade: float = 0.01
    daily_loss_limit: float = 500.0
    confidence_threshold: float = 0.35
    evaluation_profile: str = "default"
    mr_threshold: float = 0.003
    mom_threshold: float = 0.002
    vb_breakout_factor: float = 1.2
    feedback_trade_interval: int = 10
    max_ticks: Optional[int] = None
    # Optional: align Portfolio initial cash with Alpaca paper account
    sync_initial_cash_from_alpaca: bool = True
    portfolio_fee_rate: float = 0.0
    order_fill_timeout_seconds: float = 45.0
    order_poll_interval_seconds: float = 0.5
    execution_max_retries: int = 3
    execution_retry_backoff_seconds: float = 1.0
    # SQLite / dashboard output
    db_dir: str = "."
    dashboard_jsonl: str = "logs/live_dashboard.jsonl"
    dashboard_snapshot_json: str = "logs/live_dashboard_snapshot.json"
    dashboard_csv: str = "logs/live_dashboard.csv"
    brain_trace_jsonl: str = "logs/alpaca_brain_trace.jsonl"

    @classmethod
    def from_file(cls, file_path: str | Path) -> "AlpacaConfig":
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file does not exist: {path}")
        payload = _load_structured_file(path)
        root = payload.get("alpaca", payload) if isinstance(payload, dict) else {}
        risk = root.get("risk", {}) if isinstance(root.get("risk"), dict) else {}
        strategy = root.get("strategy", {}) if isinstance(root.get("strategy"), dict) else {}
        execution = root.get("execution", {}) if isinstance(root.get("execution"), dict) else {}
        market_data = root.get("market_data", {}) if isinstance(root.get("market_data"), dict) else {}

        symbols = root.get("symbols", ["SPY"])
        if not isinstance(symbols, list):
            symbols = ["SPY"]
        symbol_list = [str(s).strip().upper() for s in symbols if str(s).strip()]
        if not symbol_list:
            symbol_list = ["SPY"]

        max_ticks_value = root.get("max_ticks")
        max_ticks = int(max_ticks_value) if isinstance(max_ticks_value, (int, float)) and int(max_ticks_value) > 0 else None

        return cls(
            api_key_id=str(root.get("api_key_id", "")),
            api_secret_key=str(root.get("api_secret_key", "")),
            rest_base_url=str(root.get("rest_base_url", "https://paper-api.alpaca.markets")),
            data_ws_url=str(market_data.get("data_ws_url", root.get("data_ws_url", "wss://stream.data.alpaca.markets/v2/iex"))),
            data_feed=str(market_data.get("data_feed", root.get("data_feed", "iex"))),
            trading_ws_url=str(root.get("trading_ws_url", "wss://paper-api.alpaca.markets/stream")),
            symbols=symbol_list,
            subscribe_trades=_bool(market_data.get("subscribe_trades", root.get("subscribe_trades")), True),
            subscribe_quotes=_bool(market_data.get("subscribe_quotes", root.get("subscribe_quotes")), True),
            subscribe_bars=_bool(market_data.get("subscribe_bars", root.get("subscribe_bars")), False),
            min_tick_interval_seconds=float(market_data.get("min_tick_interval_seconds", root.get("min_tick_interval_seconds", 0.15))),
            reconnect_initial_seconds=float(market_data.get("reconnect_initial_seconds", root.get("reconnect_initial_seconds", 1.0))),
            reconnect_max_seconds=float(market_data.get("reconnect_max_seconds", root.get("reconnect_max_seconds", 60.0))),
            status_heartbeat_ticks=int(root.get("status_heartbeat_ticks", 50)),
            max_position_size=float(risk.get("max_position_size", root.get("max_position_size", 5.0))),
            cooldown_seconds=int(risk.get("cooldown_seconds", root.get("cooldown_seconds", 5))),
            max_loss_per_session=float(risk.get("max_loss_per_session", root.get("max_loss_per_session", 500.0))),
            trade_size=float(risk.get("trade_size", root.get("trade_size", 1.0))),
            risk_per_trade=float(risk.get("risk_per_trade", root.get("risk_per_trade", 0.01))),
            daily_loss_limit=float(risk.get("daily_loss_limit", root.get("daily_loss_limit", 500.0))),
            confidence_threshold=float(risk.get("confidence_threshold", root.get("confidence_threshold", 0.35))),
            evaluation_profile=str(strategy.get("evaluation_profile", root.get("evaluation_profile", "default"))),
            mr_threshold=float(strategy.get("mr_threshold", root.get("mr_threshold", 0.003))),
            mom_threshold=float(strategy.get("mom_threshold", root.get("mom_threshold", 0.002))),
            vb_breakout_factor=float(strategy.get("vb_breakout_factor", root.get("vb_breakout_factor", 1.2))),
            feedback_trade_interval=int(strategy.get("feedback_trade_interval", root.get("feedback_trade_interval", 10))),
            max_ticks=max_ticks,
            sync_initial_cash_from_alpaca=_bool(root.get("sync_initial_cash_from_alpaca"), True),
            portfolio_fee_rate=float(root.get("portfolio_fee_rate", 0.0)),
            order_fill_timeout_seconds=float(execution.get("order_fill_timeout_seconds", root.get("order_fill_timeout_seconds", 45.0))),
            order_poll_interval_seconds=float(execution.get("order_poll_interval_seconds", root.get("order_poll_interval_seconds", 0.5))),
            execution_max_retries=int(execution.get("max_retries", root.get("execution_max_retries", 3))),
            execution_retry_backoff_seconds=float(execution.get("retry_backoff_seconds", root.get("execution_retry_backoff_seconds", 1.0))),
            db_dir=str(root.get("db_dir", ".")),
            dashboard_jsonl=str(root.get("dashboard_jsonl", "logs/live_dashboard.jsonl")),
            dashboard_snapshot_json=str(root.get("dashboard_snapshot_json", "logs/live_dashboard_snapshot.json")),
            dashboard_csv=str(root.get("dashboard_csv", "logs/live_dashboard.csv")),
            brain_trace_jsonl=str(root.get("brain_trace_jsonl", "logs/alpaca_brain_trace.jsonl")),
        )

    @classmethod
    def from_env(cls, symbols: Optional[Sequence[str]] = None) -> "AlpacaConfig":
        config_path = _env("ALPACA_CONFIG_FILE", "config/alpaca_config.json")
        base = cls.from_file(config_path) if Path(config_path).exists() else cls(api_key_id="", api_secret_key="")

        key = _env("ALPACA_API_KEY_ID") or _env("APCA_API_KEY_ID") or base.api_key_id
        secret = _env("ALPACA_API_SECRET_KEY") or _env("APCA_API_SECRET_KEY") or base.api_secret_key
        if not key or not secret:
            raise ValueError(
                "Set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY (or put them in the config file)."
            )

        sym_raw = _env("ALPACA_SYMBOLS", ",".join(base.symbols))
        sym_list = list(symbols) if symbols else [s.strip().upper() for s in sym_raw.split(",") if s.strip()]
        if not sym_list:
            sym_list = ["SPY"]

        data_feed_env = _env("ALPACA_DATA_FEED", base.data_feed)
        data_ws_env = _env("ALPACA_DATA_WS_URL", base.data_ws_url)
        data_feed = data_feed_env
        data_ws = data_ws_env or f"wss://stream.data.alpaca.markets/v2/{data_feed}"
        if "/crypto/" in data_ws and data_feed == "iex":
            data_feed = "crypto/us"

        max_ticks_s = _env("ALPACA_MAX_TICKS", str(base.max_ticks or ""))
        max_ticks: Optional[int] = int(max_ticks_s) if str(max_ticks_s).isdigit() else base.max_ticks

        return cls(
            api_key_id=key,
            api_secret_key=secret,
            rest_base_url=_env("ALPACA_PAPER_REST_URL", base.rest_base_url),
            data_ws_url=data_ws,
            data_feed=data_feed,
            trading_ws_url=_env("ALPACA_TRADING_WS_URL", base.trading_ws_url),
            symbols=sym_list,
            subscribe_trades=base.subscribe_trades,
            subscribe_quotes=base.subscribe_quotes,
            subscribe_bars=base.subscribe_bars,
            min_tick_interval_seconds=float(_env("ALPACA_MIN_TICK_INTERVAL", str(base.min_tick_interval_seconds))),
            reconnect_initial_seconds=base.reconnect_initial_seconds,
            reconnect_max_seconds=base.reconnect_max_seconds,
            status_heartbeat_ticks=int(_env("ALPACA_STATUS_HEARTBEAT_TICKS", str(base.status_heartbeat_ticks))),
            max_position_size=float(_env("ALPACA_MAX_POSITION_SIZE", str(base.max_position_size))),
            cooldown_seconds=int(_env("ALPACA_COOLDOWN_SECONDS", str(base.cooldown_seconds))),
            max_loss_per_session=float(_env("ALPACA_MAX_LOSS_PER_SESSION", str(base.max_loss_per_session))),
            trade_size=float(_env("ALPACA_TRADE_SIZE", str(base.trade_size))),
            risk_per_trade=float(_env("ALPACA_RISK_PER_TRADE", str(base.risk_per_trade))),
            daily_loss_limit=float(_env("ALPACA_DAILY_LOSS_LIMIT", str(base.daily_loss_limit))),
            confidence_threshold=float(_env("ALPACA_CONFIDENCE_THRESHOLD", str(base.confidence_threshold))),
            evaluation_profile=_env("ALPACA_EVALUATION_PROFILE", base.evaluation_profile),
            mr_threshold=float(_env("ALPACA_MR_THRESHOLD", str(base.mr_threshold))),
            mom_threshold=float(_env("ALPACA_MOM_THRESHOLD", str(base.mom_threshold))),
            vb_breakout_factor=float(_env("ALPACA_VB_BREAKOUT_FACTOR", str(base.vb_breakout_factor))),
            feedback_trade_interval=int(_env("ALPACA_FEEDBACK_TRADE_INTERVAL", str(base.feedback_trade_interval))),
            max_ticks=max_ticks,
            sync_initial_cash_from_alpaca=base.sync_initial_cash_from_alpaca,
            portfolio_fee_rate=base.portfolio_fee_rate,
            order_fill_timeout_seconds=float(_env("ALPACA_ORDER_FILL_TIMEOUT", str(base.order_fill_timeout_seconds))),
            order_poll_interval_seconds=float(_env("ALPACA_ORDER_POLL_INTERVAL", str(base.order_poll_interval_seconds))),
            execution_max_retries=int(_env("ALPACA_EXECUTION_MAX_RETRIES", str(base.execution_max_retries))),
            execution_retry_backoff_seconds=float(_env("ALPACA_EXECUTION_RETRY_BACKOFF", str(base.execution_retry_backoff_seconds))),
            db_dir=base.db_dir,
            dashboard_jsonl=_env("ALPACA_DASHBOARD_JSONL", base.dashboard_jsonl),
            dashboard_snapshot_json=_env("ALPACA_DASHBOARD_SNAPSHOT_JSON", base.dashboard_snapshot_json),
            dashboard_csv=_env("ALPACA_DASHBOARD_CSV", base.dashboard_csv),
            brain_trace_jsonl=_env("ALPACA_BRAIN_TRACE_JSONL", base.brain_trace_jsonl),
        )
