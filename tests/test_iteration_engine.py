import tempfile
import unittest

from src.miniqs.engine.iteration_engine import AutoTuner, ExperimentLogger, RegimeDetector


class TestIterationEngine(unittest.TestCase):
    def test_regime_detector_classifies_trend(self) -> None:
        detector = RegimeDetector(window=20)
        prices = [100.0 + i * 0.2 for i in range(30)]
        regime = detector.detect(prices)

        self.assertIn(regime.regime, {"trending_up", "volatile", "range"})
        self.assertGreaterEqual(regime.realized_volatility, 0.0)

    def test_auto_tuner_recommends_weights_and_risk(self) -> None:
        tuner = AutoTuner()
        rec = tuner.recommend(
            current_weights={"mean_reversion": 0.5, "momentum": 0.5, "volatility_breakout": 0.0},
            risk_params={"base_trade_size": 1.0, "max_position_size": 5.0, "cooldown_seconds": 5},
            market_conditions=RegimeDetector().detect([100.0 + i * 0.1 for i in range(50)]),
            outcomes={"equity_delta": 150.0, "drawdown": 0.04, "total_pnl": 200.0},
            strategy_metrics={
                "momentum": {"hit_rate": 0.62, "avg_trade_pnl": 1.0, "sharpe_ratio": 1.1, "max_drawdown": 0.03},
                "mean_reversion": {"hit_rate": 0.47, "avg_trade_pnl": -0.2, "sharpe_ratio": -0.1, "max_drawdown": 0.05},
                "volatility_breakout": {"hit_rate": 0.55, "avg_trade_pnl": 0.4, "sharpe_ratio": 0.5, "max_drawdown": 0.04},
            },
        )

        self.assertIn("strategy_weights", rec)
        self.assertIn("risk_params", rec)
        self.assertAlmostEqual(sum(rec["strategy_weights"].values()), 1.0, places=5)
        self.assertGreater(rec["risk_params"]["base_trade_size"], 0.0)

    def test_experiment_logger_persists_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            logger = ExperimentLogger(db_path=f"{tmp}/exp.db")
            logger.log_experiment(
                run_id="unit_run",
                iteration=1,
                parameter_set={"a": 1},
                market_conditions={"regime": "range"},
                outcomes={"total_pnl": 10.0},
                recommendations={"x": 1},
            )

            import sqlite3

            conn = sqlite3.connect(f"{tmp}/exp.db")
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM experiments")
                row_count = int(cur.fetchone()[0])
            finally:
                conn.close()

            self.assertEqual(row_count, 1)


if __name__ == "__main__":
    unittest.main()
