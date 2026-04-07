"""Backtesting pipeline for simulated historical prices."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional

from data_feed import Tick
from event_bus import EventBus, EventDispatcher, ExperimentLogEvent, FillEvent, IterationEvent, MarketEvent, OrderEvent, SignalEvent
from execution_simulator import ExecutionSimulationConfig, ExecutionSimulator
from feature_engine import FeatureEngine
from iteration_engine import AutoTuner, ExperimentLogger, RegimeDetector
from performance import PerformanceTracker
from portfolio import Portfolio
from research_store import ResearchDatasetStore
from risk_manager import RiskConfig, RiskEngine
from strategies import StrategyRegistry, default_strategy_registry, generate_weighted_signals
from strategy_evaluator import emit_signal_event, evaluate_signals


@dataclass
class BacktestRuntime:
	portfolio: Portfolio
	features: FeatureEngine
	perf: PerformanceTracker
	risk_engine: RiskEngine
	execution_sim: ExecutionSimulator
	strategy_weights: Dict[str, float]
	mr_threshold: float
	mom_threshold: float
	vb_breakout_factor: float
	confidence_threshold: float
	trade_size: float
	max_position_size: float
	cooldown_seconds: int
	max_loss_per_session: float
	tune_interval: int
	iterative_tuning: bool
	regime_detector: RegimeDetector
	auto_tuner: AutoTuner
	strategy_registry: StrategyRegistry
	run_id: str
	research_store: Optional[ResearchDatasetStore] = None
	experiment_logger: Optional[ExperimentLogger] = None
	recent_prices: List[float] = field(default_factory=list)
	last_tune_equity: float = 100000.0
	iteration_index: int = 0
	last_trade_ts: Optional[str] = None
	tick_index: int = 0


def _on_backtest_market_event(event: MarketEvent, bus: EventBus, runtime: BacktestRuntime) -> None:
	tick = event.tick
	ts = tick.timestamp
	runtime.tick_index += 1
	runtime.recent_prices.append(float(tick.price))
	runtime.recent_prices = runtime.recent_prices[-200:]

	if runtime.research_store is not None:
		ts_iso = ts.isoformat()
		runtime.research_store.log_tick(ts_iso, tick.symbol, tick.price, tick.volume)
		runtime.research_store.log_ohlc(ts_iso, tick.symbol, tick.price, tick.price, tick.price, tick.price, tick.volume)

	snap = runtime.features.update(tick)
	runtime.portfolio.update_pnl(float(tick.price))
	state = runtime.portfolio.get_portfolio_state()
	runtime.perf.record_equity(float(state["equity"]))

	if runtime.research_store is not None:
		runtime.research_store.log_pnl(
			ts.isoformat(),
			float(state["equity"]),
			float(state["total_pnl"]),
			float(state["realized_pnl"]),
			float(state["unrealized_pnl"]),
		)

	if snap is None:
		return

	if runtime.research_store is not None:
		runtime.research_store.log_feature(
			ts.isoformat(),
			tick.symbol,
			tick.price,
			snap.rolling_mean,
			snap.rolling_volatility,
			snap.momentum,
		)

	weights = runtime.strategy_weights
	signals = generate_weighted_signals(
		features=snap,
		registry=runtime.strategy_registry,
		weights=weights,
		enabled={
			"mean_reversion": not bool(runtime.risk_engine.strategy_kill_switch.get("mean_reversion", False)),
			"momentum": not bool(runtime.risk_engine.strategy_kill_switch.get("momentum", False)),
			"volatility_breakout": not bool(runtime.risk_engine.strategy_kill_switch.get("volatility_breakout", False)),
		},
		params={
			"mean_reversion": {"entry_threshold": runtime.mr_threshold},
			"momentum": {"momentum_threshold": runtime.mom_threshold},
			"volatility_breakout": {"breakout_factor": runtime.vb_breakout_factor},
		},
	)
	mr = signals["mean_reversion"]
	mo = signals["momentum"]
	vb = signals["volatility_breakout"]

	if runtime.research_store is not None:
		runtime.research_store.log_signal(ts.isoformat(), mr.strategy, mr.action, mr.confidence, mr.reason)
		runtime.research_store.log_signal(ts.isoformat(), mo.strategy, mo.action, mo.confidence, mo.reason)
		runtime.research_store.log_signal(ts.isoformat(), vb.strategy, vb.action, vb.confidence, vb.reason)

	chosen = evaluate_signals([mr, mo, vb], confidence_threshold=runtime.confidence_threshold)
	if chosen is not None:
		if chosen.action != "sell" or float(state["position_size"]) > 0:
			trade = {
				"action": chosen.action,
				"size": runtime.trade_size,
				"confidence": chosen.confidence,
				"price": float(tick.price),
				"timestamp": ts.isoformat(),
				"strategy": chosen.strategy,
			}
			risk_state = {
				"current_position": float(state["position_size"]),
				"last_trade_timestamp": runtime.last_trade_ts,
				"session_loss": max(0.0, -float(state["total_pnl"])),
				"max_position_size": runtime.max_position_size,
				"cooldown_seconds": runtime.cooldown_seconds,
				"max_loss_per_session": runtime.max_loss_per_session,
				"daily_loss_limit": runtime.max_loss_per_session,
				"confidence_threshold": runtime.confidence_threshold,
				"equity": float(state["equity"]),
				"total_pnl": float(state["total_pnl"]),
				"market_volatility": float(snap.rolling_volatility),
				"strategy_weight": float(weights.get(chosen.strategy, 0.0)),
			}
			emit_signal_event(bus=bus, chosen=chosen, trade=trade, risk_state=risk_state)

	if runtime.iterative_tuning and runtime.tick_index > 0 and runtime.tick_index % runtime.tune_interval == 0:
		market = runtime.regime_detector.detect(runtime.recent_prices)
		state_now = runtime.portfolio.get_portfolio_state()
		strategy_metrics = runtime.perf.strategy_metrics_for_feedback()
		outcomes = {
			"equity_delta": float(state_now["equity"]) - runtime.last_tune_equity,
			"drawdown": float(runtime.perf.compute_metrics(float(state_now["total_pnl"]))["max_drawdown"]),
			"total_pnl": float(state_now["total_pnl"]),
		}
		bus.publish(
			IterationEvent(
				run_id=runtime.run_id,
				iteration=runtime.iteration_index,
				current_weights=dict(runtime.strategy_weights),
				risk_params={
					"base_trade_size": runtime.trade_size,
					"max_position_size": runtime.max_position_size,
					"cooldown_seconds": runtime.cooldown_seconds,
				},
				market_conditions={
					"regime": market.regime,
					"realized_volatility": float(market.realized_volatility),
					"trend_slope": float(market.trend_slope),
					"momentum": float(market.momentum),
				},
				outcomes=outcomes,
				strategy_metrics={k: dict(v) for k, v in strategy_metrics.items()},
				iteration_equity=float(state_now["equity"]),
			)
		)


def _on_backtest_signal_event(event: SignalEvent, bus: EventBus, runtime: BacktestRuntime) -> None:
	allow, reason, adjusted_trade, _ = runtime.risk_engine.assess_trade(event.trade, event.risk_state)
	if not allow:
		return
	bus.publish(OrderEvent(strategy=event.strategy, trade=adjusted_trade, reason=reason))


def _on_backtest_order_event(event: OrderEvent, bus: EventBus, runtime: BacktestRuntime) -> None:
	simulated = runtime.execution_sim.simulate(event.trade)
	filled_size = float(simulated.get("filled_size", 0.0))
	if filled_size <= 0:
		return

	ref_price = float(event.trade.get("price", 0.0))
	fill_price = float(simulated.get("avg_fill_price", ref_price))
	latency_ms = int(simulated.get("latency_ms", 0))
	trade_ts_raw = str(event.trade.get("timestamp", datetime.now(timezone.utc).isoformat()))
	trade_ts = datetime.fromisoformat(trade_ts_raw)
	fill_ts = trade_ts + timedelta(milliseconds=latency_ms)

	portfolio_trade = {
		"action": str(event.trade.get("action", "buy")),
		"size": filled_size,
		"price": fill_price,
		"timestamp": fill_ts.isoformat(),
	}
	result = runtime.portfolio.execute_trade(portfolio_trade)
	result["requested_size"] = float(event.trade.get("size", filled_size))
	result["filled_size"] = filled_size
	result["remaining_size"] = float(simulated.get("remaining_size", 0.0))
	result["order_state"] = str(simulated.get("final_state", "filled"))
	result["order_state_path"] = [str(step.get("state", "")) for step in simulated.get("path", []) if isinstance(step, dict)]
	result["expected_price"] = ref_price
	result["applied_price"] = fill_price
	result["slippage"] = fill_price - ref_price
	result["latency_ms"] = latency_ms
	bus.publish(FillEvent(strategy=event.strategy, trade=event.trade, result=result))


def _on_backtest_fill_event(event: FillEvent, bus: EventBus, runtime: BacktestRuntime) -> None:
	runtime.last_trade_ts = str(event.result.get("timestamp", event.trade.get("timestamp", "")))
	runtime.perf.record_trade(float(event.result["realized_pnl_trade"]))
	runtime.perf.record_strategy_trade(event.strategy, float(event.result["realized_pnl_trade"]))
	state = runtime.portfolio.get_portfolio_state()
	runtime.risk_engine.record_execution(
		strategy=event.strategy,
		realized_pnl_trade=float(event.result["realized_pnl_trade"]),
		equity=float(state["equity"]),
	)
	if runtime.research_store is not None:
		runtime.research_store.log_fill(str(event.result.get("timestamp", event.trade.get("timestamp", ""))), event.strategy, event.result)


def _on_backtest_iteration_event(event: IterationEvent, bus: EventBus, runtime: BacktestRuntime) -> None:
	market = runtime.regime_detector.detect(runtime.recent_prices)
	rec = runtime.auto_tuner.recommend(
		current_weights=event.current_weights,
		risk_params=event.risk_params,
		market_conditions=market,
		outcomes=event.outcomes,
		strategy_metrics=event.strategy_metrics,
	)
	runtime.strategy_weights = dict(rec["strategy_weights"])
	risk_rec = dict(rec["risk_params"])
	runtime.trade_size = float(risk_rec["base_trade_size"])
	runtime.max_position_size = float(risk_rec["max_position_size"])
	runtime.cooldown_seconds = int(risk_rec["cooldown_seconds"])

	bus.publish(
		ExperimentLogEvent(
			run_id=event.run_id,
			iteration=event.iteration,
			parameter_set={
				"weights": dict(runtime.strategy_weights),
				"mr_threshold": runtime.mr_threshold,
				"mom_threshold": runtime.mom_threshold,
				"confidence_threshold": runtime.confidence_threshold,
				"trade_size": runtime.trade_size,
				"max_position_size": runtime.max_position_size,
				"cooldown_seconds": runtime.cooldown_seconds,
			},
			market_conditions=dict(rec["market_conditions"]),
			outcomes=dict(event.outcomes),
			recommendations=dict(rec),
			iteration_equity=float(event.iteration_equity),
		)
	)


def _on_backtest_experiment_log_event(event: ExperimentLogEvent, bus: EventBus, runtime: BacktestRuntime) -> None:
	if runtime.experiment_logger is not None:
		runtime.experiment_logger.log_experiment(
			run_id=event.run_id,
			iteration=event.iteration,
			parameter_set=event.parameter_set,
			market_conditions=event.market_conditions,
			outcomes=event.outcomes,
			recommendations=event.recommendations,
		)
	runtime.last_tune_equity = float(event.iteration_equity)
	runtime.iteration_index += 1


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
		features = FeatureEngine(
			ma_window=int(cfg.get("ma_window", 20)),
			long_ma_window=int(cfg.get("long_ma_window", 50)),
			vol_window=int(cfg.get("vol_window", 20)),
			momentum_window=int(cfg.get("momentum_window", 10)),
			debug=bool(cfg.get("feature_debug", False)),
		)
		perf = PerformanceTracker(initial_equity=float(cfg.get("initial_cash", 100000.0)))
		strategy_weights = {
			"mean_reversion": float(cfg.get("w_mean_reversion", 0.4)),
			"momentum": float(cfg.get("w_momentum", 0.4)),
			"volatility_breakout": float(cfg.get("w_volatility_breakout", 0.2)),
		}
		mr_threshold = float(cfg.get("mr_threshold", 0.003))
		mom_threshold = float(cfg.get("mom_threshold", 0.002))
		vb_breakout_factor = float(cfg.get("vb_breakout_factor", 1.2))
		confidence_threshold = float(cfg.get("confidence_threshold", 0.6))
		trade_size = float(cfg.get("trade_size", 1.0))
		max_position_size = float(cfg.get("max_position_size", 5.0))
		cooldown_seconds = int(cfg.get("cooldown_seconds", 5))
		max_loss_per_session = float(cfg.get("max_loss_per_session", 500.0))
		tune_interval = int(cfg.get("tune_interval", 50))
		risk_engine = RiskEngine(
			initial_equity=float(cfg.get("initial_cash", 100000.0)),
			config=RiskConfig(
				base_trade_size=trade_size,
				max_position_size=max_position_size,
				cooldown_seconds=cooldown_seconds,
				max_loss_per_session=max_loss_per_session,
				daily_loss_limit=max_loss_per_session,
				confidence_threshold=confidence_threshold,
				risk_per_trade=float(cfg.get("risk_per_trade", 0.01)),
			),
		)
		execution_sim = ExecutionSimulator(
			config=ExecutionSimulationConfig(
				spread_bps=float(cfg.get("spread_bps", 1.5)),
				slippage_bps=float(cfg.get("slippage_bps", 3.0)),
				impact_bps_per_unit=float(cfg.get("impact_bps_per_unit", 0.25)),
				partial_fill_probability=float(cfg.get("partial_fill_probability", 0.35)),
				cancel_remainder_probability=float(cfg.get("cancel_remainder_probability", 0.2)),
				reject_probability=float(cfg.get("reject_probability", 0.0)),
				min_fill_slice=float(cfg.get("min_fill_slice", 0.1)),
				min_latency_ms=int(cfg.get("min_latency_ms", 50)),
				max_latency_ms=int(cfg.get("max_latency_ms", 200)),
			),
			seed=int(cfg.get("execution_seed", 42)),
		)

		runtime = BacktestRuntime(
			portfolio=portfolio,
			features=features,
			perf=perf,
			risk_engine=risk_engine,
			execution_sim=execution_sim,
			strategy_weights=strategy_weights,
			mr_threshold=mr_threshold,
			mom_threshold=mom_threshold,
			vb_breakout_factor=vb_breakout_factor,
			confidence_threshold=confidence_threshold,
			trade_size=trade_size,
			max_position_size=max_position_size,
			cooldown_seconds=cooldown_seconds,
			max_loss_per_session=max_loss_per_session,
			tune_interval=tune_interval,
			iterative_tuning=iterative_tuning,
			regime_detector=regime_detector,
			auto_tuner=auto_tuner,
			strategy_registry=default_strategy_registry(),
			run_id=run_id,
			research_store=research_store,
			experiment_logger=experiment_logger,
			last_tune_equity=float(cfg.get("initial_cash", 100000.0)),
		)

		bus = EventBus()
		dispatcher = EventDispatcher()
		dispatcher.register(MarketEvent, _on_backtest_market_event)
		dispatcher.register(SignalEvent, _on_backtest_signal_event)
		dispatcher.register(OrderEvent, _on_backtest_order_event)
		dispatcher.register(FillEvent, _on_backtest_fill_event)
		dispatcher.register(IterationEvent, _on_backtest_iteration_event)
		dispatcher.register(ExperimentLogEvent, _on_backtest_experiment_log_event)

		for i, p in enumerate(prices):
			ts = datetime.now(timezone.utc) + timedelta(seconds=i)
			tick = Tick(symbol="BT", price=float(p), timestamp=ts, volume=1.0)
			bus.publish(MarketEvent(tick=tick))
			while len(bus) > 0:
				next_event = bus.consume()
				if next_event is None:
					break
				dispatcher.dispatch(next_event, bus, runtime)

		final_state = runtime.portfolio.get_portfolio_state()
		metrics = runtime.perf.compute_metrics(latest_total_pnl=float(final_state["total_pnl"]))
		if research_store is not None:
			strategy_metrics = runtime.perf.strategy_metrics_for_feedback()
			for strategy, sm in strategy_metrics.items():
				research_store.log_strategy_metric(datetime.now(timezone.utc).isoformat(), strategy, sm)

	result = {
		"pipeline": metrics,
		"baseline_naive_mean_reversion": _baseline_naive_mean_reversion(prices),
		"baseline_pure_momentum": _baseline_pure_momentum(prices),
		"final_iteration_state": {
			"strategy_weights": runtime.strategy_weights,
			"trade_size": runtime.trade_size,
			"max_position_size": runtime.max_position_size,
			"cooldown_seconds": runtime.cooldown_seconds,
			"iterations": runtime.iteration_index,
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
