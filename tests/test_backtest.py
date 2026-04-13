import unittest

from scripts.run_backtest import optimize_parameters, run_backtest, run_walk_forward_backtest


class TestBacktest(unittest.TestCase):
    def test_backtest_returns_pipeline_and_baselines(self) -> None:
        prices = [100.0 + (i * 0.1) + (0.5 if i % 2 == 0 else -0.5) for i in range(250)]
        result = run_backtest(prices)

        self.assertIn("pipeline", result)
        self.assertIn("baseline_naive_mean_reversion", result)
        self.assertIn("baseline_pure_momentum", result)
        self.assertIn("research_version", result)
        self.assertIn("final_iteration_state", result)

        pipeline = result["pipeline"]
        self.assertIn("total_pnl", pipeline)
        self.assertIn("win_rate", pipeline)
        self.assertIn("avg_trade_pnl", pipeline)
        self.assertIn("max_drawdown", pipeline)

        iteration = result["final_iteration_state"]
        self.assertIn("strategy_weights", iteration)
        self.assertIn("trade_size", iteration)
        self.assertIn("iterations", iteration)

        baseline = result["baseline_pure_momentum"]
        self.assertIn("sharpe_ratio", baseline)
        self.assertIn("max_drawdown", baseline)

    def test_optimize_parameters_returns_best_config(self) -> None:
        prices = [100.0 + (i * 0.05) + (0.2 if i % 3 == 0 else -0.1) for i in range(180)]
        out = optimize_parameters(prices, base_config={"confidence_threshold": 0.6})

        self.assertIn("best_config", out)
        self.assertIn("results", out)
        self.assertGreater(len(out["results"]), 0)

    def test_walk_forward_returns_out_of_sample_metrics(self) -> None:
        prices = [100.0 + (i * 0.03) + (0.15 if i % 4 == 0 else -0.08) for i in range(320)]
        wf = run_walk_forward_backtest(prices, window_size=100, step_size=60, config={"confidence_threshold": 0.6})

        self.assertIn("folds", wf)
        self.assertIn("num_folds", wf)
        self.assertGreater(wf["num_folds"], 0)

        first = wf["folds"][0]
        self.assertIn("in_sample", first)
        self.assertIn("out_of_sample", first)
        self.assertIn("train_research_version", first)
        self.assertIn("test_research_version", first)


if __name__ == "__main__":
    unittest.main()
