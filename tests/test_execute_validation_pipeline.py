import unittest

from scripts.execute_validation_pipeline import (
    AcceptanceThresholds,
    FailFastConfig,
    ValidationFailure,
    _check_fail_fast,
    _domination_ratio,
    _evaluate_acceptance,
)


class TestExecuteValidationPipeline(unittest.TestCase):
    def test_domination_ratio(self) -> None:
        self.assertAlmostEqual(_domination_ratio({"a": 8, "b": 2}), 0.8)
        self.assertEqual(_domination_ratio({}), 0.0)

    def test_fail_fast_for_domination(self) -> None:
        cfg = FailFastConfig(max_strategy_domination=0.7)
        with self.assertRaises(ValidationFailure):
            _check_fail_fast("backtest", {"mean_reversion": 8, "momentum": 2}, trade_count=10, cfg=cfg)

    def test_acceptance_fails_on_trade_count(self) -> None:
        acceptance = _evaluate_acceptance(
            {
                "pnl": 10.0,
                "drawdown": 0.05,
                "win_rate": 0.5,
                "trade_count": 1,
                "strategy_selection_counts": {"mean_reversion": 1},
                "risk_block_rate": 0.0,
            },
            thresholds=AcceptanceThresholds(min_trade_count=3),
        )
        self.assertFalse(acceptance["passed"])
        self.assertTrue(any("trade_count" in item for item in acceptance["failures"]))


if __name__ == "__main__":
    unittest.main()
