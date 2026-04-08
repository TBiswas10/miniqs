from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from decision_terminal.backend.event_engine import EventEngine


class _StubStore:
    def persist(self, _event) -> None:
        return None


async def _noop_kill_switch(_reason: str) -> None:
    return None


class TestDecisionTerminalEventEngine(unittest.TestCase):
    def _engine(self) -> EventEngine:
        return EventEngine(
            trace_path=Path(tempfile.mkdtemp(prefix="event_engine_trace_")) / "trace.jsonl",
            store=_StubStore(),
            get_control_state=lambda: {},
            trigger_kill_switch=_noop_kill_switch,
        )

    def test_no_signal_uses_strongest_strategy_confidence(self) -> None:
        engine = self._engine()
        row = {
            "kind": "decision",
            "timestamp": "2026-04-08T04:41:52.997231+00:00",
            "symbol": "BTC/USD",
            "stage": "no_signal",
            "signals": {
                "mean_reversion": {"action": "hold", "confidence": 0.0, "reason": "volatility filter"},
                "momentum": {"action": "hold", "confidence": 0.29816, "reason": "trend mismatch"},
                "volatility_breakout": {"action": "hold", "confidence": 0.2, "reason": "threshold"},
            },
            "chosen": None,
            "detail": "confidence_below_threshold",
        }

        events = engine._map_trace_row(row)
        self.assertTrue(events)
        signal_event = next(event for event in events if event.event_type == "strategy_signal")
        portfolio_event = next(event for event in events if event.event_type == "portfolio_update")
        self.assertEqual(signal_event.payload.get("side"), "HOLD")
        self.assertEqual(signal_event.payload.get("strategy"), "momentum")
        self.assertAlmostEqual(float(signal_event.payload.get("confidence", 0.0)), 0.29816, places=6)
        self.assertEqual(portfolio_event.strategy_id, "none")

    def test_chosen_signal_takes_priority_when_present(self) -> None:
        engine = self._engine()
        row = {
            "kind": "decision",
            "timestamp": "2026-04-08T04:42:52.997231+00:00",
            "symbol": "BTC/USD",
            "signals": {
                "momentum": {"action": "hold", "confidence": 0.75, "reason": "hold"},
            },
            "chosen": {"strategy": "mean_reversion", "action": "buy", "confidence": 0.64, "reason": "vote"},
        }

        events = engine._map_trace_row(row)
        signal_event = next(event for event in events if event.event_type == "strategy_signal")
        self.assertEqual(signal_event.payload.get("side"), "BUY")
        self.assertEqual(signal_event.payload.get("strategy"), "mean_reversion")
        self.assertAlmostEqual(float(signal_event.payload.get("confidence", 0.0)), 0.64, places=6)


if __name__ == "__main__":
    unittest.main()
