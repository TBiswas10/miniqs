"""Stress testing module for realistic market shocks and edge cases.

Tests the system against:
- Price spikes / gaps
- High volatility regimes
- Prolonged downtrends
- Low liquidity scenarios
- Rapid position liquidation

Input: historical or synthetic price series with stress scenarios
Output: system response metrics (trades blocked, losses incurred, risk enforcement success)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple
import tempfile

from data_feed import Tick
from execution import ExecutionEngine
from feature_engine import FeatureEngine
from performance import PerformanceTracker
from portfolio import Portfolio
from risk_manager import check_risk
from strategies.mean_reversion import generate_signal as mean_reversion_signal
from strategies.momentum import generate_signal as momentum_signal
from strategy_evaluator import evaluate_signals


def generate_spike_scenario(base_price: float, spike_percent: float, num_ticks: int = 100) -> List[float]:
	"""Generate synthetic prices with a sudden spike / gap.

	Simulates a market shock (e.g., news-driven gap up/down or exchange halt recovery).

	Args:
		base_price: starting price
		spike_percent: spike magnitude as % (e.g., 0.05 = 5% gap)
		num_ticks: total ticks in series

	Returns:
		list of prices with sharp spike at midpoint
	"""
	prices = []
	for i in range(num_ticks):
		if i < num_ticks // 2:
			# Baseline: normal walk
			p = base_price + (i * 0.001)
		else:
			# Spike: sudden jump then recovery
			spike_offset = base_price * spike_percent
			p = base_price + (num_ticks // 2) * 0.001 + spike_offset - (i - num_ticks // 2) * 0.005
		prices.append(max(1.0, p))
	return prices


def generate_high_volatility_scenario(base_price: float, volatility_factor: float = 2.0, num_ticks: int = 100) -> List[float]:
	"""Generate synthetic prices with elevated volatility (2-3x normal).

	Simulates crypto crashes, flash crashes, or extreme IV regimes.

	Args:
		base_price: starting price
		volatility_factor: multiplier on normal price swings (e.g., 2.0 = 2x volatility)
		num_ticks: total ticks in series

	Returns:
		list of prices with higher standard deviation
	"""
	prices = [base_price]
	import random
	random.seed(42)
	for _ in range(num_ticks - 1):
		change = random.gauss(0, 0.005 * volatility_factor)
		new_p = prices[-1] * (1.0 + change)
		prices.append(max(1.0, new_p))
	return prices


def generate_downtrend_scenario(base_price: float, decline_percent: float, num_ticks: int = 100) -> List[float]:
	"""Generate synthetic prices in a prolonged downtrend.

	Simulates bear markets, strategy underperformance, max loss triggers.

	Args:
		base_price: starting price
		decline_percent: total decline as % over series (e.g., 0.20 = 20% loss)
		num_ticks: total ticks in series

	Returns:
		list of prices declining monotonically with noise
	"""
	prices = []
	import random
	random.seed(42)
	for i in range(num_ticks):
		# Linear decline + noise
		progress = i / max(1, num_ticks - 1)
		decline_offset = base_price * decline_percent * progress
		noise = random.gauss(0, base_price * 0.002)
		p = base_price - decline_offset + noise
		prices.append(max(1.0, p))
	return prices


def generate_low_liquidity_scenario(base_price: float, spread_percent: float = 0.02, num_ticks: int = 100) -> List[float]:
	"""Generate synthetic prices with large bid-ask spread effects.

	Simulates illiquid assets, trading halts, or extreme market stress.

	Args:
		base_price: starting price
		spread_percent: simulated spread % (e.g., 0.02 = 2% wide spread)
		num_ticks: total ticks in series

	Returns:
		list of prices with artificially high jump variance
	"""
	prices = []
	import random
	random.seed(42)
	for i in range(num_ticks):
		# Normal movement + large random jumps (simulating liquidity shocks)
		normal_move = base_price * (1.0 + random.gauss(0, 0.002))
		if i % 7 == 0:  # Every 7 ticks, large spread effect
			liquidity_shock = base_price * (spread_percent / 2.0) * random.choice([-1.0, 1.0])
		else:
			liquidity_shock = 0.0
		p = normal_move + liquidity_shock
		prices.append(max(1.0, p))
	return prices


def run_stress_test(
	scenario_name: str,
	prices: List[float],
	config: Dict[str, float] | None = None,
) -> Dict[str, object]:
	"""Run stress test on synthetic or historical prices.

	Args:
		scenario_name: name of the stress scenario (e.g., "spike", "downtrend")
		prices: price series to test
		config: optional strategy/risk config

	Returns:
		dict with {
			"scenario": scenario_name,
			"metrics": performance metrics,
			"risk_blocks": count of trades blocked by risk manager,
			"max_drawdown": peak-to-trough decline,
			"system_stable": bool (did system survive without crashes)
		}
	"""
	cfg = config or {}
	risk_blocks = 0

	try:
		with tempfile.TemporaryDirectory() as tmp:
			db_path = str(Path(tmp) / f"stress_{scenario_name}.db")
			portfolio = Portfolio(db_path=db_path, initial_cash=float(cfg.get("initial_cash", 100000.0)))
			execution = ExecutionEngine(portfolio=portfolio, paper_mode=True, debug=False)
			features = FeatureEngine(
				ma_window=int(cfg.get("ma_window", 20)),
				long_ma_window=int(cfg.get("long_ma_window", 50)),
				vol_window=int(cfg.get("vol_window", 20)),
				momentum_window=int(cfg.get("momentum_window", 10)),
				debug=False,
			)
			perf = PerformanceTracker(initial_equity=float(cfg.get("initial_cash", 100000.0)))

			last_trade_ts = None
			for i, p in enumerate(prices):
				ts = datetime.now(timezone.utc) + timedelta(seconds=i)
				tick = Tick(symbol="STRESS", price=float(p), timestamp=ts, volume=1.0)
				snap = features.update(tick)
				portfolio.update_pnl(float(p))
				state = portfolio.get_portfolio_state()
				perf.record_equity(float(state["equity"]))

				if snap is None:
					continue

				mr = mean_reversion_signal(snap, entry_threshold=float(cfg.get("mr_threshold", 0.003)))
				mo = momentum_signal(snap, momentum_threshold=float(cfg.get("mom_threshold", 0.002)))
				chosen = evaluate_signals([mr, mo], confidence_threshold=float(cfg.get("confidence_threshold", 0.6)))
				if chosen is None:
					continue

				# Handle long-only constraint
				if chosen.action == "sell" and float(state["position_size"]) <= 0:
					continue

				trade = {
					"action": chosen.action,
					"size": float(cfg.get("trade_size", 1.0)),
					"confidence": chosen.confidence,
					"price": float(p),
					"timestamp": ts.isoformat(),
					"strategy": chosen.strategy,
				}
				risk_state = {
					"current_position": float(state["position_size"]),
					"last_trade_timestamp": last_trade_ts,
					"session_loss": max(0.0, -float(state["total_pnl"])),
					"max_position_size": float(cfg.get("max_position_size", 5.0)),
					"cooldown_seconds": int(cfg.get("cooldown_seconds", 5)),
					"max_loss_per_session": float(cfg.get("max_loss_per_session", 500.0)),
				}
				allow, reason = check_risk(trade, risk_state)
				if not allow:
					risk_blocks += 1
					continue

				result = execution.execute_trade(trade)
				last_trade_ts = ts.isoformat()
				perf.record_trade(float(result["realized_pnl_trade"]))
				perf.record_strategy_trade(chosen.strategy, float(result["realized_pnl_trade"]))

			final_state = portfolio.get_portfolio_state()
			metrics = perf.compute_metrics(latest_total_pnl=float(final_state["total_pnl"]))

		return {
			"scenario": scenario_name,
			"metrics": metrics,
			"risk_blocks": risk_blocks,
			"system_stable": True,
		}

	except Exception as e:
		return {
			"scenario": scenario_name,
			"metrics": {},
			"risk_blocks": risk_blocks,
			"system_stable": False,
			"error": str(e),
		}


def run_stress_suite(config: Dict[str, float] | None = None) -> Dict[str, Dict[str, object]]:
	"""Run full stress test suite with all scenarios.

	Args:
		config: optional strategy/risk config

	Returns:
		dict mapping scenario names to stress test results
	"""
	cfg = config or {
		"initial_cash": 100000.0,
		"ma_window": 20,
		"long_ma_window": 50,
		"vol_window": 20,
		"momentum_window": 10,
		"mr_threshold": 0.003,
		"mom_threshold": 0.002,
		"confidence_threshold": 0.6,
		"trade_size": 1.0,
		"max_position_size": 5.0,
		"cooldown_seconds": 5,
		"max_loss_per_session": 500.0,
	}

	results: Dict[str, Dict[str, object]] = {}

	# Scenario 1: Price spike (5% gap up)
	spike_prices = generate_spike_scenario(base_price=100.0, spike_percent=0.05, num_ticks=100)
	results["spike_5pct"] = run_stress_test("spike_5pct", spike_prices, cfg)

	# Scenario 2: Extreme spike (10% gap down)
	spike_down = generate_spike_scenario(base_price=100.0, spike_percent=-0.10, num_ticks=100)
	results["spike_down_10pct"] = run_stress_test("spike_down_10pct", spike_down, cfg)

	# Scenario 3: High volatility (2x normal)
	hvol_prices = generate_high_volatility_scenario(base_price=100.0, volatility_factor=2.0, num_ticks=100)
	results["high_volatility_2x"] = run_stress_test("high_volatility_2x", hvol_prices, cfg)

	# Scenario 4: Extreme volatility (3x normal)
	hvol_extreme = generate_high_volatility_scenario(base_price=100.0, volatility_factor=3.0, num_ticks=100)
	results["high_volatility_3x"] = run_stress_test("high_volatility_3x", hvol_extreme, cfg)

	# Scenario 5: Downtrend (20% loss)
	downtrend = generate_downtrend_scenario(base_price=100.0, decline_percent=0.20, num_ticks=100)
	results["downtrend_20pct"] = run_stress_test("downtrend_20pct", downtrend, cfg)

	# Scenario 6: Severe downtrend (40% loss)
	downtrend_severe = generate_downtrend_scenario(base_price=100.0, decline_percent=0.40, num_ticks=100)
	results["downtrend_40pct"] = run_stress_test("downtrend_40pct", downtrend_severe, cfg)

	# Scenario 7: Low liquidity (2% spread)
	low_liq = generate_low_liquidity_scenario(base_price=100.0, spread_percent=0.02, num_ticks=100)
	results["low_liquidity_2pct"] = run_stress_test("low_liquidity_2pct", low_liq, cfg)

	# Scenario 8: Extreme low liquidity (5% spread)
	low_liq_extreme = generate_low_liquidity_scenario(base_price=100.0, spread_percent=0.05, num_ticks=100)
	results["low_liquidity_5pct"] = run_stress_test("low_liquidity_5pct", low_liq_extreme, cfg)

	return results


if __name__ == "__main__":
	import json

	suite_results = run_stress_suite()
	print("\n" + "=" * 80)
	print("STRESS TEST SUITE RESULTS")
	print("=" * 80)
	for scenario, result in suite_results.items():
		print(f"\n{scenario}:")
		print(f"  System Stable: {result['system_stable']}")
		print(f"  Risk Blocks: {result['risk_blocks']}")
		if "metrics" in result and result["metrics"]:
			metrics = result["metrics"]
			print(f"  Total PnL: ${metrics.get('total_pnl', 0):.2f}")
			print(f"  Win Rate: {metrics.get('win_rate', 0):.2%}")
			print(f"  Max Drawdown: ${metrics.get('max_drawdown', 0):.2f}")
			print(f"  Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.3f}")
		if "error" in result:
			print(f"  Error: {result['error']}")
	print("\n" + "=" * 80)
