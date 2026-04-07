"""Alpaca Paper Trading REST client (https://paper-api.alpaca.markets only)."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict


class AlpacaPaperClient:
    """Thin wrapper around Alpaca Trading API v2 (paper endpoint)."""

    def __init__(self, key_id: str, secret: str, base_url: str = "https://paper-api.alpaca.markets") -> None:
        self.key_id = key_id
        self.secret = secret
        self.base = base_url.rstrip("/")

    def _headers(self, content_json: bool = False) -> Dict[str, str]:
        h: Dict[str, str] = {
            "APCA-API-KEY-ID": self.key_id,
            "APCA-API-SECRET-KEY": self.secret,
        }
        if content_json:
            h["Content-Type"] = "application/json"
        return h

    def _request(self, method: str, path: str, body: Dict[str, Any] | None = None) -> Dict[str, Any]:
        url = f"{self.base}{path}"
        data: bytes | None = None
        headers = self._headers(content_json=body is not None)
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            err = e.read().decode()
            raise RuntimeError(f"Alpaca HTTP {e.code} {method} {path}: {err}") from e

    def get_account(self) -> Dict[str, Any]:
        return self._request("GET", "/v2/account")

    def get_order(self, order_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/v2/orders/{order_id}")

    def submit_market_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        client_order_id: str | None = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "qty": str(qty),
            "side": side.lower(),
            "type": "market",
            "time_in_force": "day",
        }
        if client_order_id:
            body["client_order_id"] = client_order_id
        return self._request("POST", "/v2/orders", body)

    def wait_for_fill(
        self,
        order_id: str,
        timeout_seconds: float = 45.0,
        poll_interval: float = 0.5,
    ) -> Dict[str, Any]:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            order = self.get_order(order_id)
            status = str(order.get("status", "")).lower()
            if status == "filled":
                return order
            if status in ("canceled", "expired", "rejected", "failed"):
                raise RuntimeError(f"Order {order_id} terminal status={status!r} body={order!r}")
            time.sleep(poll_interval)
        raise TimeoutError(f"Order {order_id} not filled within {timeout_seconds}s")
