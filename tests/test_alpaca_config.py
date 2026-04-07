import json
import tempfile
import unittest
from pathlib import Path

from alpaca_config import AlpacaConfig


class TestAlpacaConfig(unittest.TestCase):
    def test_load_from_json_file(self) -> None:
        payload = {
            "alpaca": {
                "api_key_id": "key",
                "api_secret_key": "secret",
                "symbols": ["SPY", "QQQ"],
                "risk": {
                    "trade_size": 2.0,
                    "risk_per_trade": 0.02,
                    "daily_loss_limit": 700.0,
                    "confidence_threshold": 0.4,
                    "max_position_size": 6.0,
                    "cooldown_seconds": 3,
                },
                "strategy": {
                    "mr_threshold": 0.004,
                    "mom_threshold": 0.003,
                    "vb_breakout_factor": 1.35,
                },
                "execution": {
                    "max_retries": 4,
                    "retry_backoff_seconds": 1.5,
                },
            }
        }

        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "alpaca_config.json"
            p.write_text(json.dumps(payload), encoding="utf-8")

            cfg = AlpacaConfig.from_file(p)

        self.assertEqual(cfg.api_key_id, "key")
        self.assertEqual(cfg.api_secret_key, "secret")
        self.assertEqual(cfg.symbols, ["SPY", "QQQ"])
        self.assertEqual(cfg.trade_size, 2.0)
        self.assertEqual(cfg.risk_per_trade, 0.02)
        self.assertEqual(cfg.daily_loss_limit, 700.0)
        self.assertEqual(cfg.confidence_threshold, 0.4)
        self.assertEqual(cfg.vb_breakout_factor, 1.35)
        self.assertEqual(cfg.execution_max_retries, 4)
        self.assertEqual(cfg.execution_retry_backoff_seconds, 1.5)


if __name__ == "__main__":
    unittest.main()
