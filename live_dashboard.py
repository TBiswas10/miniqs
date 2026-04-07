"""Append-only JSONL dashboard + latest snapshot JSON + CSV row for live sessions."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _ensure_parent(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def append_jsonl(path: str, row: Dict[str, Any]) -> None:
    _ensure_parent(path)
    line = json.dumps(row, default=str)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def write_snapshot(path: str, snapshot: Dict[str, Any]) -> None:
    _ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, default=str)


def append_csv_row(path: str, fieldnames: List[str], row: Dict[str, Any]) -> None:
    _ensure_parent(path)
    file_exists = Path(path).is_file()
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists:
            w.writeheader()
        w.writerow(row)


def dashboard_row(
    *,
    event: str,
    metrics: Dict[str, Any],
    weights: Dict[str, float],
    symbol: str,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    ts = datetime.now(timezone.utc).isoformat()
    out: Dict[str, Any] = {
        "ts": ts,
        "event": event,
        "symbol": symbol,
        "weights_mean_reversion": weights.get("mean_reversion"),
        "weights_momentum": weights.get("momentum"),
        "weights_volatility_breakout": weights.get("volatility_breakout"),
        **metrics,
    }
    if extra:
        out.update(extra)
    return out
