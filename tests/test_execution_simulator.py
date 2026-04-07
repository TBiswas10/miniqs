import unittest

from execution_simulator import ExecutionSimulationConfig, ExecutionSimulator, OrderState


class TestExecutionSimulator(unittest.TestCase):
    def test_full_fill_state_path(self) -> None:
        sim = ExecutionSimulator(
            config=ExecutionSimulationConfig(
                partial_fill_probability=0.0,
                reject_probability=0.0,
                cancel_remainder_probability=0.0,
            ),
            seed=7,
        )
        out = sim.simulate({"action": "buy", "size": 2.0, "price": 100.0})

        path = [step["state"] for step in out["path"]]
        self.assertEqual(path[:3], [OrderState.CREATED, OrderState.SUBMITTED, OrderState.ACKNOWLEDGED])
        self.assertEqual(path[-1], OrderState.FILLED)
        self.assertAlmostEqual(out["filled_size"], 2.0, places=6)
        self.assertAlmostEqual(out["remaining_size"], 0.0, places=6)
        self.assertGreater(out["avg_fill_price"], 100.0)

    def test_partial_cancel_state_path(self) -> None:
        sim = ExecutionSimulator(
            config=ExecutionSimulationConfig(
                partial_fill_probability=1.0,
                reject_probability=0.0,
                cancel_remainder_probability=1.0,
            ),
            seed=13,
        )
        out = sim.simulate({"action": "sell", "size": 5.0, "price": 100.0})

        path = [step["state"] for step in out["path"]]
        self.assertIn(OrderState.PARTIAL, path)
        self.assertEqual(path[-1], OrderState.CANCELED)
        self.assertGreater(out["filled_size"], 0.0)
        self.assertGreater(out["remaining_size"], 0.0)

    def test_rejected_invalid_trade(self) -> None:
        sim = ExecutionSimulator(seed=21)
        out = sim.simulate({"action": "buy", "size": -1.0, "price": 100.0})
        self.assertEqual(out["final_state"], OrderState.REJECTED)
        self.assertEqual(out["filled_size"], 0.0)


if __name__ == "__main__":
    unittest.main()
