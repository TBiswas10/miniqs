"""Market data feed module.

Paper-trading first:
- Uses a deterministic/randomized simulator by default.
- Live feed is intentionally disabled unless explicitly enabled.

Alpaca integration (see ``alpaca_data_stream`` and ``alpaca_paper_runner``):
- Market **quotes/trades/bars** use the Data API WebSocket
  ``wss://stream.data.alpaca.markets/v2/{feed}`` (not the paper REST host).
- Order lifecycle / paper fills use REST ``https://paper-api.alpaca.markets`` and the
  trading stream ``wss://paper-api.alpaca.markets/stream``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import random
from typing import AsyncIterator, Dict, Iterator, List, Optional


@dataclass(frozen=True)
class Tick:
    """Single market tick."""

    symbol: str
    price: float
    timestamp: datetime
    volume: float


class DataFeed:
    """Provides market ticks from a simulated or (disabled-by-default) live source.

    Inputs:
    - symbol: instrument symbol (for example, "AAPL")
    - mode: "simulated" or "live"
    - allow_live: must be True to permit live mode
    - seed: optional RNG seed for reproducible simulation

    Outputs:
    - stream(): iterator of Tick objects
    - start_feed(): generates ticks and stores latest payload {timestamp, mid_price}
    - get_latest_tick(): returns latest payload
    - stop_feed(): marks feed as stopped
    """

    def __init__(
        self,
        symbol: str,
        mode: str = "simulated",
        allow_live: bool = False,
        seed: Optional[int] = None,
        start_price: float = 100.0,
    ) -> None:
        if mode not in {"simulated", "live"}:
            raise ValueError("mode must be 'simulated' or 'live'")
        if mode == "live" and not allow_live:
            raise PermissionError(
                "Live data feed disabled. Set allow_live=True only after paper validation."
            )
        if start_price <= 0:
            raise ValueError("start_price must be positive")

        self.symbol = symbol
        self.mode = mode
        self.allow_live = allow_live
        self._rng = random.Random(seed)
        self._last_price = start_price
        self._running = False
        self._latest_tick_payload: Optional[Dict[str, object]] = None

    def stream(self) -> Iterator[Tick]:
        """Yield ticks indefinitely.

        Simulated mode:
        - Random walk around the last observed price.
        - Small random volume samples.

        Live mode:
        - Bridges the async Binance mid-price feed into this sync iterator API.
        """
        if self.mode == "simulated":
            while True:
                yield self._next_simulated_tick()
        else:
            live_symbol = self.symbol.replace("/", "").replace("-", "").lower()
            if not live_symbol.endswith("usdt"):
                live_symbol = f"{live_symbol}usdt"

            loop = asyncio.new_event_loop()
            stream = self.live_binance_midprice_stream(symbol=live_symbol)

            try:
                while True:
                    payload = loop.run_until_complete(anext(stream))
                    price = float(payload["mid_price"])
                    tick = Tick(
                        symbol=self.symbol,
                        price=price,
                        timestamp=datetime.now(timezone.utc),
                        volume=0.0,
                    )
                    self._last_price = price
                    self._latest_tick_payload = {
                        "timestamp": tick.timestamp.isoformat(),
                        "mid_price": float(tick.price),
                    }
                    yield tick
            finally:
                try:
                    loop.run_until_complete(stream.aclose())
                except Exception:
                    pass
                loop.close()

    def _next_simulated_tick(self) -> Tick:
        change_pct = self._rng.uniform(-0.002, 0.002)
        new_price = max(0.01, self._last_price * (1.0 + change_pct))
        self._last_price = new_price

        volume = self._rng.uniform(1.0, 100.0)
        return Tick(
            symbol=self.symbol,
            price=round(new_price, 4),
            timestamp=datetime.now(timezone.utc),
            volume=round(volume, 2),
        )

    def start_feed(self, tick_count: int = 1) -> List[Dict[str, object]]:
        """Start feed and produce ticks.

        Input:
        - tick_count: number of ticks to generate in this call

        Output:
        - list of payloads: {"timestamp": iso string, "mid_price": float}
        """
        if tick_count < 1:
            raise ValueError("tick_count must be >= 1")

        self._running = True
        payloads: List[Dict[str, object]] = []
        stream = self.stream()
        for _ in range(tick_count):
            tick = next(stream)
            payload = {
                "timestamp": tick.timestamp.isoformat(),
                "mid_price": float(tick.price),
            }
            self._latest_tick_payload = payload
            payloads.append(payload)
        return payloads

    def get_latest_tick(self) -> Optional[Dict[str, object]]:
        """Return latest tick payload as {timestamp, mid_price}."""
        return self._latest_tick_payload

    def stop_feed(self) -> None:
        """Stop data feed generation."""
        self._running = False

    async def live_binance_midprice_stream(
        self,
        symbol: str = "btcusdt",
        max_messages: Optional[int] = None,
    ) -> AsyncIterator[Dict[str, object]]:
        """Yield live mid-price updates from Binance bookTicker stream.

        Input:
        - symbol: lower-case market symbol, e.g. ``btcusdt``
        - max_messages: optional max number of updates

        Output:
        - async stream of {"timestamp": iso str, "mid_price": float}

        Notes:
        - Paper-observation only. This does not execute orders.
        - Requires ``websockets`` package installed.
        """
        try:
            import websockets  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "websockets is required for live feed. Install with: pip install websockets"
            ) from exc

        stream_symbol = symbol.lower()
        url = f"wss://stream.binance.com:9443/ws/{stream_symbol}@bookTicker"
        count = 0
        async with websockets.connect(url) as ws:
            async for message in ws:
                payload = json.loads(message)
                bid = float(payload.get("b", 0.0))
                ask = float(payload.get("a", 0.0))
                if bid <= 0 or ask <= 0:
                    continue

                mid_price = (bid + ask) / 2.0
                out = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "mid_price": round(mid_price, 8),
                }
                self._latest_tick_payload = out
                yield out

                count += 1
                if max_messages is not None and count >= max_messages:
                    break


def demo_feed(num_ticks: int = 5) -> None:
    """Simple console demo for manual verification."""
    feed = DataFeed(symbol="DEMO", mode="simulated", seed=42)
    ticks = feed.start_feed(tick_count=num_ticks)
    for i, tick in enumerate(ticks, start=1):
        print(f"[{i}] mid_price={tick['mid_price']} ts={tick['timestamp']}")
    feed.stop_feed()


if __name__ == "__main__":
    demo_feed()
