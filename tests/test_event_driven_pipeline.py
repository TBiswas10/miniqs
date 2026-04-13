import unittest

from scripts.run_event_pipeline import run_event_driven_paper_trading_session


class TestEventDrivenPipeline(unittest.TestCase):
    def test_event_driven_pipeline_runs(self) -> None:
        summary = run_event_driven_paper_trading_session(num_ticks=120, seed=11)

        self.assertIn("executed_trades", summary)
        self.assertIn("total_pnl", summary)
        self.assertIn("win_rate", summary)
        self.assertIn("max_drawdown", summary)
        self.assertIn("strategy_weights", summary)

        self.assertGreaterEqual(summary["executed_trades"], 0.0)
        self.assertAlmostEqual(sum(summary["strategy_weights"].values()), 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
