from datetime import datetime, timezone
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
    )


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


if __name__ == "__main__":
    unittest.main()
