from datetime import datetime, timedelta, timezone
import unittest

from src.miniqs.risk.risk_manager import check_risk


class TestRiskManager(unittest.TestCase):
    def test_multiple_trade_risk_rules(self) -> None:
        now = datetime.now(timezone.utc)
        base_state = {
            "current_position": 2.0,
            "last_trade_timestamp": now - timedelta(seconds=120),
            "session_loss": 100.0,
            "max_position_size": 5.0,
            "cooldown_seconds": 60,
            "max_loss_per_session": 500.0,
            "daily_loss_limit": 500.0,
            "confidence_threshold": 0.35,
            "risk_per_trade": 0.02,
            "equity": 100000.0,
            "max_exposure": 1.0,
        }

        allow, reason = check_risk(
            {"action": "buy", "size": 1.0, "confidence": 0.8, "timestamp": now},
            base_state,
        )
        self.assertTrue(allow)
        self.assertEqual(reason, "allowed")

        block_pos, reason_pos = check_risk(
            {"action": "buy", "size": 5.0, "confidence": 0.9, "timestamp": now},
            base_state,
        )
        self.assertFalse(block_pos)
        self.assertIn("max position", reason_pos)

        cooldown_state = dict(base_state)
        cooldown_state["last_trade_timestamp"] = now - timedelta(seconds=10)
        block_cd, reason_cd = check_risk(
            {"action": "sell", "size": 1.0, "confidence": 0.7, "timestamp": now},
            cooldown_state,
        )
        self.assertFalse(block_cd)
        self.assertIn("cooldown", reason_cd)

        loss_state = dict(base_state)
        loss_state["session_loss"] = 500.0
        block_loss, reason_loss = check_risk(
            {"action": "sell", "size": 1.0, "confidence": 0.7, "timestamp": now},
            loss_state,
        )
        self.assertFalse(block_loss)
        self.assertIn("daily loss kill switch", reason_loss)

    def test_confidence_and_risk_budget_gate(self) -> None:
        now = datetime.now(timezone.utc)
        state = {
            "current_position": 0.0,
            "last_trade_timestamp": now - timedelta(seconds=120),
            "session_loss": 0.0,
            "max_position_size": 20.0,
            "cooldown_seconds": 0,
            "daily_loss_limit": 1000.0,
            "risk_per_trade": 0.01,
            "confidence_threshold": 0.6,
            "equity": 1000.0,
            "max_exposure": 1.0,
        }

        block_conf, reason_conf = check_risk(
            {"action": "buy", "size": 1.0, "price": 100.0, "confidence": 0.4, "timestamp": now},
            state,
        )
        self.assertFalse(block_conf)
        self.assertIn("confidence threshold", reason_conf)

        block_risk, reason_risk = check_risk(
            {"action": "buy", "size": 1.0, "price": 100.0, "confidence": 0.9, "timestamp": now},
            state,
        )
        self.assertFalse(block_risk)
        self.assertIn("src.miniqs.risk per trade", reason_risk)

    def test_max_exposure_and_concurrent_positions(self) -> None:
        now = datetime.now(timezone.utc)
        exposure_state = {
            "current_position": 0.0,
            "open_positions_count": 0,
            "max_concurrent_positions": 5,
            "last_trade_timestamp": now - timedelta(seconds=120),
            "session_loss": 0.0,
            "max_position_size": 20.0,
            "cooldown_seconds": 0,
            "daily_loss_limit": 1000.0,
            "risk_per_trade": 1.0,
            "confidence_threshold": 0.3,
            "equity": 1000.0,
            "max_exposure": 0.2,
        }

        block_exposure, reason_exposure = check_risk(
            {"action": "buy", "size": 3.0, "price": 100.0, "confidence": 0.9, "timestamp": now},
            exposure_state,
        )
        self.assertFalse(block_exposure)
        self.assertIn("max exposure", reason_exposure)

        concurrent_state = dict(exposure_state)
        concurrent_state["open_positions_count"] = 2
        concurrent_state["max_concurrent_positions"] = 2
        concurrent_state["max_exposure"] = 1.0

        block_concurrent, reason_concurrent = check_risk(
            {"action": "buy", "size": 1.0, "price": 10.0, "confidence": 0.9, "timestamp": now},
            concurrent_state,
        )
        self.assertFalse(block_concurrent)
        self.assertIn("max concurrent positions", reason_concurrent)

    def test_cannot_sell_more_than_position(self) -> None:
        now = datetime.now(timezone.utc)
        state = {
            "current_position": 0.0,
            "last_trade_timestamp": now - timedelta(seconds=120),
            "session_loss": 0.0,
            "max_position_size": 5.0,
            "cooldown_seconds": 0,
            "max_loss_per_session": 500.0,
        }
        allow, reason = check_risk(
            {"action": "sell", "size": 1.0, "confidence": 0.7, "timestamp": now},
            state,
        )
        self.assertFalse(allow)
        self.assertIn("cannot sell more than position", reason)


if __name__ == "__main__":
    unittest.main()
