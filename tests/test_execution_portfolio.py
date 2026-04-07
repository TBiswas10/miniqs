from datetime import datetime, timezone
import os
import sqlite3
import tempfile
import unittest

from execution import ExecutionEngine
from portfolio import Portfolio


class TestExecutionPortfolio(unittest.TestCase):
    def test_trade_sequence_pnl_and_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "portfolio_test.db")
            portfolio = Portfolio(db_path=db_path, initial_cash=10000.0, fee_rate=0.001)
            engine = ExecutionEngine(portfolio=portfolio, paper_mode=True)

            now = datetime.now(timezone.utc).isoformat()

            engine.execute_trade({"action": "buy", "size": 10.0, "price": 100.0, "timestamp": now})
            engine.execute_trade({"action": "buy", "size": 10.0, "price": 110.0, "timestamp": now})
            engine.execute_trade({"action": "sell", "size": 15.0, "price": 120.0, "timestamp": now})

            pnl = portfolio.update_pnl(market_price=118.0)
            state = portfolio.get_portfolio_state()

            self.assertAlmostEqual(state["position_size"], 5.0, places=6)
            self.assertAlmostEqual(state["avg_entry_price"], 105.0, places=6)
            self.assertAlmostEqual(state["cash"], 9696.1, places=6)
            self.assertAlmostEqual(state["fees_paid"], 3.9, places=6)
            self.assertAlmostEqual(pnl["realized_pnl"], 225.0, places=6)
            self.assertAlmostEqual(pnl["unrealized_pnl"], 65.0, places=6)
            self.assertAlmostEqual(pnl["total_pnl"], 286.1, places=6)

            conn = sqlite3.connect(db_path)
            try:
                count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
            finally:
                conn.close()
            self.assertEqual(count, 3)


if __name__ == "__main__":
    unittest.main()
