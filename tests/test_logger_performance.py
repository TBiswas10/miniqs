import os
import sqlite3
import tempfile
import unittest

from logger import QuantLogger
from performance import PerformanceTracker


class TestLoggerPerformance(unittest.TestCase):
    def test_logger_and_performance_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "logs_test.db")
            logger = QuantLogger(db_path=db_path)
            perf = PerformanceTracker(initial_equity=100000.0)

            logger.log_signal("momentum", "buy", 0.8, "positive momentum")
            logger.log_trade(
                {
                    "action": "buy",
                    "size": 1.0,
                    "price": 100.0,
                    "fee": 0.1,
                    "realized_pnl_trade": 5.0,
                },
                strategy="momentum",
            )
            logger.log_portfolio_snapshot({"cash": 99900.0, "position_size": 1.0, "equity": 100005.0, "total_pnl": 5.0})

            perf.record_trade(5.0)
            perf.record_trade(-2.0)
            perf.record_equity(100000.0)
            perf.record_equity(100010.0)
            perf.record_equity(100008.0)
            metrics = perf.compute_metrics(latest_total_pnl=3.0)
            logger.log_performance_metrics(metrics)

            conn = sqlite3.connect(db_path)
            try:
                signals_count = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
                trades_count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
                snapshots_count = conn.execute("SELECT COUNT(*) FROM portfolio_snapshots").fetchone()[0]
                metrics_count = conn.execute("SELECT COUNT(*) FROM performance_metrics").fetchone()[0]
                events_count = conn.execute("SELECT COUNT(*) FROM event_log").fetchone()[0]
            finally:
                conn.close()

            self.assertEqual(signals_count, 1)
            self.assertEqual(trades_count, 1)
            self.assertEqual(snapshots_count, 1)
            self.assertEqual(metrics_count, 1)
            self.assertGreaterEqual(events_count, 4)
            self.assertIn("sharpe_ratio", metrics)


if __name__ == "__main__":
    unittest.main()
