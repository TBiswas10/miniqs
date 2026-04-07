import unittest

from backtest import optimize_parameters, run_backtest


class TestBacktest(unittest.TestCase):
    def test_backtest_returns_pipeline_and_baselines(self) -> None:
        prices = [100.0 + (i * 0.1) + (0.5 if i % 2 == 0 else -0.5) for i in range(250)]
        result = run_backtest(prices)

        self.assertIn("pipeline", result)
        self.assertIn("baseline_naive_mean_reversion", result)
        self.assertIn("baseline_pure_momentum", result)

        pipeline = result["pipeline"]
        self.assertIn("total_pnl", pipeline)
        self.assertIn("win_rate", pipeline)
        self.assertIn("avg_trade_pnl", pipeline)
        self.assertIn("max_drawdown", pipeline)

        baseline = result["baseline_pure_momentum"]
        self.assertIn("sharpe_ratio", baseline)
        self.assertIn("max_drawdown", baseline)

    def test_optimize_parameters_returns_best_config(self) -> None:
        prices = [100.0 + (i * 0.05) + (0.2 if i % 3 == 0 else -0.1) for i in range(180)]
        out = optimize_parameters(prices, base_config={"confidence_threshold": 0.6})

        self.assertIn("best_config", out)
        self.assertIn("results", out)
        self.assertGreater(len(out["results"]), 0)


if __name__ == "__main__":
    unittest.main()
