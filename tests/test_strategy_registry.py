from datetime import datetime, timezone
import unittest

from feature_engine import FeatureSnapshot
from strategies import StrategySignal, default_strategy_registry, generate_weighted_signals


class _AlwaysBuyMomentum:
    name = "momentum"

    def generate_signal(self, features: FeatureSnapshot, **params: float) -> StrategySignal:
        _ = features
        _ = params
        return StrategySignal(strategy="momentum", action="buy", confidence=0.9, reason="custom_override")


def _features() -> FeatureSnapshot:
    return FeatureSnapshot(
        symbol="TEST",
        timestamp=datetime.now(timezone.utc),
        price=100.0,
        rolling_mean=100.0,
        rolling_volatility=0.01,
        momentum=0.001,
    )


class TestStrategyRegistry(unittest.TestCase):
    def test_hot_swap_strategy(self) -> None:
        registry = default_strategy_registry()
        registry.swap("momentum", _AlwaysBuyMomentum())

        signals = generate_weighted_signals(
            features=_features(),
            registry=registry,
            weights={"mean_reversion": 0.4, "momentum": 1.0, "volatility_breakout": 0.2},
            enabled={"mean_reversion": True, "momentum": True, "volatility_breakout": True},
            params={
                "mean_reversion": {"entry_threshold": 0.003},
                "momentum": {"momentum_threshold": 0.002},
                "volatility_breakout": {"breakout_factor": 1.2},
            },
        )

        self.assertIn("momentum", signals)
        self.assertEqual(signals["momentum"].action, "buy")
        self.assertEqual(signals["momentum"].reason, "custom_override")


if __name__ == "__main__":
    unittest.main()
