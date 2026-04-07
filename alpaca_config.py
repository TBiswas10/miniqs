"""Alpaca Paper Trading configuration (REST + WebSocket URLs, throttles, symbols).

Market data uses Alpaca's **Data API** WebSocket (``stream.data.alpaca.markets``).
Order lifecycle and fills use the **Trading** WebSocket (``paper-api.alpaca.markets/stream``).
REST orders use ``https://paper-api.alpaca.markets`` — paper only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional, Sequence


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


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
    # Session limits (passed through to risk_manager)
    max_position_size: float = 5.0
    cooldown_seconds: int = 5
    max_loss_per_session: float = 500.0
    trade_size: float = 1.0
    confidence_threshold: float = 0.35
    mr_threshold: float = 0.003
    mom_threshold: float = 0.002
    feedback_trade_interval: int = 10
    max_ticks: Optional[int] = None
    # Optional: align Portfolio initial cash with Alpaca paper account
    sync_initial_cash_from_alpaca: bool = True
    portfolio_fee_rate: float = 0.0
    order_fill_timeout_seconds: float = 45.0
    order_poll_interval_seconds: float = 0.5
    # SQLite / dashboard output
    db_dir: str = "."
    dashboard_jsonl: str = "logs/live_dashboard.jsonl"
    dashboard_snapshot_json: str = "logs/live_dashboard_snapshot.json"
    dashboard_csv: str = "logs/live_dashboard.csv"

    @classmethod
    def from_env(cls, symbols: Optional[Sequence[str]] = None) -> "AlpacaConfig":
        key = _env("ALPACA_API_KEY_ID") or _env("APCA_API_KEY_ID")
        secret = _env("ALPACA_API_SECRET_KEY") or _env("APCA_API_SECRET_KEY")
        if not key or not secret:
            raise ValueError(
                "Set ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY (paper keys) in the environment."
            )
        rest = _env("ALPACA_PAPER_REST_URL", "https://paper-api.alpaca.markets")
        data_feed = _env("ALPACA_DATA_FEED", "iex")
        data_ws = _env("ALPACA_DATA_WS_URL", f"wss://stream.data.alpaca.markets/v2/{data_feed}")
        trading_ws = _env("ALPACA_TRADING_WS_URL", "wss://paper-api.alpaca.markets/stream")
        sym_raw = _env("ALPACA_SYMBOLS", "SPY")
        sym_list = list(symbols) if symbols else [s.strip().upper() for s in sym_raw.split(",") if s.strip()]
        if not sym_list:
            sym_list = ["SPY"]
        max_ticks_s = _env("ALPACA_MAX_TICKS", "")
        max_ticks: Optional[int] = int(max_ticks_s) if max_ticks_s.isdigit() else None
        return cls(
            api_key_id=key,
            api_secret_key=secret,
            rest_base_url=rest,
            data_ws_url=data_ws,
            data_feed=data_feed,
            trading_ws_url=trading_ws,
            symbols=sym_list,
            min_tick_interval_seconds=float(_env("ALPACA_MIN_TICK_INTERVAL", "0.15") or "0.15"),
            max_ticks=max_ticks,
        )
