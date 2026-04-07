"""Alpaca market data WebSocket (Data API: stream.data.alpaca.markets).

Produces ``Tick`` objects for ``feature_engine``. Includes auth, subscribe,
reconnect with backoff, duplicate suppression, and optional per-symbol throttle.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from collections import deque
from typing import AsyncIterator, Callable, Deque, Dict, Optional, Set

import pandas as pd

from alpaca_config import AlpacaConfig
from data_feed import Tick

_log = logging.getLogger(__name__)


def parse_alpaca_timestamp(raw: str) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    ts = pd.Timestamp(raw)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.floor("us").to_pydatetime()


def dedupe_key_for_message(obj: Dict[str, object]) -> Optional[str]:
    """Return a stable key for duplicate suppression, or None to skip dedupe."""
    t = obj.get("T")
    if t == "t":
        sym = obj.get("S", "")
        tid = obj.get("i", "")
        return f"trade:{sym}:{tid}"
    if t == "q":
        sym = obj.get("S", "")
        bp = obj.get("bp", "")
        ap = obj.get("ap", "")
        ts = obj.get("t", "")
        return f"quote:{sym}:{bp}:{ap}:{ts}"
    if t == "b":
        sym = obj.get("S", "")
        ts = obj.get("t", "")
        return f"bar:{sym}:{ts}"
    return None


def alpaca_message_to_tick(obj: Dict[str, object]) -> Optional[Tick]:
    """Convert one Alpaca data payload to a Tick (mid for quotes, last for trades)."""
    t = obj.get("T")
    sym = str(obj.get("S", "")).upper()
    if not sym:
        return None
    if t == "q":
        bp = float(obj.get("bp", 0.0) or 0.0)
        ap = float(obj.get("ap", 0.0) or 0.0)
        if bp <= 0 or ap <= 0:
            return None
        price = (bp + ap) / 2.0
        bs = float(obj.get("bs", 0.0) or 0.0)
        a_s = float(obj.get("as", 0.0) or 0.0)
        vol = bs + a_s
        ts = parse_alpaca_timestamp(str(obj.get("t", "")))
        return Tick(symbol=sym, price=round(price, 8), timestamp=ts, volume=vol)
    if t == "t":
        price = float(obj.get("p", 0.0) or 0.0)
        if price <= 0:
            return None
        vol = float(obj.get("s", 0.0) or 0.0)
        ts = parse_alpaca_timestamp(str(obj.get("t", "")))
        return Tick(symbol=sym, price=round(price, 8), timestamp=ts, volume=vol)
    if t == "b":
        c = float(obj.get("c", 0.0) or 0.0)
        if c <= 0:
            return None
        vol = float(obj.get("v", 0.0) or 0.0)
        ts = parse_alpaca_timestamp(str(obj.get("t", "")))
        return Tick(symbol=sym, price=round(c, 8), timestamp=ts, volume=vol)
    return None


async def _connect_market_ws(config: AlpacaConfig):
    import websockets  # type: ignore

    return await websockets.connect(
        config.data_ws_url,
        ping_interval=20,
        ping_timeout=20,
        close_timeout=10,
        max_size=2**23,
    )


async def stream_alpaca_ticks(
    config: AlpacaConfig,
    on_connection_event: Optional[Callable[[str, str], None]] = None,
) -> AsyncIterator[Tick]:
    """Reconnecting async iterator of market ``Tick`` objects."""
    backoff = config.reconnect_initial_seconds
    seen: Deque[str] = deque(maxlen=50_000)
    seen_set: Set[str] = set()
    last_emit: Dict[str, float] = {}
    tick_count = 0

    def remember(key: str) -> bool:
        if key in seen_set:
            return True
        if len(seen) >= seen.maxlen:
            old = seen.popleft()
            seen_set.discard(old)
        seen.append(key)
        seen_set.add(key)
        return False

    import websockets  # type: ignore
    import websockets.exceptions  # type: ignore
    reconnect_attempts = 0

    while True:
        try:
            async with await _connect_market_ws(config) as ws:
                reconnect_attempts = 0
                if on_connection_event:
                    on_connection_event("market_data", "connected")
                await ws.send(
                    json.dumps(
                        {"action": "auth", "key": config.api_key_id, "secret": config.api_secret_key}
                    )
                )
                authenticated = False
                for _ in range(20):
                    raw_auth = await asyncio.wait_for(ws.recv(), timeout=10.0)
                    if isinstance(raw_auth, bytes):
                        raw_auth = raw_auth.decode("utf-8", errors="replace")
                    try:
                        auth_arr = json.loads(raw_auth)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(auth_arr, list):
                        continue
                    for auth_obj in auth_arr:
                        if isinstance(auth_obj, dict) and auth_obj.get("T") == "success" and auth_obj.get("msg") == "authenticated":
                            authenticated = True
                            break
                        if isinstance(auth_obj, dict) and auth_obj.get("T") == "error":
                            msg = str(auth_obj.get("msg", auth_obj))
                            if on_connection_event:
                                on_connection_event("market_data_auth_failed", msg)
                            raise RuntimeError(f"Alpaca market data auth failed: {msg}")
                    if authenticated:
                        break
                if not authenticated:
                    raise RuntimeError("Alpaca market data auth timeout")

                sub: Dict[str, object] = {"action": "subscribe"}
                syms = [s.upper() for s in config.symbols]
                if config.subscribe_trades:
                    sub["trades"] = syms
                if config.subscribe_quotes:
                    sub["quotes"] = syms
                if config.subscribe_bars:
                    sub["bars"] = syms
                await ws.send(json.dumps(sub))
                if on_connection_event:
                    on_connection_event("market_data", f"subscribed:{','.join(syms)}")
                backoff = config.reconnect_initial_seconds

                async for raw in ws:
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", errors="replace")
                    try:
                        arr = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(arr, list):
                        continue
                    for obj in arr:
                        if not isinstance(obj, dict):
                            continue
                        o = {str(k): v for k, v in obj.items()}
                        if o.get("T") == "error":
                            msg = str(o.get("msg", o))
                            _log.warning("Alpaca data error: %s", msg)
                            if on_connection_event:
                                on_connection_event("market_data_error", msg)
                            continue
                        if o.get("T") in ("success", "subscription"):
                            continue
                        dk = dedupe_key_for_message(o)
                        if dk and remember(dk):
                            continue
                        tick = alpaca_message_to_tick(o)
                        if tick is None:
                            continue
                        # Throttle per symbol
                        import time as _time

                        now = _time.monotonic()
                        last = last_emit.get(tick.symbol, 0.0)
                        if now - last < config.min_tick_interval_seconds:
                            continue
                        last_emit[tick.symbol] = now
                        tick_count += 1
                        yield tick
                        if config.max_ticks is not None and tick_count >= config.max_ticks:
                            return

        except asyncio.CancelledError:
            raise
        except websockets.exceptions.ConnectionClosed as exc:  # type: ignore[attr-defined]
            reconnect_attempts += 1
            detail = f"closed code={getattr(exc, 'code', 'n/a')} reason={getattr(exc, 'reason', '')} attempt={reconnect_attempts}"
            _log.warning("Market data WS closed: %s", detail)
            if on_connection_event:
                on_connection_event("market_data_reconnecting", detail)
            jitter = random.uniform(0.0, 0.5)
            await asyncio.sleep(backoff + jitter)
            backoff = min(config.reconnect_max_seconds, backoff * 2.0)
        except Exception as exc:  # noqa: BLE001 — reconnect loop
            reconnect_attempts += 1
            _log.exception("Market data WS error: %s", exc)
            if on_connection_event:
                on_connection_event("market_data_reconnecting", f"attempt={reconnect_attempts} error={exc}")
            jitter = random.uniform(0.0, 0.5)
            await asyncio.sleep(backoff + jitter)
            backoff = min(config.reconnect_max_seconds, backoff * 2.0)
