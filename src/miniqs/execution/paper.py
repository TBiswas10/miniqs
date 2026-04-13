"""Execute paper trades via Alpaca REST, then mirror fills into ``Portfolio``."""

from __future__ import annotations

import time
import hashlib
import json
from typing import Any, Dict

from src.miniqs.execution.http import AlpacaPaperClient
from src.miniqs.risk.portfolio import Portfolio


class AlpacaPaperExecutionEngine:
    """Submit market orders to Alpaca paper; update local portfolio from fill price."""

    def __init__(
        self,
        portfolio: Portfolio,
        client: AlpacaPaperClient,
        paper_mode: bool = True,
        debug: bool = False,
        fill_timeout_seconds: float = 45.0,
        poll_interval: float = 0.5,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        self.portfolio = portfolio
        self.client = client
        self.paper_mode = paper_mode
        self.debug = debug
        self.fill_timeout_seconds = fill_timeout_seconds
        self.poll_interval = poll_interval
        self.max_retries = max(1, int(max_retries))
        self.retry_backoff_seconds = max(0.1, float(retry_backoff_seconds))

    def execute_trade(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        if not self.paper_mode:
            raise PermissionError("AlpacaPaperExecutionEngine only supports paper_mode=True")

        action = str(trade.get("action", "")).lower()
        symbol = str(trade.get("symbol", "")).upper()
        size = float(trade.get("size", 0.0))
        if action not in {"buy", "sell"} or size <= 0:
            raise ValueError("trade must have action buy/sell and positive size")
        if not symbol:
            raise ValueError("trade must include symbol for Alpaca execution")

        side = "buy" if action == "buy" else "sell"
        client_order_id = trade.get("client_order_id") or self._stable_client_order_id(trade)

        order: Dict[str, Any] = {}
        filled: Dict[str, Any] = {}
        oid = ""
        for attempt in range(1, self.max_retries + 1):
            try:
                order = self.client.submit_market_order(
                    symbol,
                    size,
                    side,
                    client_order_id=str(client_order_id)[:48],
                )
                oid = str(order.get("id", ""))
                if not oid:
                    raise RuntimeError(f"Unexpected submit response: {order!r}")
                filled = self.client.wait_for_fill(oid, self.fill_timeout_seconds, self.poll_interval)
                break
            except Exception as exc:  # noqa: BLE001
                if attempt >= self.max_retries:
                    raise RuntimeError(
                        f"Alpaca REST execution failed after {self.max_retries} attempts: {exc}"
                    ) from exc
                time.sleep(self.retry_backoff_seconds * attempt)

        fill_price = float(filled.get("filled_avg_price") or trade.get("price") or 0.0)
        if fill_price <= 0:
            raise RuntimeError(f"Invalid fill price from order {order!r}")

        ts = filled.get("filled_at") or filled.get("updated_at") or trade.get("timestamp")
        if ts is None:
            ts = trade.get("timestamp")

        local_trade = {
            "action": action,
            "size": float(filled.get("filled_qty", size) or size),
            "price": fill_price,
            "timestamp": ts,
        }
        result = self.portfolio.execute_trade(local_trade)
        result["alpaca_order_id"] = oid
        result["client_order_id"] = client_order_id
        result["symbol"] = symbol
        result["fill_source"] = "alpaca_rest"
        if self.debug:
            print(
                f"[alpaca_execution] {action} {symbol} size={local_trade['size']} "
                f"price={fill_price} order_id={oid}"
            )
        return result

    def _stable_client_order_id(self, trade: Dict[str, Any]) -> str:
        payload = {
            "action": str(trade.get("action", "")).lower(),
            "symbol": str(trade.get("symbol", "")).upper(),
            "size": round(float(trade.get("size", 0.0)), 8),
            "price": round(float(trade.get("price", 0.0)), 8),
            "timestamp": str(trade.get("timestamp", "")),
            "strategy": str(trade.get("strategy", "")),
            "confidence": round(float(trade.get("confidence", 0.0)), 6),
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return f"mq-{digest[:32]}"
