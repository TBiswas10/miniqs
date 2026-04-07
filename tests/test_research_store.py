import tempfile
import unittest

from research_store import ResearchDatasetStore


class TestResearchStore(unittest.TestCase):
    def test_versioned_store_and_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = ResearchDatasetStore(dataset_name="unit_ds", root_dir=tmp)
            version = store.create_version({"purpose": "unit_test"})

            self.assertTrue(version)

            store.log_tick("2026-01-01T00:00:00+00:00", "SIM", 100.0, 1.0)
            store.log_ohlc("2026-01-01T00:00:00+00:00", "SIM", 99.5, 100.5, 99.0, 100.0, 1.0)
            store.log_feature("2026-01-01T00:00:00+00:00", "SIM", 100.0, 100.0, 0.01, 0.002)
            store.log_signal("2026-01-01T00:00:00+00:00", "momentum", "buy", 0.8, "test")
            store.log_fill(
                "2026-01-01T00:00:00+00:00",
                "momentum",
                {
                    "action": "buy",
                    "requested_size": 1.0,
                    "filled_size": 1.0,
                    "remaining_size": 0.0,
                    "applied_price": 100.1,
                    "fee": 0.1,
                    "order_state": "filled",
                    "order_state_path": ["created", "submitted", "acknowledged", "filled"],
                },
            )
            store.log_pnl("2026-01-01T00:00:00+00:00", 100000.0, 10.0, 5.0, 5.0)
            store.log_strategy_metric(
                "2026-01-01T00:00:00+00:00",
                "momentum",
                {
                    "hit_rate": 0.6,
                    "sharpe_ratio": 1.2,
                    "max_drawdown": 0.05,
                    "avg_trade_pnl": 1.0,
                    "trade_count": 10,
                },
            )

            ticks = list(store.replay_ticks())
            self.assertEqual(len(ticks), 1)
            self.assertEqual(ticks[0]["symbol"], "SIM")


if __name__ == "__main__":
    unittest.main()
