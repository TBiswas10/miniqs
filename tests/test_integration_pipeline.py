import unittest

from scripts.run_main import run_paper_trading_session


class TestIntegrationPipeline(unittest.TestCase):
    def test_full_paper_pipeline_runs(self) -> None:
        summary = run_paper_trading_session(num_ticks=180, seed=21)

        self.assertIn("executed_trades", summary)
        self.assertIn("total_pnl", summary)
        self.assertIn("win_rate", summary)
        self.assertIn("max_drawdown", summary)
        self.assertIn("strategy_weights", summary)

        self.assertGreaterEqual(summary["executed_trades"], 0.0)
        for value in summary["strategy_weights"].values():
            self.assertGreaterEqual(value, 0.0)
        self.assertAlmostEqual(sum(summary["strategy_weights"].values()), 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
