from datetime import datetime, timezone
import unittest

import numpy as np

from src.miniqs.data.data_feed import Tick
from src.miniqs.engine.feature_engine import FeatureEngine


class TestFeatureEngine(unittest.TestCase):
    def _tick(self, price: float, volume: float = 10.0) -> Tick:
        return Tick(symbol="TEST", price=price, timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc), volume=volume)

    def test_returns_none_until_enough_history(self) -> None:
        engine = FeatureEngine(ma_window=3, long_ma_window=3, vol_window=3, momentum_window=2)

        self.assertIsNone(engine.update(self._tick(100.0)))
        self.assertIsNone(engine.update(self._tick(101.0)))
        self.assertIsNone(engine.update(self._tick(102.0)))
        snapshot = engine.update(self._tick(103.0))
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
        self.assertGreaterEqual(snapshot.realized_vol_short, 0.0)
        self.assertGreaterEqual(snapshot.realized_vol_long, 0.0)

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
            latest = engine.update_features(
                {"timestamp": "2026-01-01T00:00:00+00:00", "mid_price": float(p), "volume": float(p - 50)}
            )

        self.assertIsNotNone(latest)
        got = engine.get_latest_features()
        self.assertIsNotNone(got)
        assert got is not None
        self.assertIn("rolling_avg_20", got)
        self.assertIn("rolling_avg_50", got)
        self.assertIn("volatility", got)
        self.assertIn("momentum", got)
        self.assertIn("realized_vol_short", got)
        self.assertIn("realized_vol_long", got)
        self.assertIn("spread_bps", got)
        self.assertIn("book_imbalance", got)
        self.assertIn("rel_volume", got)
        self.assertIn("volume_zscore", got)
        self.assertIn("trend_slope_short", got)
        self.assertIn("trend_slope_long", got)
        self.assertIn("distance_to_ma50", got)

    def test_new_features_match_expected_values(self) -> None:
        engine = FeatureEngine(ma_window=3, long_ma_window=5, vol_window=4, momentum_window=2, debug=False)
        prices = [100.0, 101.0, 103.0, 102.0, 104.0, 106.0]
        volumes = [10.0, 12.0, 11.0, 14.0, 18.0, 20.0]

        snapshot = None
        for p, v in zip(prices, volumes):
            snapshot = engine.update(self._tick(p, v))

        self.assertIsNotNone(snapshot)
        assert snapshot is not None

        px = np.array(prices, dtype=float)
        vol = np.array(volumes, dtype=float)
        vol_slice = px[-4:]
        current_price = px[-1]
        long_ma = px[-5:].mean()

        expected_realized_vol_short = float(np.std(np.log(vol_slice[1:] / vol_slice[:-1]), ddof=0))
        expected_realized_vol_long = float(np.std(np.log(px[-6:][1:] / px[-6:][:-1]), ddof=0))
        expected_spread_bps = float(((vol_slice.max() - vol_slice.min()) / current_price) * 1e4)

        diffs = np.diff(vol_slice, prepend=vol_slice[0])
        signed_volume = np.sign(diffs) * vol[-4:]
        expected_book_imbalance = float(signed_volume.sum() / vol[-4:].sum())

        expected_rel_volume = float(vol[-1] / vol[-5:].mean())
        expected_volume_zscore = float((vol[-1] - vol[-3:].mean()) / vol[-3:].std(ddof=0))

        short_ma_series = np.convolve(px, np.ones(3) / 3, mode="valid")
        long_ma_series = np.convolve(px, np.ones(5) / 5, mode="valid")
        expected_trend_slope_short = float(np.polyfit(np.arange(len(short_ma_series[-3:])), short_ma_series[-3:], 1)[0])
        expected_trend_slope_long = float(np.polyfit(np.arange(len(long_ma_series[-3:])), long_ma_series[-3:], 1)[0])
        expected_distance_to_ma50 = float((current_price - long_ma) / long_ma)

        self.assertAlmostEqual(snapshot.realized_vol_short, expected_realized_vol_short, places=8)
        self.assertAlmostEqual(snapshot.rolling_volatility, expected_realized_vol_short, places=8)
        self.assertAlmostEqual(snapshot.realized_vol_long, expected_realized_vol_long, places=8)
        self.assertAlmostEqual(snapshot.spread_bps, expected_spread_bps, places=8)
        self.assertAlmostEqual(snapshot.book_imbalance, expected_book_imbalance, places=8)
        self.assertAlmostEqual(snapshot.rel_volume, expected_rel_volume, places=8)
        self.assertAlmostEqual(snapshot.volume_zscore, expected_volume_zscore, places=8)
        self.assertAlmostEqual(snapshot.trend_slope_short, expected_trend_slope_short, places=8)
        self.assertAlmostEqual(snapshot.trend_slope_long, expected_trend_slope_long, places=8)
        self.assertAlmostEqual(snapshot.distance_to_ma50, expected_distance_to_ma50, places=8)

    def test_quote_microstructure_fields_reach_feature_input(self) -> None:
        engine = FeatureEngine(ma_window=3, long_ma_window=3, vol_window=3, momentum_window=2, debug=False)
        ticks = [
            Tick(symbol="SPY", price=500.00, timestamp=datetime.now(timezone.utc), volume=20.0, message_type="q", bid_price=499.99, ask_price=500.01, bid_size=10.0, ask_size=10.0),
            Tick(symbol="SPY", price=500.02, timestamp=datetime.now(timezone.utc), volume=20.0, message_type="q", bid_price=500.01, ask_price=500.03, bid_size=12.0, ask_size=8.0),
            Tick(symbol="SPY", price=500.04, timestamp=datetime.now(timezone.utc), volume=22.0, message_type="q", bid_price=500.03, ask_price=500.05, bid_size=14.0, ask_size=8.0),
        ]
        for tick in ticks:
            engine.update_features(tick)

        latest_input = engine.get_latest_event_input()
        self.assertIsNotNone(latest_input)
        assert latest_input is not None
        self.assertEqual(latest_input["message_type"], "q")
        self.assertEqual(latest_input["bid_price"], 500.03)
        self.assertEqual(latest_input["ask_price"], 500.05)
        self.assertEqual(latest_input["bid_size"], 14.0)
        self.assertEqual(latest_input["ask_size"], 8.0)
        self.assertIn("mid_price", latest_input)


if __name__ == "__main__":
    unittest.main()
