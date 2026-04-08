from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from feature_engine import FeatureSnapshot
from strategies.mean_reversion import generate_signal as mean_reversion_signal
from strategies.momentum import generate_signal as momentum_signal
from strategies.volatility_breakout import generate_signal as volatility_breakout_signal


def _features(price: float, mean: float, momentum: float) -> FeatureSnapshot:
    return FeatureSnapshot(
        symbol="TEST",
        timestamp=datetime.now(timezone.utc),
        price=price,
        rolling_mean=mean,
        rolling_volatility=0.01,
        momentum=momentum,
        realized_vol_short=0.01,
        realized_vol_long=0.01,
        spread_bps=5.0,
        book_imbalance=0.0,
        rel_volume=1.0,
        volume_zscore=0.0,
        trend_slope_short=0.0,
        trend_slope_long=0.0,
        distance_to_ma50=0.0,
    )


def _feature_with_meta(
    price: float,
    mean: float,
    momentum: float,
    **meta: float,
) -> SimpleNamespace:
    base = _features(price=price, mean=mean, momentum=momentum)
    payload = {
        "symbol": base.symbol,
        "timestamp": base.timestamp,
        "price": base.price,
        "rolling_mean": base.rolling_mean,
        "rolling_volatility": base.rolling_volatility,
        "momentum": base.momentum,
    }
    payload.update(meta)
    return SimpleNamespace(**payload)


class TestMeanReversionStrategy(unittest.TestCase):
    def test_buy_when_price_below_mean(self) -> None:
        signal = mean_reversion_signal(_features(price=99.0, mean=100.0, momentum=0.0), entry_threshold=0.003)
        self.assertEqual(signal.action, "buy")
        self.assertGreaterEqual(signal.confidence, 0.0)
        self.assertLessEqual(signal.confidence, 1.0)

    def test_sell_when_price_above_mean(self) -> None:
        signal = mean_reversion_signal(_features(price=101.0, mean=100.0, momentum=0.0), entry_threshold=0.003)
        self.assertEqual(signal.action, "sell")

    def test_hold_when_within_threshold(self) -> None:
        signal = mean_reversion_signal(_features(price=100.1, mean=100.0, momentum=0.0), entry_threshold=0.003)
        self.assertEqual(signal.action, "hold")

    def test_hold_when_spread_is_wide(self) -> None:
        signal = mean_reversion_signal(
            _feature_with_meta(price=99.0, mean=100.0, momentum=0.0, spread=0.0035),
            max_spread=0.002,
        )
        self.assertEqual(signal.action, "hold")
        self.assertIn("spread filter", signal.reason)

    def test_hold_when_order_imbalance_out_of_range(self) -> None:
        signal = mean_reversion_signal(
            _feature_with_meta(price=101.0, mean=100.0, momentum=0.0, order_imbalance=0.85),
            min_order_imbalance=-0.2,
            max_order_imbalance=0.2,
        )
        self.assertEqual(signal.action, "hold")
        self.assertIn("imbalance filter", signal.reason)

    def test_hold_when_volatility_too_high(self) -> None:
        signal = mean_reversion_signal(
            _feature_with_meta(price=99.0, mean=100.0, momentum=0.0, rolling_volatility=0.05),
            max_volatility=0.03,
        )
        self.assertEqual(signal.action, "hold")
        self.assertIn("volatility filter", signal.reason)


class TestMomentumStrategy(unittest.TestCase):
    def test_buy_on_positive_momentum(self) -> None:
        signal = momentum_signal(_features(price=100.0, mean=100.0, momentum=0.01), momentum_threshold=0.002)
        self.assertEqual(signal.action, "buy")
        self.assertGreaterEqual(signal.confidence, 0.0)
        self.assertLessEqual(signal.confidence, 1.0)

    def test_sell_on_negative_momentum(self) -> None:
        signal = momentum_signal(_features(price=100.0, mean=100.0, momentum=-0.01), momentum_threshold=0.002)
        self.assertEqual(signal.action, "sell")

    def test_hold_on_small_momentum(self) -> None:
        signal = momentum_signal(_features(price=100.0, mean=100.0, momentum=0.0005), momentum_threshold=0.002)
        self.assertEqual(signal.action, "hold")

    def test_hold_when_trend_persistence_is_weak(self) -> None:
        signal = momentum_signal(
            _feature_with_meta(price=100.5, mean=100.0, momentum=0.01, trend_persistence=0.4, volume_confirmation=1.5),
            min_trend_persistence=0.55,
            min_volume_confirmation=1.0,
        )
        self.assertEqual(signal.action, "hold")
        self.assertIn("trend persistence", signal.reason)

    def test_hold_when_volume_confirmation_is_weak(self) -> None:
        signal = momentum_signal(
            _feature_with_meta(price=100.5, mean=100.0, momentum=0.01, trend_persistence=0.8, volume_confirmation=0.6),
            min_trend_persistence=0.55,
            min_volume_confirmation=1.0,
        )
        self.assertEqual(signal.action, "hold")
        self.assertIn("volume confirmation", signal.reason)

    def test_buy_when_persistence_and_volume_confirm(self) -> None:
        signal = momentum_signal(
            _feature_with_meta(price=100.5, mean=100.0, momentum=0.01, trend_persistence=0.9, volume_confirmation=1.3),
            min_trend_persistence=0.55,
            min_volume_confirmation=1.0,
        )
        self.assertEqual(signal.action, "buy")


class TestVolatilityBreakoutStrategy(unittest.TestCase):
    def test_buy_on_volatility_breakout(self) -> None:
        signal = volatility_breakout_signal(
            _features(price=100.0, mean=100.0, momentum=0.03),
            breakout_factor=1.2,
        )
        self.assertEqual(signal.action, "buy")

    def test_sell_on_volatility_breakdown(self) -> None:
        signal = volatility_breakout_signal(
            _features(price=100.0, mean=100.0, momentum=-0.03),
            breakout_factor=1.2,
        )
        self.assertEqual(signal.action, "sell")

    def test_hold_inside_vol_band(self) -> None:
        signal = volatility_breakout_signal(
            _features(price=100.0, mean=100.0, momentum=0.001),
            breakout_factor=1.2,
        )
        self.assertEqual(signal.action, "hold")

    def test_hold_when_return_volatility_expansion_is_weak(self) -> None:
        signal = volatility_breakout_signal(
            _feature_with_meta(
                price=100.5,
                mean=100.0,
                momentum=0.03,
                return_volatility=0.01,
                baseline_return_volatility=0.01,
                spread=0.001,
                volume_confirmation=1.5,
            ),
            min_volatility=0.005,
            min_volatility_expansion=1.2,
        )
        self.assertEqual(signal.action, "hold")
        self.assertIn("expansion too weak", signal.reason)

    def test_hold_when_spread_is_too_wide(self) -> None:
        signal = volatility_breakout_signal(
            _feature_with_meta(
                price=100.5,
                mean=100.0,
                momentum=0.03,
                return_volatility=0.02,
                baseline_return_volatility=0.01,
                spread=0.004,
                volume_confirmation=1.5,
            ),
            max_spread=0.002,
        )
        self.assertEqual(signal.action, "hold")
        self.assertIn("spread too wide", signal.reason)

    def test_hold_when_volume_confirmation_is_weak(self) -> None:
        signal = volatility_breakout_signal(
            _feature_with_meta(
                price=100.5,
                mean=100.0,
                momentum=0.03,
                return_volatility=0.02,
                baseline_return_volatility=0.01,
                spread=0.001,
                volume_confirmation=0.7,
            ),
            min_volume_confirmation=1.0,
        )
        self.assertEqual(signal.action, "hold")
        self.assertIn("volume confirmation", signal.reason)


if __name__ == "__main__":
    unittest.main()
