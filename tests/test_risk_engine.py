from datetime import datetime, timedelta, timezone
import unittest

from risk_manager import RiskConfig, RiskEngine


class TestRiskEngine(unittest.TestCase):
    def test_vol_scaled_sizing_changes_with_volatility(self) -> None:
        engine = RiskEngine(initial_equity=100000.0, config=RiskConfig(base_trade_size=1.0, vol_target=0.01))
        now = datetime.now(timezone.utc)

        trade = {
            "action": "buy",
            "size": 1.0,
            "confidence": 0.8,
            "price": 100.0,
            "timestamp": now.isoformat(),
            "strategy": "momentum",
        }
        low_vol_state = {
            "current_position": 0.0,
            "last_trade_timestamp": now - timedelta(seconds=120),
            "session_loss": 0.0,
            "max_position_size": 5.0,
            "cooldown_seconds": 1,
            "max_loss_per_session": 500.0,
            "equity": 100000.0,
            "total_pnl": 0.0,
            "market_volatility": 0.004,
            "strategy_weight": 1.0,
        }
        high_vol_state = dict(low_vol_state)
        high_vol_state["market_volatility"] = 0.03

        allow_low, _, adjusted_low, _ = engine.assess_trade(trade, low_vol_state)
        allow_high, _, adjusted_high, _ = engine.assess_trade(trade, high_vol_state)

        self.assertTrue(allow_low)
        self.assertTrue(allow_high)
        self.assertGreater(float(adjusted_low["size"]), float(adjusted_high["size"]))

    def test_portfolio_drawdown_kill_switch(self) -> None:
        engine = RiskEngine(
            initial_equity=100000.0,
            config=RiskConfig(portfolio_drawdown_limit=0.1),
        )
        now = datetime.now(timezone.utc)
        trade = {
            "action": "buy",
            "size": 1.0,
            "confidence": 0.7,
            "price": 100.0,
            "timestamp": now.isoformat(),
            "strategy": "mean_reversion",
        }
        state = {
            "current_position": 0.0,
            "last_trade_timestamp": now - timedelta(seconds=120),
            "session_loss": 0.0,
            "max_position_size": 5.0,
            "cooldown_seconds": 1,
            "max_loss_per_session": 500.0,
            "equity": 85000.0,
            "total_pnl": -15000.0,
            "market_volatility": 0.01,
            "strategy_weight": 1.0,
        }

        allow, reason, _, flags = engine.assess_trade(trade, state)
        self.assertFalse(allow)
        self.assertIn("drawdown kill switch", reason)
        self.assertTrue(flags["global_kill_switch"])

    def test_per_strategy_kill_switch(self) -> None:
        engine = RiskEngine(
            initial_equity=100000.0,
            config=RiskConfig(strategy_kill_loss=50.0),
        )
        strategy = "momentum"

        engine.record_execution(strategy=strategy, realized_pnl_trade=-60.0, equity=99940.0)
        self.assertTrue(engine.strategy_kill_switch.get(strategy, False))

    def test_combined_gate_blocks_drawdown_limit(self) -> None:
        engine = RiskEngine(
            initial_equity=100000.0,
            config=RiskConfig(portfolio_drawdown_limit=0.2),
        )
        now = datetime.now(timezone.utc)
        trade = {
            "action": "buy",
            "size": 1.0,
            "confidence": 0.9,
            "price": 100.0,
            "timestamp": now.isoformat(),
            "strategy": "momentum",
        }
        state = {
            "current_position": 0.0,
            "open_positions_count": 0,
            "max_concurrent_positions": 3,
            "last_trade_timestamp": now - timedelta(seconds=120),
            "session_loss": 0.0,
            "max_position_size": 5.0,
            "cooldown_seconds": 1,
            "daily_loss_limit": 1000.0,
            "equity": 100000.0,
            "total_pnl": 0.0,
            "portfolio_drawdown": 0.25,
            "portfolio_drawdown_limit": 0.2,
            "market_volatility": 0.01,
            "strategy_weight": 1.0,
        }

        allow, reason, _, _ = engine.assess_trade(trade, state)
        self.assertFalse(allow)
        self.assertIn("drawdown", reason)


if __name__ == "__main__":
    unittest.main()
