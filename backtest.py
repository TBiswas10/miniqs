"""Backtesting pipeline for simulated historical prices."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from typing import Dict, List

from data_feed import Tick
from execution import ExecutionEngine
from feature_engine import FeatureEngine
from iteration_engine import AutoTuner, ExperimentLogger, RegimeDetector
from performance import PerformanceTracker
from portfolio import Portfolio
from research_store import ResearchDatasetStore
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
	persist_research = bool(cfg.get("persist_research", True))
	iterative_tuning = bool(cfg.get("iterative_tuning", True))
	research_store: ResearchDatasetStore | None = None
	research_version: str | None = None
	experiment_logger: ExperimentLogger | None = None
	regime_detector = RegimeDetector(window=int(cfg.get("regime_window", 40)))
	auto_tuner = AutoTuner()
	run_id = datetime.now(timezone.utc).strftime("backtest_%Y%m%d_%H%M%S")
	if persist_research:
		research_store = ResearchDatasetStore(
			dataset_name=str(cfg.get("dataset_name", "backtest")),
			root_dir=str(cfg.get("research_output_dir", "research_data")),
		)
		experiment_logger = ExperimentLogger(
			db_path=str(Path(cfg.get("research_output_dir", "research_data")) / "experiment_history.db")
		)
		research_version = research_store.create_version(
			{
				"mode": "backtest",
				"num_prices": len(prices),
				"config": cfg,
			}
		)

	with tempfile.TemporaryDirectory() as tmp:
		db_path = str(Path(tmp) / "backtest_portfolio.db")
		portfolio = Portfolio(db_path=db_path, initial_cash=float(cfg.get("initial_cash", 100000.0)))
		execution = ExecutionEngine(portfolio=portfolio, paper_mode=True, debug=False, realistic_simulation=True)
		features = FeatureEngine(
			ma_window=int(cfg.get("ma_window", 20)),
			long_ma_window=int(cfg.get("long_ma_window", 50)),
			vol_window=int(cfg.get("vol_window", 20)),
			momentum_window=int(cfg.get("momentum_window", 10)),
			debug=bool(cfg.get("feature_debug", False)),
		)
		perf = PerformanceTracker(initial_equity=float(cfg.get("initial_cash", 100000.0)))
		strategy_weights = {
			"mean_reversion": float(cfg.get("w_mean_reversion", 0.5)),
			"momentum": float(cfg.get("w_momentum", 0.5)),
		}
		mr_threshold = float(cfg.get("mr_threshold", 0.003))
		mom_threshold = float(cfg.get("mom_threshold", 0.002))
		confidence_threshold = float(cfg.get("confidence_threshold", 0.6))
		trade_size = float(cfg.get("trade_size", 1.0))
		max_position_size = float(cfg.get("max_position_size", 5.0))
		cooldown_seconds = int(cfg.get("cooldown_seconds", 5))
		max_loss_per_session = float(cfg.get("max_loss_per_session", 500.0))
		tune_interval = int(cfg.get("tune_interval", 50))
		recent_prices: List[float] = []
		last_tune_equity = float(cfg.get("initial_cash", 100000.0))
		iteration_index = 0

		last_trade_ts = None
		for i, p in enumerate(prices):
			ts = datetime.now(timezone.utc) + timedelta(seconds=i)
			recent_prices.append(float(p))
			recent_prices = recent_prices[-200:]
			tick = Tick(symbol="BT", price=float(p), timestamp=ts, volume=1.0)
			if research_store is not None:
				ts_iso = ts.isoformat()
				research_store.log_tick(ts_iso, tick.symbol, tick.price, tick.volume)
				research_store.log_ohlc(ts_iso, tick.symbol, tick.price, tick.price, tick.price, tick.price, tick.volume)
			snap = features.update(tick)
			portfolio.update_pnl(float(p))
			state = portfolio.get_portfolio_state()
			if research_store is not None:
				research_store.log_pnl(
					ts.isoformat(),
					float(state["equity"]),
					float(state["total_pnl"]),
					float(state["realized_pnl"]),
					float(state["unrealized_pnl"]),
				)
			perf.record_equity(float(state["equity"]))

			if snap is None:
				continue
			if research_store is not None:
				research_store.log_feature(
					ts.isoformat(),
					tick.symbol,
					tick.price,
					snap.rolling_mean,
					snap.rolling_volatility,
					snap.momentum,
				)

			mr = mean_reversion_signal(snap, entry_threshold=mr_threshold)
			mo = momentum_signal(snap, momentum_threshold=mom_threshold)
			mr = mr.__class__(
				strategy=mr.strategy,
				action=mr.action,
				confidence=min(1.0, mr.confidence * strategy_weights.get("mean_reversion", 0.5)),
				reason=mr.reason,
			)
			mo = mo.__class__(
				strategy=mo.strategy,
				action=mo.action,
				confidence=min(1.0, mo.confidence * strategy_weights.get("momentum", 0.5)),
				reason=mo.reason,
			)
			if research_store is not None:
				research_store.log_signal(ts.isoformat(), mr.strategy, mr.action, mr.confidence, mr.reason)
				research_store.log_signal(ts.isoformat(), mo.strategy, mo.action, mo.confidence, mo.reason)
			chosen = evaluate_signals([mr, mo], confidence_threshold=confidence_threshold)
			if chosen is None:
				if iterative_tuning and i > 0 and i % tune_interval == 0:
					market = regime_detector.detect(recent_prices)
					state_now = portfolio.get_portfolio_state()
					strategy_metrics = perf.strategy_metrics_for_feedback()
					outcomes = {
						"equity_delta": float(state_now["equity"]) - last_tune_equity,
						"drawdown": float(perf.compute_metrics(float(state_now["total_pnl"]))["max_drawdown"]),
						"total_pnl": float(state_now["total_pnl"]),
					}
					rec = auto_tuner.recommend(
						current_weights=strategy_weights,
						risk_params={
							"base_trade_size": trade_size,
							"max_position_size": max_position_size,
							"cooldown_seconds": cooldown_seconds,
						},
						market_conditions=market,
						outcomes=outcomes,
						strategy_metrics=strategy_metrics,
					)
					strategy_weights = dict(rec["strategy_weights"])
					risk_rec = dict(rec["risk_params"])
					trade_size = float(risk_rec["base_trade_size"])
					max_position_size = float(risk_rec["max_position_size"])
					cooldown_seconds = int(risk_rec["cooldown_seconds"])
					if experiment_logger is not None:
						experiment_logger.log_experiment(
							run_id=run_id,
							iteration=iteration_index,
							parameter_set={
								"weights": strategy_weights,
								"mr_threshold": mr_threshold,
								"mom_threshold": mom_threshold,
								"confidence_threshold": confidence_threshold,
								"trade_size": trade_size,
								"max_position_size": max_position_size,
								"cooldown_seconds": cooldown_seconds,
							},
							market_conditions=rec["market_conditions"],
							outcomes=outcomes,
							recommendations=rec,
						)
					last_tune_equity = float(state_now["equity"])
					iteration_index += 1
				continue

			# Current portfolio skeleton is long-only; skip unsupported sells with no inventory.
			if chosen.action == "sell" and float(state["position_size"]) <= 0:
				continue

			trade = {
				"action": chosen.action,
				"size": trade_size,
				"confidence": chosen.confidence,
				"price": float(p),
				"timestamp": ts.isoformat(),
				"strategy": chosen.strategy,
			}
			risk_state = {
				"current_position": float(state["position_size"]),
				"last_trade_timestamp": last_trade_ts,
				"session_loss": max(0.0, -float(state["total_pnl"])),
				"max_position_size": max_position_size,
				"cooldown_seconds": cooldown_seconds,
				"max_loss_per_session": max_loss_per_session,
			}
			allow, _ = check_risk(trade, risk_state)
			if not allow:
				continue

			result = execution.execute_trade(trade)
			last_trade_ts = ts.isoformat()
			perf.record_trade(float(result["realized_pnl_trade"]))
			perf.record_strategy_trade(chosen.strategy, float(result["realized_pnl_trade"]))
			if research_store is not None:
				research_store.log_fill(ts.isoformat(), chosen.strategy, result)

		final_state = portfolio.get_portfolio_state()
		metrics = perf.compute_metrics(latest_total_pnl=float(final_state["total_pnl"]))
		if research_store is not None:
			strategy_metrics = perf.strategy_metrics_for_feedback()
			for strategy, sm in strategy_metrics.items():
				research_store.log_strategy_metric(datetime.now(timezone.utc).isoformat(), strategy, sm)

	result = {
		"pipeline": metrics,
		"baseline_naive_mean_reversion": _baseline_naive_mean_reversion(prices),
		"baseline_pure_momentum": _baseline_pure_momentum(prices),
		"final_iteration_state": {
			"strategy_weights": strategy_weights,
			"trade_size": trade_size,
			"max_position_size": max_position_size,
			"cooldown_seconds": cooldown_seconds,
			"iterations": iteration_index,
		},
	}
	if research_version is not None:
		result["research_version"] = research_version
	return result


def run_walk_forward_backtest(
	prices: List[float],
	window_size: int = 100,
	step_size: int = 50,
	config: Dict[str, float] | None = None,
) -> Dict[str, object]:
	"""Walk-forward optimization with explicit in-sample/out-of-sample reports."""
	if not prices:
		raise ValueError("prices cannot be empty")
	cfg = config or {}
	folds: List[Dict[str, object]] = []

	for wf_idx in range(0, len(prices) - window_size - step_size, step_size):
		train_end = wf_idx + window_size
		test_end = train_end + step_size
		if test_end > len(prices):
			break

		train_prices = prices[:train_end]
		test_prices = prices[train_end:test_end]

		opt_result = optimize_parameters(train_prices, base_config=cfg)
		best_cfg = dict(opt_result["best_config"])

		in_sample = run_backtest(train_prices, config={**best_cfg, "persist_research": True, "dataset_name": "wf_train"})
		out_sample = run_backtest(test_prices, config={**best_cfg, "persist_research": True, "dataset_name": "wf_test"})

		folds.append(
			{
				"wf_index": wf_idx,
				"train_ticks": len(train_prices),
				"test_ticks": len(test_prices),
				"optimized_config": best_cfg,
				"in_sample": in_sample["pipeline"],
				"out_of_sample": out_sample["pipeline"],
				"train_research_version": in_sample.get("research_version"),
				"test_research_version": out_sample.get("research_version"),
			}
		)

		cfg = best_cfg

	return {
		"folds": folds,
		"num_folds": len(folds),
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
