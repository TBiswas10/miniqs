from datetime import datetime, timezone
import unittest

from event_bus import EventBus, SignalEvent
from feature_engine import FeatureSnapshot
from strategies import StrategySignal
from strategies.mean_reversion import generate_signal as mean_reversion_signal
from strategies.momentum import generate_signal as momentum_signal
from strategy_evaluator import emit_signal_event, evaluate_signals, evaluate_signals_v2


def _features(price: float, mean: float, momentum: float) -> FeatureSnapshot:
    return FeatureSnapshot(
        symbol="TEST",
        timestamp=datetime.now(timezone.utc),
        price=price,
        rolling_mean=mean,
        rolling_volatility=0.02,
        momentum=momentum,
        realized_vol_short=0.02,
        realized_vol_long=0.02,
        spread_bps=5.0,
        book_imbalance=0.0,
        rel_volume=1.0,
        volume_zscore=0.0,
        trend_slope_short=0.0,
        trend_slope_long=0.0,
        distance_to_ma50=0.0,
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


class TestStrategyEvaluatorV2(unittest.TestCase):
    def test_ensemble_voting_prefers_aggregate_side(self) -> None:
        signals = [
            StrategySignal("momentum", "buy", 0.56, "x"),
            StrategySignal("mean_reversion", "buy", 0.55, "x"),
            StrategySignal("volatility_breakout", "sell", 0.8, "x"),
        ]

        chosen = evaluate_signals_v2(signals, confidence_threshold=0.6)

        self.assertIsNotNone(chosen)
        assert chosen is not None
        self.assertEqual(chosen.action, "buy")

    def test_per_strategy_normalization_reduces_momentum_dominance(self) -> None:
        signals = [
            StrategySignal("momentum", "buy", 0.95, "x"),
            StrategySignal("mean_reversion", "buy", 0.7, "x"),
            StrategySignal("volatility_breakout", "buy", 0.65, "x"),
        ]

        chosen = evaluate_signals_v2(
            signals,
            confidence_threshold=0.6,
            strategy_normalization={"momentum": 0.45, "mean_reversion": 1.0, "volatility_breakout": 1.0},
            dominance_cap=0.6,
        )

        self.assertIsNotNone(chosen)
        assert chosen is not None
        self.assertNotEqual(chosen.strategy, "momentum")

    def test_strict_forward_profile_relaxes_threshold(self) -> None:
        signals = [
            StrategySignal("momentum", "buy", 0.5, "x"),
            StrategySignal("mean_reversion", "hold", 0.2, "x"),
        ]

        chosen_default = evaluate_signals_v2(signals, confidence_threshold=0.6, profile="default")
        chosen_strict = evaluate_signals_v2(signals, confidence_threshold=0.6, profile="strict_forward")

        self.assertIsNone(chosen_default)
        self.assertIsNotNone(chosen_strict)

    def test_telemetry_keys_and_winning_side_consistency(self) -> None:
        signals = [
            StrategySignal("momentum", "buy", 0.72, "x"),
            StrategySignal("mean_reversion", "sell", 0.21, "x"),
            StrategySignal("volatility_breakout", "buy", 0.55, "x"),
        ]

        chosen, telemetry = evaluate_signals_v2(
            signals,
            confidence_threshold=0.6,
            return_telemetry=True,
        )

        self.assertIsNotNone(chosen)
        assert chosen is not None
        self.assertIn("buy_score", telemetry)
        self.assertIn("sell_score", telemetry)
        self.assertIn("normalized_contributions", telemetry)
        self.assertIn("applied_threshold", telemetry)
        self.assertIn("applied_profile", telemetry)
        if chosen.action == "buy":
            self.assertGreaterEqual(float(telemetry["buy_score"]), float(telemetry["sell_score"]))
        else:
            self.assertGreater(float(telemetry["sell_score"]), float(telemetry["buy_score"]))


if __name__ == "__main__":
    unittest.main()
