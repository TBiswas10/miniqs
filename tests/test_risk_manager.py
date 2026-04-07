from datetime import datetime, timedelta, timezone
import unittest

from risk_manager import check_risk


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
        self.assertIn("max session loss", reason_loss)

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
