from __future__ import annotations

import unittest
from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient

from decision_terminal.backend.main import (
    app,
    _build_decision_inspector,
    _clamp01,
    _confidence_decomposition,
    _counterfactual_replay,
    _hold_reasons,
    _risk_debug,
    _strategy_health,
)


class TestDecisionTerminalExplainability(unittest.TestCase):
    def _sample_history(self) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        rows: list[dict[str, Any]] = []
        for idx in range(12):
            strategy = "momentum" if idx % 2 == 0 else "mean_reversion"
            action = "EXECUTED" if idx % 3 == 0 else "HOLD"
            confidence = 0.62 if action == "EXECUTED" else 0.31
            rows.append(
                {
                    "ts": now,
                    "symbol": "BTC/USD",
                    "signal": "BUY" if action == "EXECUTED" else "HOLD",
                    "action": action,
                    "strategy": strategy,
                    "confidence": confidence,
                    "pnl": 30.0 if action == "EXECUTED" else 0.0,
                    "price": 70000.0 + idx,
                    "reason": "ok" if action == "EXECUTED" else "no_actionable_signal",
                    "risk_checks": [],
                    "raw": {
                        "raw": {
                            "signals": {
                                "mean_reversion": {"action": "hold", "confidence": 0.2, "reason": "range"},
                                "momentum": {"action": "buy", "confidence": 0.62, "reason": "trend"},
                                "volatility_breakout": {"action": "hold", "confidence": 0.1, "reason": "quiet"},
                            },
                            "stage": "signals_generated",
                            "detail": "ok",
                            "position_size": 0.5,
                            "equity": 100000.0,
                            "drawdown": 120.0,
                        }
                    },
                }
            )
        return rows

    def _sample_signal(self) -> dict[str, Any]:
        return {
            "strategy": "momentum",
            "side": "HOLD",
            "confidence": 0.34,
            "reason": "ensemble_score_below_threshold",
            "raw": {
                "raw": {
                    "tick": 101,
                    "stage": "no_signal",
                    "detail": "confidence_below_threshold",
                    "signals": {
                        "mean_reversion": {"action": "hold", "confidence": 0.22, "reason": "volatility filter"},
                        "momentum": {"action": "buy", "confidence": 0.34, "reason": "trend weak"},
                        "volatility_breakout": {"action": "sell", "confidence": 0.30, "reason": "breakout weak"},
                    },
                    "position_size": 0.75,
                    "equity": 100000.0,
                    "drawdown": 250.0,
                }
            },
        }

    def _assert_no_none(self, value: Any) -> None:
        if isinstance(value, dict):
            for sub in value.values():
                self._assert_no_none(sub)
        elif isinstance(value, list):
            for sub in value:
                self._assert_no_none(sub)
        else:
            self.assertIsNotNone(value)

    def test_confidence_decomposition_populated_and_normalized(self) -> None:
        history = self._sample_history()
        signal = self._sample_signal()
        health = _strategy_health(history, ["mean_reversion", "momentum", "volatility_breakout"], window=80)
        confidence = _confidence_decomposition(signal, signal["raw"]["raw"], health)

        self.assertEqual(set(confidence.keys()), {"signal_strength", "agreement", "regime_fit", "historical_edge", "final"})
        for value in confidence.values():
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)

    def test_hold_reasons_top_three_sorted(self) -> None:
        history = self._sample_history()
        signal = self._sample_signal()
        health = _strategy_health(history, ["mean_reversion", "momentum", "volatility_breakout"], window=80)
        confidence = _confidence_decomposition(signal, signal["raw"]["raw"], health)
        debug = _risk_debug(confidence, {"position_size": 0.9, "equity": 100000.0, "drawdown": 500.0}, {"confidence_threshold": 0.5, "max_position_size": 0.8, "portfolio_drawdown_limit": 0.003})
        reasons = _hold_reasons(confidence, debug)

        self.assertEqual(len(reasons), 3)
        impacts = [float(row["impact"]) for row in reasons]
        self.assertEqual(impacts, sorted(impacts, reverse=True))
        allowed = {"low confidence", "strategy disagreement", "regime mismatch", "risk gate failure"}
        self.assertTrue(all(str(row["reason"]) in allowed for row in reasons))

    def test_strategy_health_fields_exist(self) -> None:
        health = _strategy_health(self._sample_history(), ["mean_reversion", "momentum", "volatility_breakout"], window=20)
        self.assertEqual(set(health.keys()), {"mean_reversion", "momentum", "volatility_breakout"})
        for row in health.values():
            for key in ("participation_rate", "avg_confidence", "recent_hit_rate", "contribution_score", "health_score", "status"):
                self.assertIn(key, row)
                self.assertIsNotNone(row[key])

    def test_risk_debug_all_gates_present(self) -> None:
        debug = _risk_debug(
            {"signal_strength": 0.5, "agreement": 0.5, "regime_fit": 0.5, "historical_edge": 0.5, "final": 0.5},
            {"position_size": 0.4, "equity": 100000.0, "drawdown": 120.0},
            {"confidence_threshold": 0.35, "max_position_size": 1.0, "portfolio_drawdown_limit": 0.01},
        )
        self.assertEqual(set(debug.keys()), {"confidence_gate", "position_limit", "drawdown_guard"})
        for gate in debug.values():
            for key in gate.keys():
                self.assertIsNotNone(gate[key])

    def test_counterfactual_replay_deterministic(self) -> None:
        timeline = self._sample_history()[-8:]
        controls = {"risk": {"confidence_threshold": 0.4, "max_position_size": 1.0}}
        override = {"confidence_threshold": 0.3, "strategy_weights": {"momentum": 1.2, "mean_reversion": 0.9}}
        out1 = _counterfactual_replay(timeline, controls, input_prices=[row["price"] for row in timeline], config_override=override)
        out2 = _counterfactual_replay(timeline, controls, input_prices=[row["price"] for row in timeline], config_override=override)
        self.assertEqual(out1, out2)
        self.assertIn("counterfactual_result", out1)

    def test_inspector_payload_is_not_empty_for_live_signal(self) -> None:
        history = self._sample_history()
        signal = self._sample_signal()
        health = _strategy_health(history, ["mean_reversion", "momentum", "volatility_breakout"], window=80)
        confidence = _confidence_decomposition(signal, signal["raw"]["raw"], health)
        debug = _risk_debug(confidence, {"position_size": 0.75, "equity": 100000.0, "drawdown": 250.0}, {"confidence_threshold": 0.35, "max_position_size": 1.0, "portfolio_drawdown_limit": 0.01})
        reasons = _hold_reasons(confidence, debug)
        inspector = _build_decision_inspector(
            latest_signal=signal,
            latest_risk={"risk_type": "trade_block", "severity": "warn", "reason": "test"},
            controls={"trading_enabled": True, "kill_switch": False},
            control_risk={"confidence_threshold": 0.35},
            confidence=confidence,
            hold_reasons=reasons,
            risk_debug=debug,
        )

        self.assertTrue(inspector["features"])
        self.assertTrue(inspector["risk_checks"])
        self._assert_no_none(inspector)

    def test_clamp01_bounds(self) -> None:
        self.assertEqual(_clamp01(-5), 0.0)
        self.assertEqual(_clamp01(5), 1.0)

    def test_snapshot_endpoint_explainability_schema(self) -> None:
        with TestClient(app) as client:
            response = client.get("/api/decision/snapshot")
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertIn("decision", payload)
        signal = payload["decision"]["signal"]
        self.assertIn("confidence", signal)
        confidence = signal["confidence"]
        self.assertEqual(set(confidence.keys()), {"signal_strength", "agreement", "regime_fit", "historical_edge", "final"})

        self.assertIn("hold_reasons", payload)
        self.assertIn("strategy_health", payload)
        self.assertIn("risk_debug", payload)
        self.assertIn("decision_inspector", payload)
        self.assertIn("counterfactual_result", payload)

        for key in ("confidence_gate", "position_limit", "drawdown_guard"):
            self.assertIn(key, payload["risk_debug"])

        inspector = payload["decision_inspector"]
        self.assertIn("features", inspector)
        self.assertIn("risk_checks", inspector)
        self.assertTrue(isinstance(inspector["features"], dict))
        self.assertTrue(isinstance(inspector["risk_checks"], list))

        required_subset = {
            "decision": {
                "signal": signal,
            },
            "hold_reasons": payload["hold_reasons"],
            "strategy_health": payload["strategy_health"],
            "risk_debug": payload["risk_debug"],
            "decision_inspector": payload["decision_inspector"],
            "counterfactual_result": payload["counterfactual_result"],
        }
        self._assert_no_none(required_subset)


if __name__ == "__main__":
    unittest.main()
