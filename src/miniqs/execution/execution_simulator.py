"""Execution simulation with realistic order-state transitions and fills."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import random
import math
from typing import Any, Dict, List


@dataclass
class ExecutionSimulationConfig:
    spread_bps: float = 1.5
    slippage_bps: float = 3.0
    impact_coefficient: float = 0.5  # For non-linear square root impact
    min_latency_ms: int = 50
    max_latency_ms: int = 200
    partial_fill_probability: float = 0.35
    cancel_remainder_probability: float = 0.2
    reject_probability: float = 0.0
    min_fill_slice: float = 0.1


class OrderState:
    CREATED = "created"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"


class ExecutionSimulator:
    def __init__(self, config: ExecutionSimulationConfig | None = None, seed: int = 42) -> None:
        self.config = config or ExecutionSimulationConfig()
        self._rng = random.Random(seed)

    def simulate(self, trade: Dict[str, Any]) -> Dict[str, Any]:
        action = str(trade.get("action", "")).lower()
        requested_size = float(trade.get("size", 0.0))
        reference_price = float(trade.get("price", 0.0))

        path: List[Dict[str, Any]] = []
        fills: List[Dict[str, Any]] = []
        min_latency = max(1, int(self.config.min_latency_ms))
        max_latency = max(min_latency, int(self.config.max_latency_ms))
        total_latency_ms = int(self._rng.randint(min_latency, max_latency))
        base_time = datetime.now(timezone.utc)
        state_count = 1

        def push_state(state: str, detail: str = "") -> None:
            nonlocal state_count
            ms_offset = int((total_latency_ms * state_count) / 6)
            path.append(
                {
                    "state": state,
                    "timestamp": (base_time + timedelta(milliseconds=ms_offset)).isoformat(),
                    "detail": detail,
                }
            )
            state_count += 1

        push_state(OrderState.CREATED)

        if action not in {"buy", "sell"} or requested_size <= 0 or reference_price <= 0:
            push_state(OrderState.REJECTED, "invalid_trade_payload")
            return {
                "final_state": OrderState.REJECTED,
                "filled_size": 0.0,
                "remaining_size": requested_size,
                "avg_fill_price": reference_price,
                "latency_ms": total_latency_ms,
                "path": path,
                "fills": fills,
            }

        push_state(OrderState.SUBMITTED)
        push_state(OrderState.ACKNOWLEDGED)

        if self._rng.random() < self.config.reject_probability:
            push_state(OrderState.REJECTED, "venue_reject")
            return {
                "final_state": OrderState.REJECTED,
                "filled_size": 0.0,
                "remaining_size": requested_size,
                "avg_fill_price": reference_price,
                "latency_ms": total_latency_ms,
                "path": path,
                "fills": fills,
            }

        remaining = requested_size
        do_partial = requested_size >= (2 * self.config.min_fill_slice) and self._rng.random() < self.config.partial_fill_probability

        if do_partial:
            first_slice = max(self.config.min_fill_slice, min(remaining, requested_size * self._rng.uniform(0.35, 0.75)))
            first_price = self._executed_price(action=action, reference_price=reference_price, qty=first_slice)
            fills.append({"qty": round(first_slice, 8), "price": round(first_price, 8), "state": OrderState.PARTIAL})
            remaining -= first_slice
            push_state(OrderState.PARTIAL, f"partial_fill={first_slice:.4f}")

            should_cancel_remainder = self._rng.random() < self.config.cancel_remainder_probability
            if should_cancel_remainder and remaining > 0:
                push_state(OrderState.CANCELED, f"remaining_canceled={remaining:.4f}")
            else:
                last_qty = max(0.0, remaining)
                if last_qty > 0:
                    last_price = self._executed_price(action=action, reference_price=reference_price, qty=last_qty)
                    fills.append({"qty": round(last_qty, 8), "price": round(last_price, 8), "state": OrderState.FILLED})
                    remaining = 0.0
                    push_state(OrderState.FILLED)
                else:
                    push_state(OrderState.FILLED)
        else:
            fill_price = self._executed_price(action=action, reference_price=reference_price, qty=requested_size)
            fills.append({"qty": round(requested_size, 8), "price": round(fill_price, 8), "state": OrderState.FILLED})
            remaining = 0.0
            push_state(OrderState.FILLED)

        filled_size = round(sum(float(f["qty"]) for f in fills), 8)
        notional = sum(float(f["qty"]) * float(f["price"]) for f in fills)
        avg_fill_price = (notional / filled_size) if filled_size > 0 else reference_price
        final_state = path[-1]["state"]

        return {
            "final_state": final_state,
            "filled_size": round(filled_size, 8),
            "remaining_size": round(max(0.0, requested_size - filled_size), 8),
            "avg_fill_price": round(avg_fill_price, 8),
            "latency_ms": total_latency_ms,
            "path": path,
            "fills": fills,
        }

    def _executed_price(self, *, action: str, reference_price: float, qty: float) -> float:
        spread = self.config.spread_bps / 10000.0
        slippage = self.config.slippage_bps / 10000.0
        # Non-linear impact: cost scales with square root of quantity
        impact = (self.config.impact_coefficient * math.sqrt(max(qty, 0.0))) / 10000.0
        total = spread + slippage + impact
        if action == "buy":
            return reference_price * (1.0 + total)
        return reference_price * max(0.000001, (1.0 - total))
