from datetime import datetime, timezone
import unittest

from event_bus import EventBus, SignalEvent
from feature_engine import FeatureSnapshot
from strategies import StrategySignal
from strategies.mean_reversion import generate_signal as mean_reversion_signal
from strategies.momentum import generate_signal as momentum_signal
from strategy_evaluator import emit_signal_event, evaluate_signals


def _features(price: float, mean: float, momentum: float) -> FeatureSnapshot:
    return FeatureSnapshot(
        symbol="TEST",
        timestamp=datetime.now(timezone.utc),
        price=price,
        rolling_mean=mean,
        rolling_volatility=0.02,
        momentum=momentum,
    )


class TestStrategyEvaluator(unittest.TestCase):
    def test_selects_highest_confidence_signal_from_strategies(self) -> None:
        features = _features(price=102.0, mean=100.0, momentum=0.02)
        signals = [
            mean_reversion_signal(features, entry_threshold=0.005),
            momentum_signal(features, momentum_threshold=0.002),
        ]

        chosen = evaluate_signals(signals, confidence_threshold=0.6)

        self.assertIsNotNone(chosen)
        assert chosen is not None
        self.assertEqual(chosen.strategy, "momentum")
        self.assertEqual(chosen.action, "buy")
        self.assertGreaterEqual(chosen.confidence, 0.6)

    def test_returns_none_below_threshold(self) -> None:
        features = _features(price=100.1, mean=100.0, momentum=0.0005)
        signals = [
            mean_reversion_signal(features, entry_threshold=0.01),
            momentum_signal(features, momentum_threshold=0.01),
        ]

        chosen = evaluate_signals(signals, confidence_threshold=0.9)
        self.assertIsNone(chosen)

    def test_emit_signal_event_publishes_signal_event(self) -> None:
        bus = EventBus()
        chosen = StrategySignal("momentum", "buy", 0.88, "strong_trend")
        trade = {
            "action": "buy",
            "size": 1.0,
            "confidence": 0.88,
            "price": 101.5,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "strategy": "momentum",
            "symbol": "SIM",
        }
        risk_state = {"max_position_size": 5.0}

        emit_signal_event(bus=bus, chosen=chosen, trade=trade, risk_state=risk_state)
        event = bus.consume()

        self.assertIsInstance(event, SignalEvent)
        assert isinstance(event, SignalEvent)
        self.assertEqual(event.strategy, "momentum")
        self.assertEqual(event.trade["action"], "buy")
        required = {"action", "size", "confidence", "price", "strategy", "symbol"}
        self.assertTrue(required.issubset(set(event.trade.keys())))
        self.assertIn("max_position_size", event.risk_state)


if __name__ == "__main__":
    unittest.main()
