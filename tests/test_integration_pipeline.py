import unittest

from main import run_paper_trading_session


class TestIntegrationPipeline(unittest.TestCase):
    def test_full_paper_pipeline_runs(self) -> None:
        summary = run_paper_trading_session(num_ticks=180, seed=21)

        self.assertIn("executed_trades", summary)
        self.assertIn("total_pnl", summary)
        self.assertIn("win_rate", summary)
        self.assertIn("max_drawdown", summary)
        self.assertIn("mean_reversion_weight", summary)
        self.assertIn("momentum_weight", summary)

        self.assertGreaterEqual(summary["executed_trades"], 0.0)
        self.assertGreaterEqual(summary["mean_reversion_weight"], 0.0)
        self.assertGreaterEqual(summary["momentum_weight"], 0.0)
        self.assertAlmostEqual(
            summary["mean_reversion_weight"] + summary["momentum_weight"],
            1.0,
            places=6,
        )


if __name__ == "__main__":
    unittest.main()
