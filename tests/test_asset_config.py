from datetime import datetime, timezone
import unittest

from src.miniqs.config.asset import default_asset_config, is_asset_tradable_now, resolve_asset_config


class TestAssetConfig(unittest.TestCase):
    def test_default_crypto_config(self) -> None:
        cfg = default_asset_config("BTC/USD")
        self.assertEqual(cfg.asset_type, "crypto")
        self.assertIsNone(cfg.market_hours)
        self.assertGreater(cfg.trading_fees, 0.0)

    def test_default_equity_config(self) -> None:
        cfg = default_asset_config("SPY")
        self.assertEqual(cfg.asset_type, "equity")
        self.assertIsNotNone(cfg.market_hours)

    def test_market_hours_gate_for_equity(self) -> None:
        cfg = resolve_asset_config(symbol="SPY", asset_type="equity")
        # 14:31 UTC on Monday is 09:31 ET during standard time windows for this test case.
        open_time = datetime(2026, 1, 5, 14, 31, tzinfo=timezone.utc)
        closed_time = datetime(2026, 1, 4, 14, 31, tzinfo=timezone.utc)  # Sunday
        self.assertTrue(is_asset_tradable_now(cfg, open_time))
        self.assertFalse(is_asset_tradable_now(cfg, closed_time))


if __name__ == "__main__":
    unittest.main()
