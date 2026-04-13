"""Alpaca Trading WebSocket (paper): wss://paper-api.alpaca.markets/stream

Listens to ``trade_updates`` for order lifecycle logging (fills, rejects).
Does not replace REST fill handling — complements ``alpaca_http`` logging.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any, Callable, Dict

_log = logging.getLogger(__name__)


def _parse_trading_payload(raw: str | bytes) -> Any:
    if isinstance(raw, bytes):
        try:
            import msgpack  # type: ignore

            return msgpack.unpackb(raw, raw=False)
        except Exception:  # noqa: BLE001
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception:
                return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def run_trading_stream_listener(
    *,
    ws_url: str,
    api_key_id: str,
    api_secret_key: str,
    on_message: Callable[[str, Dict[str, Any]], None],
    on_connection_event: Callable[[str, str], None],
    stop_event: asyncio.Event,
) -> None:
    """Background task: connect, auth, listen, reconnect."""
    import websockets  # type: ignore

    backoff = 1.0
    reconnect_attempts = 0
    while not stop_event.is_set():
        try:
            async with websockets.connect(
                ws_url,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10,
                max_size=2**23,
            ) as ws:
                reconnect_attempts = 0
                on_connection_event("connected", "")
                await ws.send(
                    json.dumps({"action": "auth", "key": api_key_id, "secret": api_secret_key})
                )
                authorized = False
                for _ in range(40):
                    if stop_event.is_set():
                        return
                    raw = await asyncio.wait_for(ws.recv(), timeout=15.0)
                    data = _parse_trading_payload(raw)
                    if isinstance(data, dict):
                        stream = data.get("stream")
                        if stream == "authorization":
                            st = (data.get("data") or {}).get("status")
                            if st == "authorized":
                                authorized = True
                                on_connection_event("authenticated", "authorized")
                                break
                            if st == "unauthorized":
                                on_connection_event("auth_failed", str(data))
                                raise RuntimeError("Alpaca trading WS unauthorized")
                if not authorized:
                    on_connection_event("auth_timeout", "authorization timeout")
                    raise RuntimeError("Alpaca trading WS: authorization timeout")

                await ws.send(json.dumps({"action": "listen", "data": {"streams": ["trade_updates"]}}))
                on_connection_event("subscribed", "trade_updates")
                backoff = 1.0

                while not stop_event.is_set():
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue
                    data = _parse_trading_payload(raw)
                    if isinstance(data, dict):
                        stream = str(data.get("stream", ""))
                        payload = data.get("data")
                        if stream == "trade_updates" and isinstance(payload, dict):
                            on_message("trade_updates", payload)
                        elif stream == "listening":
                            on_connection_event("listening", json.dumps(payload))
                        elif stream == "authorization":
                            on_connection_event("authorization", json.dumps(payload))
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and item.get("stream") == "trade_updates":
                                pl = item.get("data")
                                if isinstance(pl, dict):
                                    on_message("trade_updates", pl)
            on_connection_event("disconnected", "socket_closed")

        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError as exc:
            reconnect_attempts += 1
            _log.warning("Trading WS timeout: %s", exc)
            on_connection_event("reconnecting", f"attempt={reconnect_attempts} timeout={exc}")
            jitter = random.uniform(0.0, 0.5)
            await asyncio.sleep(backoff + jitter)
            backoff = min(60.0, backoff * 2.0)
        except Exception as exc:  # noqa: BLE001
            reconnect_attempts += 1
            _log.exception("Trading WS error: %s", exc)
            on_connection_event("reconnecting", f"attempt={reconnect_attempts} error={exc}")
            jitter = random.uniform(0.0, 0.5)
            await asyncio.sleep(backoff + jitter)
            backoff = min(60.0, backoff * 2.0)
