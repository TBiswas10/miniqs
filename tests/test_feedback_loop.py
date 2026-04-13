import unittest

from scripts.run_main import FeedbackLoop, run_feedback_simulation


class TestFeedbackLoop(unittest.TestCase):
    def test_simulation_adjusts_weights_gradually_over_100_ticks(self) -> None:
        final_weights = run_feedback_simulation(num_ticks=100)

        self.assertIn("mean_reversion", final_weights)
        self.assertIn("momentum", final_weights)
        self.assertIn("volatility_breakout", final_weights)

        total = (
            final_weights["mean_reversion"]
            + final_weights["momentum"]
            + final_weights["volatility_breakout"]
        )
        self.assertAlmostEqual(total, 1.0, places=6)

        # Momentum should gain some weight in the synthetic scenario.
        self.assertGreater(final_weights["momentum"], final_weights["mean_reversion"])

    def test_single_step_change_is_small(self) -> None:
        loop = FeedbackLoop(learning_rate=0.02, max_delta_per_step=0.01)
        before = dict(loop.strategy_weights)

        metrics = {
            "mean_reversion": {
                "hit_rate": 0.0,
                "avg_trade_pnl": -10.0,
                "max_drawdown": 10.0,
                "sharpe_ratio": -0.5,
                "trade_count": 1.0,
            },
            "momentum": {
                "hit_rate": 1.0,
                "avg_trade_pnl": 10.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.8,
                "trade_count": 1.0,
            },
            "volatility_breakout": {
                "hit_rate": 0.5,
                "avg_trade_pnl": 0.0,
                "max_drawdown": 0.0,
                "sharpe_ratio": 0.0,
                "trade_count": 1.0,
            },
        }
        after = loop.update(metrics)

        self.assertLessEqual(abs(after["mean_reversion"] - before["mean_reversion"]), 0.02)
        self.assertLessEqual(abs(after["momentum"] - before["momentum"]), 0.02)

    def test_auto_disable_underperforming_strategy(self) -> None:
        loop = FeedbackLoop(
            strategy_weights={"mean_reversion": 0.5, "momentum": 0.4, "volatility_breakout": 0.1},
            disable_min_trades=5.0,
        )
        metrics = {
            "mean_reversion": {
                "hit_rate": 0.2,
                "avg_trade_pnl": -5.0,
                "max_drawdown": 0.4,
                "sharpe_ratio": -0.4,
                "trade_count": 12.0,
            },
            "momentum": {
                "hit_rate": 0.65,
                "avg_trade_pnl": 2.0,
                "max_drawdown": 0.1,
                "sharpe_ratio": 0.6,
                "trade_count": 12.0,
            },
            "volatility_breakout": {
                "hit_rate": 0.6,
                "avg_trade_pnl": 1.0,
                "max_drawdown": 0.1,
                "sharpe_ratio": 0.5,
                "trade_count": 12.0,
            },
        }
        loop.update(metrics)
        self.assertFalse(loop.is_enabled("mean_reversion"))
        self.assertEqual(loop.strategy_weights["mean_reversion"], 0.0)


if __name__ == "__main__":
    unittest.main()
