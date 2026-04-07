"""Test suite for stress testing module."""

import sys
from pathlib import Path
import unittest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from stress_testing import (
	generate_spike_scenario,
	generate_high_volatility_scenario,
	generate_downtrend_scenario,
	generate_low_liquidity_scenario,
	run_stress_test,
	run_stress_suite,
)


class TestStressScenarioGeneration(unittest.TestCase):
	"""Test synthetic price scenario generators."""

	def test_spike_scenario_generates_prices(self):
		"""Verify spike scenario produces valid price series."""
		prices = generate_spike_scenario(base_price=100.0, spike_percent=0.05, num_ticks=100)
		self.assertEqual(len(prices), 100)
		self.assertTrue(all(p > 0 for p in prices))
		# Prices should contain a significant jump
		max_jump = max(abs(prices[i] - prices[i - 1]) for i in range(1, len(prices)))
		self.assertGreater(max_jump, 0.1)  # Spike should be visible

	def test_high_volatility_scenario_generates_prices(self):
		"""Verify high volatility scenario produces prices with elevated variance."""
		prices = generate_high_volatility_scenario(base_price=100.0, volatility_factor=2.0, num_ticks=100)
		self.assertEqual(len(prices), 100)
		self.assertTrue(all(p > 0 for p in prices))
		# Calculate volatility
		returns = [abs(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]
		avg_volatility = sum(returns) / len(returns)
		self.assertGreater(avg_volatility, 0.003)  # Should be elevated

	def test_downtrend_scenario_generates_declining_prices(self):
		"""Verify downtrend scenario produces declining prices overall."""
		prices = generate_downtrend_scenario(base_price=100.0, decline_percent=0.20, num_ticks=100)
		self.assertEqual(len(prices), 100)
		self.assertTrue(all(p > 0 for p in prices))
		# Should end lower than start (with noise it might not be strict monotonic)
		self.assertLess(prices[-1], prices[0])

	def test_low_liquidity_scenario_generates_prices(self):
		"""Verify low liquidity scenario produces prices with wide spreads."""
		prices = generate_low_liquidity_scenario(base_price=100.0, spread_percent=0.02, num_ticks=100)
		self.assertEqual(len(prices), 100)
		self.assertTrue(all(p > 0 for p in prices))
		# Should have some large jumps due to spread simulation
		jumps = [abs(prices[i] - prices[i - 1]) for i in range(1, len(prices))]
		max_jump = max(jumps)
		self.assertGreater(max_jump, 0.5)  # Should see meaningful gaps


class TestStressTestExecution(unittest.TestCase):
	"""Test stress test pipeline execution."""

	def test_stress_test_runs_without_crash(self):
		"""Verify stress test executes without exceptions."""
		prices = generate_spike_scenario(base_price=100.0, spike_percent=0.05, num_ticks=50)
		result = run_stress_test("test_spike", prices)
		self.assertIn("system_stable", result)
		self.assertTrue(result["system_stable"])

	def test_stress_test_tracks_risk_blocks(self):
		"""Verify stress test counts risk manager blocks."""
		prices = generate_downtrend_scenario(base_price=100.0, decline_percent=0.20, num_ticks=100)
		config = {
			"initial_cash": 100000.0,
			"max_loss_per_session": 100.0,  # Very tight loss limit
			"cooldown_seconds": 10,  # Tight cooldown
			"max_position_size": 1.0,  # Very small position
		}
		result = run_stress_test("tight_risk", prices, config)
		self.assertIsInstance(result["risk_blocks"], int)
		self.assertGreaterEqual(result["risk_blocks"], 0)

	def test_stress_test_returns_metrics(self):
		"""Verify stress test computes performance metrics."""
		prices = generate_high_volatility_scenario(base_price=100.0, volatility_factor=2.0, num_ticks=80)
		result = run_stress_test("volatility_test", prices)
		if result.get("metrics"):
			metrics = result["metrics"]
			self.assertIn("total_pnl", metrics)
			self.assertIn("win_rate", metrics)
			self.assertIn("max_drawdown", metrics)


class TestStressSuite(unittest.TestCase):
	"""Test full stress suite."""

	def test_stress_suite_runs_all_scenarios(self):
		"""Verify stress suite executes all 8 scenarios."""
		results = run_stress_suite()
		expected_scenarios = {
			"spike_5pct",
			"spike_down_10pct",
			"high_volatility_2x",
			"high_volatility_3x",
			"downtrend_20pct",
			"downtrend_40pct",
			"low_liquidity_2pct",
			"low_liquidity_5pct",
		}
		self.assertEqual(set(results.keys()), expected_scenarios)

	def test_stress_suite_all_scenarios_stable(self):
		"""Verify all scenarios complete without crashes."""
		results = run_stress_suite()
		for scenario_name, result in results.items():
			with self.subTest(scenario=scenario_name):
				self.assertTrue(
					result["system_stable"],
					f"Scenario {scenario_name} crashed: {result.get('error', 'unknown error')}",
				)


if __name__ == "__main__":
	unittest.main()
