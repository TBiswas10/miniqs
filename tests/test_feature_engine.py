from datetime import datetime, timezone
import unittest

from data_feed import Tick
from feature_engine import FeatureEngine


class TestFeatureEngine(unittest.TestCase):
    def _tick(self, price: float) -> Tick:
        return Tick(symbol="TEST", price=price, timestamp=datetime.now(timezone.utc), volume=10.0)

    def test_returns_none_until_enough_history(self) -> None:
        engine = FeatureEngine(ma_window=3, long_ma_window=3, vol_window=3, momentum_window=2)

        self.assertIsNone(engine.update(self._tick(100.0)))
        self.assertIsNone(engine.update(self._tick(101.0)))
        snapshot = engine.update(self._tick(102.0))
        self.assertIsNotNone(snapshot)

    def test_feature_values_for_monotonic_prices(self) -> None:
        engine = FeatureEngine(ma_window=3, long_ma_window=3, vol_window=3, momentum_window=2)
        prices = [100.0, 101.0, 102.0, 103.0]

        snapshot = None
        for price in prices:
            snapshot = engine.update(self._tick(price))

        self.assertIsNotNone(snapshot)
        assert snapshot is not None

        self.assertAlmostEqual(snapshot.rolling_mean, (101.0 + 102.0 + 103.0) / 3, places=6)
        self.assertGreater(snapshot.momentum, 0.0)
        self.assertGreater(snapshot.rolling_volatility, 0.0)

    def test_invalid_windows_raise(self) -> None:
        with self.assertRaises(ValueError):
            FeatureEngine(ma_window=1, long_ma_window=3, vol_window=3, momentum_window=2)

        with self.assertRaises(ValueError):
            FeatureEngine(ma_window=3, long_ma_window=1, vol_window=3, momentum_window=2)

        with self.assertRaises(ValueError):
            FeatureEngine(ma_window=3, long_ma_window=3, vol_window=1, momentum_window=2)

        with self.assertRaises(ValueError):
            FeatureEngine(ma_window=3, long_ma_window=3, vol_window=3, momentum_window=0)

    def test_update_features_and_get_latest_features(self) -> None:
        engine = FeatureEngine(ma_window=20, long_ma_window=50, vol_window=20, momentum_window=10)
        latest = None
        for p in range(100, 200):
            latest = engine.update_features({"timestamp": "2026-01-01T00:00:00+00:00", "mid_price": float(p)})

        self.assertIsNotNone(latest)
        got = engine.get_latest_features()
        self.assertIsNotNone(got)
        assert got is not None
        self.assertIn("rolling_avg_20", got)
        self.assertIn("rolling_avg_50", got)
        self.assertIn("volatility", got)
        self.assertIn("momentum", got)


if __name__ == "__main__":
    unittest.main()
