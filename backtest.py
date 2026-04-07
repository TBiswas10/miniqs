"""Backtesting pipeline for simulated historical prices."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from typing import Dict, List

from data_feed import Tick
from execution import ExecutionEngine
from feature_engine import FeatureEngine
from performance import PerformanceTracker
from portfolio import Portfolio
from risk_manager import check_risk
from strategies.mean_reversion import generate_signal as mean_reversion_signal
from strategies.momentum import generate_signal as momentum_signal
from strategy_evaluator import evaluate_signals


def run_backtest(
	prices: List[float],
	config: Dict[str, float] | None = None,
) -> Dict[str, Dict[str, float]]:
	"""Run backtest on historical prices with current pipeline.

	Input:
	- prices: ordered price series
	- config: optional strategy/risk parameters

	Output:
	- dict with pipeline metrics and baseline comparisons
	"""
	if not prices:
		raise ValueError("prices cannot be empty")
	cfg = config or {}

	with tempfile.TemporaryDirectory() as tmp:
		db_path = str(Path(tmp) / "backtest_portfolio.db")
		portfolio = Portfolio(db_path=db_path, initial_cash=float(cfg.get("initial_cash", 100000.0)))
		execution = ExecutionEngine(portfolio=portfolio, paper_mode=True, debug=False)
		features = FeatureEngine(
			ma_window=int(cfg.get("ma_window", 20)),
			long_ma_window=int(cfg.get("long_ma_window", 50)),
			vol_window=int(cfg.get("vol_window", 20)),
			momentum_window=int(cfg.get("momentum_window", 10)),
			debug=bool(cfg.get("feature_debug", False)),
		)
		perf = PerformanceTracker(initial_equity=float(cfg.get("initial_cash", 100000.0)))

		last_trade_ts = None
		for i, p in enumerate(prices):
			ts = datetime.now(timezone.utc) + timedelta(seconds=i)
			tick = Tick(symbol="BT", price=float(p), timestamp=ts, volume=1.0)
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

			# Current portfolio skeleton is long-only; skip unsupported sells with no inventory.
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
			allow, _ = check_risk(trade, risk_state)
			if not allow:
				continue

			result = execution.execute_trade(trade)
			last_trade_ts = ts.isoformat()
			perf.record_trade(float(result["realized_pnl_trade"]))
			perf.record_strategy_trade(chosen.strategy, float(result["realized_pnl_trade"]))

		final_state = portfolio.get_portfolio_state()
		metrics = perf.compute_metrics(latest_total_pnl=float(final_state["total_pnl"]))

	return {
		"pipeline": metrics,
		"baseline_naive_mean_reversion": _baseline_naive_mean_reversion(prices),
		"baseline_pure_momentum": _baseline_pure_momentum(prices),
	}


def optimize_parameters(prices: List[float], base_config: Dict[str, float] | None = None) -> Dict[str, object]:
	"""Run a conservative parameter sweep to avoid large overfitting jumps.

	Input:
	- prices: historical prices
	- base_config: current config baseline

	Output:
	- dict with best_config and all tested results sorted by total_pnl
	"""
	cfg = base_config or {}
	candidates: List[Dict[str, float]] = []

	base_mr = float(cfg.get("mr_threshold", 0.003))
	base_mom = float(cfg.get("mom_threshold", 0.002))
	base_conf = float(cfg.get("confidence_threshold", 0.6))

	for mr_mul in [0.95, 1.0, 1.05]:
		for mom_mul in [0.95, 1.0, 1.05]:
			for conf_shift in [-0.02, 0.0, 0.02]:
				candidate = dict(cfg)
				candidate["mr_threshold"] = max(0.0005, base_mr * mr_mul)
				candidate["mom_threshold"] = max(0.0005, base_mom * mom_mul)
				candidate["confidence_threshold"] = min(0.9, max(0.3, base_conf + conf_shift))
				candidates.append(candidate)

	scored: List[Dict[str, object]] = []
	for candidate in candidates:
		result = run_backtest(prices, config=candidate)
		scored.append({"config": candidate, "pipeline": result["pipeline"]})

	scored.sort(key=lambda x: float(x["pipeline"]["total_pnl"]), reverse=True)
	return {
		"best_config": scored[0]["config"] if scored else dict(cfg),
		"results": scored,
	}


def _baseline_naive_mean_reversion(prices: List[float]) -> Dict[str, float]:
	deltas: List[float] = []
	for i in range(1, len(prices)):
		deltas.append(-(prices[i] - prices[i - 1]))
	return _compute_series_metrics(deltas)


def _baseline_pure_momentum(prices: List[float]) -> Dict[str, float]:
	deltas: List[float] = []
	for i in range(1, len(prices)):
		deltas.append(prices[i] - prices[i - 1])
	return _compute_series_metrics(deltas)


def _compute_series_metrics(pnls: List[float]) -> Dict[str, float]:
	if not pnls:
		return {
			"total_pnl": 0.0,
			"win_rate": 0.0,
			"avg_trade_pnl": 0.0,
			"max_drawdown": 0.0,
			"sharpe_ratio": 0.0,
		}

	total_pnl = float(sum(pnls))
	win_rate = float(sum(1 for p in pnls if p > 0) / len(pnls))
	avg_trade_pnl = float(total_pnl / len(pnls))

	equity = 0.0
	peak = 0.0
	max_dd = 0.0
	for p in pnls:
		equity += p
		peak = max(peak, equity)
		dd = peak - equity
		max_dd = max(max_dd, dd)

	mean_pnl = avg_trade_pnl
	var = sum((p - mean_pnl) ** 2 for p in pnls) / len(pnls)
	std = var ** 0.5
	sharpe = float(mean_pnl / std) if std > 0 else 0.0

	return {
		"total_pnl": total_pnl,
		"win_rate": win_rate,
		"avg_trade_pnl": avg_trade_pnl,
		"max_drawdown": float(max_dd),
		"sharpe_ratio": sharpe,
	}
