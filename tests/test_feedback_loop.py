import unittest

from main import FeedbackLoop, run_feedback_simulation


class TestFeedbackLoop(unittest.TestCase):
    def test_simulation_adjusts_weights_gradually_over_100_ticks(self) -> None:
        final_weights = run_feedback_simulation(num_ticks=100)

        self.assertIn("mean_reversion", final_weights)
        self.assertIn("momentum", final_weights)

        total = final_weights["mean_reversion"] + final_weights["momentum"]
        self.assertAlmostEqual(total, 1.0, places=6)

        # Momentum should gain some weight in the synthetic scenario.
        self.assertGreater(final_weights["momentum"], 0.5)
        self.assertLess(final_weights["mean_reversion"], 0.5)

    def test_single_step_change_is_small(self) -> None:
        loop = FeedbackLoop(learning_rate=0.02, max_delta_per_step=0.01)
        before = dict(loop.strategy_weights)

        metrics = {
            "mean_reversion": {"win_rate": 0.0, "avg_trade_pnl": -10.0, "max_drawdown": 10.0},
            "momentum": {"win_rate": 1.0, "avg_trade_pnl": 10.0, "max_drawdown": 0.0},
        }
        after = loop.update(metrics)

        self.assertLessEqual(abs(after["mean_reversion"] - before["mean_reversion"]), 0.02)
        self.assertLessEqual(abs(after["momentum"] - before["momentum"]), 0.02)


if __name__ == "__main__":
    unittest.main()
