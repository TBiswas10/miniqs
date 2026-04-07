import unittest

from event_driven_pipeline import run_event_driven_paper_trading_session


class TestEventDrivenPipeline(unittest.TestCase):
    def test_event_driven_pipeline_runs(self) -> None:
        summary = run_event_driven_paper_trading_session(num_ticks=120, seed=11)

        self.assertIn("executed_trades", summary)
        self.assertIn("total_pnl", summary)
        self.assertIn("win_rate", summary)
        self.assertIn("max_drawdown", summary)
        self.assertIn("mean_reversion_weight", summary)
        self.assertIn("momentum_weight", summary)
        self.assertIn("volatility_breakout_weight", summary)

        self.assertGreaterEqual(summary["executed_trades"], 0.0)
        self.assertAlmostEqual(
            summary["mean_reversion_weight"]
            + summary["momentum_weight"]
            + summary["volatility_breakout_weight"],
            1.0,
            places=6,
        )


if __name__ == "__main__":
    unittest.main()
