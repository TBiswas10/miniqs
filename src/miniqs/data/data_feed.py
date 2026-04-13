"""Market data feed module.

Paper-trading first:
- Uses a deterministic/randomized simulator by default.
- Live feed is intentionally disabled unless explicitly enabled.

Alpaca integration (see ``alpaca_data_stream`` and ``runners.paper``):
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
import math
import random
import time
from typing import AsyncIterator, Dict, Iterator, List, Optional, Deque


class Tick:
    """Single market tick."""
    __slots__ = ('symbol', 'price', 'timestamp', 'volume', 'message_type', 'bid_price', 'ask_price', 'bid_size', 'ask_size', 'trade_size')

    def __init__(
        self,
        symbol: str,
        price: float,
        timestamp: datetime,
        volume: float,
        message_type: str = "",
        bid_price: Optional[float] = None,
        ask_price: Optional[float] = None,
        bid_size: Optional[float] = None,
        ask_size: Optional[float] = None,
        trade_size: Optional[float] = None,
    ):
        self.symbol = symbol
        self.price = price
        self.timestamp = timestamp
        self.volume = volume
        self.message_type = message_type
        self.bid_price = bid_price
        self.ask_price = ask_price
        self.bid_size = bid_size
        self.ask_size = ask_size
        self.trade_size = trade_size

    def validate(self) -> bool:
        """Data Agent check: ensure prices are sane and timestamp is recent."""
        if self.price <= 0 or self.volume < 0:
            return False
        # Ensure we haven't received a stale tick (older than 1 minute)
        age = datetime.now(timezone.utc) - self.timestamp
        if age.total_seconds() > 60:
            return False
        return True

    def to_feature_payload(self) -> Dict[str, object]:
        """Return a backwards-compatible feature payload plus microstructure fields."""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "mid_price": float(self.price),
            "message_type": self.message_type,
            "bid_price": self.bid_price,
            "ask_price": self.ask_price,
            "bid_size": self.bid_size,
            "ask_size": self.ask_size,
            "trade_size": self.trade_size,
            "volume": float(self.volume),
        }


class DataCleaner:
    """Data Agent utility for cleaning, normalizing, and gap detection."""

    def __init__(self, window_size: int = 100, gap_threshold_sec: float = 5.0):
        from collections import deque
        self.window: Deque[float] = deque(maxlen=window_size)
        self.last_ts: Optional[datetime] = None
        self.gap_threshold = gap_threshold_sec

    def process(self, tick: Tick) -> Optional[Tick]:
        """Returns a cleaned/normalized tick or None if validation fails."""
        # 1. Gap Detection
        if self.last_ts:
            gap = (tick.timestamp - self.last_ts).total_seconds()
            if gap > self.gap_threshold:
                # Log gap for Orchestrator/Evaluator
                print(f"[DataAgent] Warning: Gap detected ({gap:.2f}s) at {tick.timestamp}")
        
        self.last_ts = tick.timestamp

        # 2. Validation
        if not tick.validate():
            return None

        # 3. Normalization (Internal state update)
        self.window.append(tick.price)
        return tick

    def get_z_score(self, current_price: float) -> float:
        """Calculate Z-score for normalization."""
        if len(self.window) < 2:
            return 0.0
        mean_val = sum(self.window) / len(self.window)
        variance = sum((x - mean_val) ** 2 for x in self.window) / len(self.window)
        std_dev = math.sqrt(variance)
        return (current_price - mean_val) / std_dev if std_dev > 0 else 0.0


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
        latency_ms: int = 0,
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
        self._cleaner = DataCleaner()
        self._latest_tick_payload: Optional[Dict[str, object]] = None
        self.latency_ms = max(0, int(latency_ms))

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
                tick = self._next_simulated_tick()
                
                # Jitter simulation
                if self.latency_ms > 0:
                    time.sleep(self._rng.uniform(0, self.latency_ms / 1000.0))
                
                cleaned = self._cleaner.process(tick)
                if cleaned:
                    yield cleaned
        else:
            import threading
            from queue import Queue
            
            payload_queue: Queue[Dict[str, Any]] = Queue()
            live_symbol = self.symbol.replace("/", "").replace("-", "").lower()
            if not live_symbol.endswith("usdt"):
                live_symbol = f"{live_symbol}usdt"

            def _run_async_loop():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                async def _consumer():
                    async for payload in self.live_binance_midprice_stream(symbol=live_symbol):
                        payload_queue.put(payload)
                
                try:
                    loop.run_until_complete(_consumer())
                finally:
                    loop.close()

            background_thread = threading.Thread(target=_run_async_loop, daemon=True)
            background_thread.start()

            try:
                while True:
                    payload = payload_queue.get()
                    price = float(payload["mid_price"])
                    tick = Tick(
                        symbol=self.symbol,
                        price=price,
                        timestamp=datetime.now(timezone.utc),
                        volume=0.0,
                    )
                    if not tick.validate():
                        continue

                    self._last_price = price
                    self._latest_tick_payload = {
                        "timestamp": tick.timestamp.isoformat(),
                        "mid_price": float(tick.price),
                    }
                    yield tick
            finally:
                pass

    def _next_simulated_tick(self) -> Tick:
        change_pct = self._rng.uniform(-0.002, 0.002)
        new_price = max(0.01, self._last_price * (1.0 + change_pct))
        self._last_price = new_price

        # Realistic BTC volume uses a log-normal distribution
        # median ~ 0.5 BTC, with occasional large spikes
        volume = self._rng.lognormvariate(mu=-0.7, sigma=1.2)
        return Tick(
            symbol=self.symbol,
            price=round(new_price, 4),
            timestamp=datetime.now(timezone.utc),
            volume=round(volume, 4),
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
        while self._running:
            try:
                async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                    self.logger_callback = getattr(self, "logger_callback", None)
                    if self.logger_callback: 
                        self.logger_callback("data_feed", f"Connected to {url}")
                    
                    while self._running:
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=60.0)
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
                        except asyncio.TimeoutError:
                            if self.logger_callback:
                                self.logger_callback("data_feed", "Watchdog: 60s timeout reached. Reconnecting...")
                            break
                        except Exception as e:
                            if self.logger_callback:
                                self.logger_callback("data_feed", f"Stream Error: {e}. Reconnecting...")
                            break
            except Exception as e:
                if not self._running: break
                await asyncio.sleep(2.0)


def demo_feed(num_ticks: int = 5) -> None:
    """Simple console demo for manual verification."""
    feed = DataFeed(symbol="BTC/USD", mode="simulated", seed=42, start_price=65000.0)
    ticks = feed.start_feed(tick_count=num_ticks)
    for i, tick in enumerate(ticks, start=1):
        print(f"[{i}] mid_price={tick['mid_price']} ts={tick['timestamp']}")
    feed.stop_feed()


if __name__ == "__main__":
    demo_feed()
