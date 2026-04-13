"""Historical market data feed from CSV files."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from src.miniqs.data.data_feed import Tick


class CSVDataFeed:
    """Provides market ticks replayed from a CSV file.
    
    Expected CSV format (headers optional but recommended):
    timestamp,price,volume
    2023-01-01T00:00:00Z,16500.5,1.2
    """

    def __init__(
        self,
        file_path: str | Path,
        symbol: str = "BTC/USD",
        time_col: str = "timestamp",
        price_col: str = "price",
        vol_col: str = "volume",
    ) -> None:
        self.file_path = Path(file_path)
        self.symbol = symbol
        self.time_col = time_col
        self.price_col = price_col
        self.vol_col = vol_col
        self._latest_tick_payload: Optional[Dict[str, object]] = None

        if not self.file_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.file_path}")

    def stream(self) -> Iterator[Tick]:
        """Yield ticks from the CSV file."""
        with open(self.file_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ts = datetime.fromisoformat(row[self.time_col].replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    
                    price = float(row[self.price_col])
                    volume = float(row.get(self.vol_col, 0.0))
                    
                    tick = Tick(
                        symbol=self.symbol,
                        price=price,
                        timestamp=ts,
                        volume=volume
                    )
                    
                    self._latest_tick_payload = {
                        "timestamp": tick.timestamp.isoformat(),
                        "mid_price": float(tick.price),
                    }
                    yield tick
                except (ValueError, KeyError) as e:
                    print(f"[CSVDataFeed] Skipping invalid row: {row} - Error: {e}")
                    continue

    def start_feed(self, limit: Optional[int] = None) -> List[Dict[str, object]]:
        """Dry run or limited fetch of the feed."""
        payloads: List[Dict[str, object]] = []
        count = 0
        for tick in self.stream():
            payload = {
                "timestamp": tick.timestamp.isoformat(),
                "mid_price": float(tick.price),
            }
            payloads.append(payload)
            count += 1
            if limit and count >= limit:
                break
        return payloads
