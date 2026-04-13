import json
import os
import tempfile
import unittest
from pathlib import Path

from src.miniqs.config.alpaca import AlpacaConfig


class TestAlpacaConfig(unittest.TestCase):
    def test_load_from_json_file(self) -> None:
        payload = {
            "alpaca": {
                "api_key_id": "key",
                "api_secret_key": "secret",
                "trading_api_version": "v2",
                "symbols": ["SPY", "QQQ"],
                "src.miniqs.risk": {
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
                "src.miniqs.execution": {
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
        self.assertEqual(cfg.trading_api_version, "v2")
        self.assertEqual(cfg.symbols, ["SPY", "QQQ"])
        self.assertEqual(cfg.trade_size, 2.0)
        self.assertEqual(cfg.risk_per_trade, 0.02)
        self.assertEqual(cfg.daily_loss_limit, 700.0)
        self.assertEqual(cfg.confidence_threshold, 0.4)
        self.assertEqual(cfg.vb_breakout_factor, 1.35)
        self.assertEqual(cfg.execution_max_retries, 4)
        self.assertEqual(cfg.execution_retry_backoff_seconds, 1.5)
        self.assertEqual(
            cfg.strategy_normalization,
            {"mean_reversion": 1.0, "momentum": 1.0, "volatility_breakout": 1.0},
        )
        self.assertEqual(cfg.dominance_cap, 0.65)

    def test_trading_api_version_env_override_is_normalized(self) -> None:
        payload = {
            "alpaca": {
                "api_key_id": "file_key",
                "api_secret_key": "file_secret",
                "trading_api_version": "v2",
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "alpaca_config.json"
            p.write_text(json.dumps(payload), encoding="utf-8")

            prev = dict(os.environ)
            try:
                os.environ["ALPACA_CONFIG_FILE"] = str(p)
                os.environ["ALPACA_API_KEY_ID"] = "env_key"
                os.environ["ALPACA_API_SECRET_KEY"] = "env_secret"
                os.environ["ALPACA_TRADING_API_VERSION"] = "V2"
                cfg = AlpacaConfig.from_env()
            finally:
                os.environ.clear()
                os.environ.update(prev)

        self.assertEqual(cfg.trading_api_version, "v2")

    def test_strategy_normalization_partial_file_payload_uses_defaults(self) -> None:
        payload = {
            "alpaca": {
                "api_key_id": "key",
                "api_secret_key": "secret",
                "strategy": {
                    "strategy_normalization": {
                        "momentum": 0.55,
                    },
                    "dominance_cap": 0.7,
                },
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "alpaca_config.json"
            p.write_text(json.dumps(payload), encoding="utf-8")
            cfg = AlpacaConfig.from_file(p)

        self.assertEqual(cfg.strategy_normalization["momentum"], 0.55)
        self.assertEqual(cfg.strategy_normalization["mean_reversion"], 1.0)
        self.assertEqual(cfg.strategy_normalization["volatility_breakout"], 1.0)
        self.assertEqual(cfg.dominance_cap, 0.7)

    def test_strategy_normalization_malformed_file_payload_falls_back(self) -> None:
        payload = {
            "alpaca": {
                "api_key_id": "key",
                "api_secret_key": "secret",
                "strategy": {
                    "strategy_normalization": {
                        "momentum": "oops",
                        "mean_reversion": -1,
                        "volatility_breakout": 7,
                    },
                    "dominance_cap": 9,
                },
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "alpaca_config.json"
            p.write_text(json.dumps(payload), encoding="utf-8")
            cfg = AlpacaConfig.from_file(p)

        self.assertEqual(
            cfg.strategy_normalization,
            {"mean_reversion": 1.0, "momentum": 1.0, "volatility_breakout": 1.0},
        )
        self.assertEqual(cfg.dominance_cap, 0.65)

    def test_strategy_normalization_malformed_env_payload_falls_back_to_file(self) -> None:
        payload = {
            "alpaca": {
                "api_key_id": "file_key",
                "api_secret_key": "file_secret",
                "strategy": {
                    "strategy_normalization": {
                        "momentum": 0.8,
                        "mean_reversion": 1.1,
                        "volatility_breakout": 0.9,
                    },
                    "dominance_cap": 0.6,
                },
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "alpaca_config.json"
            p.write_text(json.dumps(payload), encoding="utf-8")

            prev = dict(os.environ)
            try:
                os.environ["ALPACA_CONFIG_FILE"] = str(p)
                os.environ["ALPACA_API_KEY_ID"] = "env_key"
                os.environ["ALPACA_API_SECRET_KEY"] = "env_secret"
                os.environ["ALPACA_STRATEGY_NORMALIZATION"] = "{bad-json"
                os.environ["ALPACA_DOMINANCE_CAP"] = "20"
                cfg = AlpacaConfig.from_env()
            finally:
                os.environ.clear()
                os.environ.update(prev)

        self.assertEqual(
            cfg.strategy_normalization,
            {"mean_reversion": 1.1, "momentum": 0.8, "volatility_breakout": 0.9},
        )
        self.assertEqual(cfg.dominance_cap, 0.6)


if __name__ == "__main__":
    unittest.main()
