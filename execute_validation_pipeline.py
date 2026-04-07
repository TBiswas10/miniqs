"""
Comprehensive validation pipeline for the Mini Quant System.
Executes:
1. Historical backtesting with baseline comparisons
2. Walk-forward testing with incremental optimization
3. Stress testing with 9 scenarios
4. Live paper trading simulation
5. Generates CSV + JSON reports
"""

from __future__ import annotations

import csv
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backtest import run_backtest, optimize_parameters
from data_feed import DataFeed
from execution import ExecutionEngine
from feature_engine import FeatureEngine
from main import FeedbackLoop
from performance import PerformanceTracker
from portfolio import Portfolio
from risk_manager import check_risk
from strategies.mean_reversion import generate_signal as mean_reversion_signal
from strategies.momentum import generate_signal as momentum_signal
from strategy_evaluator import evaluate_signals
from stress_testing import (
    generate_spike_scenario,
    generate_high_volatility_scenario,
    generate_downtrend_scenario,
    generate_low_liquidity_scenario,
    run_stress_test,
)


class ValidationPipeline:
    """Orchestrates all validation stages with reporting."""

    def __init__(self, output_dir: str = "validation_reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.reports = {
            "backtest": [],
            "walk_forward": [],
            "stress_testing": [],
            "live_paper": [],
        }

    def generate_historical_prices(
        self,
        base_price: float = 100.0,
        num_ticks: int = 500,
        trend: float = 0.0001,
        volatility: float = 0.005,
        seed: int = 42,
    ) -> List[float]:
        """Generate synthetic but realistic historical price series.

        Args:
            base_price: starting price
            num_ticks: total price points
            trend: drift per tick
            volatility: standard deviation per tick
            seed: RNG seed for reproducibility

        Returns:
            list of prices
        """
        import random

        random.seed(seed)
        prices = [base_price]
        for _ in range(num_ticks - 1):
            change = random.gauss(trend, volatility)
            new_price = prices[-1] * (1.0 + change)
            prices.append(max(1.0, new_price))
        return prices

    def run_historical_backtesting(
        self,
        prices: Optional[List[float]] = None,
        config: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """Execute historical backtest.

        Args:
            prices: historical price series (generated if None)
            config: strategy/risk configuration

        Returns:
            dict with backtest metrics and baseline comparisons
        """
        if prices is None:
            prices = self.generate_historical_prices(num_ticks=500)

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

        print("[backtest] Running historical backtest on 500 ticks...")
        result = run_backtest(prices, config=cfg)

        self.reports["backtest"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "num_ticks": len(prices),
            "pipeline_metrics": result["pipeline"],
            "baseline_naive_mean_reversion": result["baseline_naive_mean_reversion"],
            "baseline_pure_momentum": result["baseline_pure_momentum"],
            "config": cfg,
        })

        return self.reports["backtest"][-1]

    def run_walk_forward_testing(
        self,
        prices: Optional[List[float]] = None,
        window_size: int = 100,
        step_size: int = 50,
        config: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute walk-forward testing with incremental optimization.

        Splits prices into sequential windows:
        1. Train on window 1, optimize, test on window 2
        2. Train on windows 1-2, optimize, test on window 3
        ... and so on.

        Args:
            prices: historical price series
            window_size: training window size
            step_size: forward step for test window
            config: base configuration

        Returns:
            list of results per walk-forward period
        """
        if prices is None:
            prices = self.generate_historical_prices(num_ticks=500)

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

        results = []
        print(f"[walk_forward] Running walk-forward test (window={window_size}, step={step_size})...")

        for wf_idx in range(0, len(prices) - window_size - step_size, step_size):
            train_end = wf_idx + window_size
            test_end = train_end + step_size

            if test_end > len(prices):
                break

            train_prices = prices[:train_end]
            test_prices = prices[train_end:test_end]

            print(
                f"  [walk_forward {wf_idx}] Training on ticks 0-{train_end}, "
                f"testing on {train_end}-{test_end}..."
            )

            # Optimize on training set
            opt_result = optimize_parameters(train_prices, base_config=cfg)
            best_cfg = opt_result["best_config"]

            # Test on unseen window
            test_result = run_backtest(test_prices, config=best_cfg)

            results.append({
                "wf_index": wf_idx,
                "train_ticks": len(train_prices),
                "test_ticks": len(test_prices),
                "optimized_config": best_cfg,
                "test_metrics": test_result["pipeline"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            # Update base config for incremental optimization
            cfg = best_cfg

        self.reports["walk_forward"] = results
        return results

    def run_stress_testing_suite(
        self,
        base_price: float = 100.0,
        config: Optional[Dict[str, float]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute all 9 stress test scenarios.

        Scenarios:
        1. +5% spike
        2. -5% spike (gap down)
        3. 2x volatility
        4. 3x volatility
        5. 20% downtrend
        6. 10% downtrend
        7. 2% spread (low liquidity)
        8. 4% spread (extreme illiquidity)
        9. Recovery after shock

        Args:
            base_price: starting price for synthetic scenarios
            config: strategy/risk config

        Returns:
            list of stress test results
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

        scenarios = [
            ("spike_up_5pct", generate_spike_scenario(base_price, 0.05, 100)),
            ("spike_down_5pct", generate_spike_scenario(base_price, -0.05, 100)),
            ("high_volatility_2x", generate_high_volatility_scenario(base_price, 2.0, 100)),
            ("high_volatility_3x", generate_high_volatility_scenario(base_price, 3.0, 100)),
            ("downtrend_20pct", generate_downtrend_scenario(base_price, 0.20, 100)),
            ("downtrend_10pct", generate_downtrend_scenario(base_price, 0.10, 100)),
            ("low_liquidity_2pct_spread", generate_low_liquidity_scenario(base_price, 0.02, 100)),
            ("low_liquidity_4pct_spread", generate_low_liquidity_scenario(base_price, 0.04, 100)),
        ]

        # Recovery scenario: down then up
        recovery_prices = (
            self.generate_historical_prices(
                base_price=base_price,
                num_ticks=50,
                trend=-0.002,
                volatility=0.01,
                seed=123,
            )
            + self.generate_historical_prices(
                base_price=base_price * 0.90,
                num_ticks=50,
                trend=0.002,
                volatility=0.01,
                seed=456,
            )
        )
        scenarios.append(("recovery_after_shock", recovery_prices))

        results = []
        print(f"[stress_testing] Running {len(scenarios)} stress test scenarios...")

        for scenario_name, prices in scenarios:
            print(f"  [stress_test] {scenario_name}...")
            result = run_stress_test(scenario_name, prices, config=cfg)
            result["timestamp"] = datetime.now(timezone.utc).isoformat()
            results.append(result)

        self.reports["stress_testing"] = results
        return results

    def run_live_paper_trading_simulation(
        self,
        duration_seconds: int = 300,
        tick_interval: float = 0.5,
        config: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        """Simulate live paper trading with real-time signal generation and execution.

        Args:
            duration_seconds: simulation duration
            tick_interval: seconds between ticks
            config: strategy/risk config

        Returns:
            dict with paper trading metrics and trade log
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

        print(f"[live_paper] Starting paper trading simulation for {duration_seconds}s...")

        with tempfile.TemporaryDirectory() as tmp:
            db_path = str(Path(tmp) / "live_paper_trading.db")
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
            feedback_loop = FeedbackLoop()

            # Data feed
            feed = DataFeed(symbol="LIVE", mode="simulated", seed=999)

            trades_executed = []
            signals_generated = 0
            trades_blocked = 0
            last_trade_ts = None
            num_ticks = 0
            max_ticks = int(duration_seconds / tick_interval)
            tick_counter = 0

            for tick in feed.stream():
                tick_counter += 1
                if tick_counter > max_ticks:
                    break
                num_ticks += 1
                snap = features.update(tick)
                portfolio.update_pnl(tick.price)
                state = portfolio.get_portfolio_state()
                perf.record_equity(float(state["equity"]))

                if snap is None:
                    continue

                # Generate signals
                mr = mean_reversion_signal(snap, entry_threshold=float(cfg.get("mr_threshold", 0.003)))
                mo = momentum_signal(snap, momentum_threshold=float(cfg.get("mom_threshold", 0.002)))
                chosen = evaluate_signals([mr, mo], confidence_threshold=float(cfg.get("confidence_threshold", 0.6)))

                if chosen is None:
                    continue

                signals_generated += 1

                # Handle long-only constraint
                if chosen.action == "sell" and float(state["position_size"]) <= 0:
                    trades_blocked += 1
                    continue

                trade = {
                    "action": chosen.action,
                    "size": float(cfg.get("trade_size", 1.0)),
                    "confidence": chosen.confidence,
                    "price": tick.price,
                    "timestamp": tick.timestamp.isoformat(),
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
                    trades_blocked += 1
                    continue

                result = execution.execute_trade(trade)
                last_trade_ts = tick.timestamp.isoformat()
                perf.record_trade(float(result["realized_pnl_trade"]))
                perf.record_strategy_trade(chosen.strategy, float(result["realized_pnl_trade"]))

                trades_executed.append({
                    "tick": num_ticks,
                    "action": chosen.action,
                    "price": tick.price,
                    "strategy": chosen.strategy,
                    "confidence": chosen.confidence,
                    "pnl": float(result["realized_pnl_trade"]),
                    "timestamp": tick.timestamp.isoformat(),
                })

            final_state = portfolio.get_portfolio_state()
            metrics = perf.compute_metrics(latest_total_pnl=float(final_state["total_pnl"]))

            result = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": duration_seconds,
                "num_ticks": num_ticks,
                "signals_generated": signals_generated,
                "trades_executed": len(trades_executed),
                "trades_blocked": trades_blocked,
                "metrics": metrics,
                "final_portfolio_state": final_state,
                "trades": trades_executed,
            }

            self.reports["live_paper"].append(result)
            return result

    def save_reports_to_csv(self) -> None:
        """Save all reports to CSV files."""
        # Backtest report
        if self.reports["backtest"]:
            csv_path = self.output_dir / f"backtest_report_{self.timestamp}.csv"
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "timestamp",
                        "num_ticks",
                        "pipeline_total_pnl",
                        "pipeline_sharpe_ratio",
                        "pipeline_max_drawdown",
                        "pipeline_win_rate",
                        "pipeline_trade_count",
                        "naive_mr_total_pnl",
                        "pure_mom_total_pnl",
                    ],
                )
                writer.writeheader()
                for report in self.reports["backtest"]:
                    writer.writerow({
                        "timestamp": report["timestamp"],
                        "num_ticks": report["num_ticks"],
                        "pipeline_total_pnl": report["pipeline_metrics"]["total_pnl"],
                        "pipeline_sharpe_ratio": report["pipeline_metrics"]["sharpe_ratio"],
                        "pipeline_max_drawdown": report["pipeline_metrics"]["max_drawdown"],
                        "pipeline_win_rate": report["pipeline_metrics"]["win_rate"],
                        "pipeline_trade_count": int(report["pipeline_metrics"]["trade_count"]),
                        "naive_mr_total_pnl": report["baseline_naive_mean_reversion"]["total_pnl"],
                        "pure_mom_total_pnl": report["baseline_pure_momentum"]["total_pnl"],
                    })
            print(f"✓ Backtest report saved to {csv_path}")

        # Walk-forward report
        if self.reports["walk_forward"]:
            csv_path = self.output_dir / f"walk_forward_report_{self.timestamp}.csv"
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "wf_index",
                        "train_ticks",
                        "test_ticks",
                        "test_total_pnl",
                        "test_sharpe_ratio",
                        "test_max_drawdown",
                        "test_win_rate",
                    ],
                )
                writer.writeheader()
                for report in self.reports["walk_forward"]:
                    writer.writerow({
                        "wf_index": report["wf_index"],
                        "train_ticks": report["train_ticks"],
                        "test_ticks": report["test_ticks"],
                        "test_total_pnl": report["test_metrics"]["total_pnl"],
                        "test_sharpe_ratio": report["test_metrics"]["sharpe_ratio"],
                        "test_max_drawdown": report["test_metrics"]["max_drawdown"],
                        "test_win_rate": report["test_metrics"]["win_rate"],
                    })
            print(f"✓ Walk-forward report saved to {csv_path}")

        # Stress testing report
        if self.reports["stress_testing"]:
            csv_path = self.output_dir / f"stress_testing_report_{self.timestamp}.csv"
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "scenario",
                        "total_pnl",
                        "sharpe_ratio",
                        "max_drawdown",
                        "win_rate",
                        "system_stable",
                    ],
                )
                writer.writeheader()
                for report in self.reports["stress_testing"]:
                    writer.writerow({
                        "scenario": report["scenario"],
                        "total_pnl": report["metrics"]["total_pnl"],
                        "sharpe_ratio": report["metrics"]["sharpe_ratio"],
                        "max_drawdown": report["metrics"]["max_drawdown"],
                        "win_rate": report["metrics"]["win_rate"],
                        "system_stable": report.get("system_stable", True),
                    })
            print(f"✓ Stress testing report saved to {csv_path}")

        # Live paper trading report
        if self.reports["live_paper"]:
            csv_path = self.output_dir / f"live_paper_trading_report_{self.timestamp}.csv"
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=[
                        "timestamp",
                        "duration_seconds",
                        "num_ticks",
                        "signals_generated",
                        "trades_executed",
                        "trades_blocked",
                        "total_pnl",
                        "sharpe_ratio",
                        "max_drawdown",
                        "win_rate",
                    ],
                )
                writer.writeheader()
                for report in self.reports["live_paper"]:
                    writer.writerow({
                        "timestamp": report["timestamp"],
                        "duration_seconds": report["duration_seconds"],
                        "num_ticks": report["num_ticks"],
                        "signals_generated": report["signals_generated"],
                        "trades_executed": report["trades_executed"],
                        "trades_blocked": report["trades_blocked"],
                        "total_pnl": report["metrics"]["total_pnl"],
                        "sharpe_ratio": report["metrics"]["sharpe_ratio"],
                        "max_drawdown": report["metrics"]["max_drawdown"],
                        "win_rate": report["metrics"]["win_rate"],
                    })
            print(f"✓ Live paper trading report saved to {csv_path}")

    def save_reports_to_json(self) -> None:
        """Save all reports to JSON files (with serialization handling)."""
        json_path = self.output_dir / f"validation_pipeline_report_{self.timestamp}.json"

        # Serialize reports, converting any non-JSON-compatible types
        def serialize_value(val: Any) -> Any:
            if isinstance(val, float):
                return round(val, 8)
            if isinstance(val, dict):
                return {k: serialize_value(v) for k, v in val.items()}
            if isinstance(val, (list, tuple)):
                return [serialize_value(item) for item in val]
            return val

        serialized_reports = {
            "backtest": [serialize_value(r) for r in self.reports["backtest"]],
            "walk_forward": [serialize_value(r) for r in self.reports["walk_forward"]],
            "stress_testing": [serialize_value(r) for r in self.reports["stress_testing"]],
            "live_paper": [serialize_value(r) for r in self.reports["live_paper"]],
        }

        with open(json_path, "w") as f:
            json.dump(serialized_reports, f, indent=2)

        print(f"✓ Full JSON report saved to {json_path}")

    def generate_summary_report(self) -> str:
        """Generate a human-readable summary of all validation results."""
        lines = [
            "=" * 80,
            "MINI QUANT SYSTEM - VALIDATION PIPELINE SUMMARY",
            "=" * 80,
            f"Timestamp: {datetime.now(timezone.utc).isoformat()}",
            "",
        ]

        # Backtest summary
        if self.reports["backtest"]:
            report = self.reports["backtest"][0]
            metrics = report["pipeline_metrics"]
            lines.extend([
                "1. HISTORICAL BACKTESTING",
                "-" * 40,
                f"Total Ticks: {report['num_ticks']}",
                f"Total PnL: ${metrics['total_pnl']:.2f}",
                f"Sharpe Ratio: {metrics['sharpe_ratio']:.4f}",
                f"Max Drawdown: {metrics['max_drawdown']:.4f}",
                f"Win Rate: {metrics['win_rate']:.2%}",
                f"Trade Count: {int(metrics['trade_count'])}",
                "",
                "Baseline Comparisons:",
                f"  Naive Mean Reversion: ${report['baseline_naive_mean_reversion']['total_pnl']:.2f}",
                f"  Pure Momentum: ${report['baseline_pure_momentum']['total_pnl']:.2f}",
                "",
            ])

        # Walk-forward summary
        if self.reports["walk_forward"]:
            lines.extend([
                "2. WALK-FORWARD TESTING",
                "-" * 40,
                f"Number of Periods: {len(self.reports['walk_forward'])}",
            ])
            avg_pnl = sum(r["test_metrics"]["total_pnl"] for r in self.reports["walk_forward"]) / len(self.reports["walk_forward"])
            avg_sharpe = sum(r["test_metrics"]["sharpe_ratio"] for r in self.reports["walk_forward"]) / len(self.reports["walk_forward"])
            lines.extend([
                f"Average Test PnL: ${avg_pnl:.2f}",
                f"Average Sharpe Ratio: {avg_sharpe:.4f}",
                "",
            ])

        # Stress testing summary
        if self.reports["stress_testing"]:
            lines.extend([
                "3. STRESS TESTING",
                "-" * 40,
                f"Scenarios Run: {len(self.reports['stress_testing'])}",
            ])
            stable_count = sum(1 for r in self.reports["stress_testing"] if r.get("system_stable", True))
            lines.append(f"System Stability: {stable_count}/{len(self.reports['stress_testing'])} scenarios")
            lines.append("")
            for result in self.reports["stress_testing"]:
                metrics = result["metrics"]
                lines.append(
                    f"  {result['scenario']}: "
                    f"PnL=${metrics['total_pnl']:.2f}, "
                    f"Sharpe={metrics['sharpe_ratio']:.4f}"
                )
            lines.append("")

        # Live paper summary
        if self.reports["live_paper"]:
            report = self.reports["live_paper"][0]
            metrics = report["metrics"]
            lines.extend([
                "4. LIVE PAPER TRADING SIMULATION",
                "-" * 40,
                f"Duration: {report['duration_seconds']}s",
                f"Ticks Processed: {report['num_ticks']}",
                f"Signals Generated: {report['signals_generated']}",
                f"Trades Executed: {report['trades_executed']}",
                f"Trades Blocked (Risk): {report['trades_blocked']}",
                f"Total PnL: ${metrics['total_pnl']:.2f}",
                f"Sharpe Ratio: {metrics['sharpe_ratio']:.4f}",
                f"Max Drawdown: {metrics['max_drawdown']:.4f}",
                f"Win Rate: {metrics['win_rate']:.2%}",
                "",
            ])

        lines.extend([
            "=" * 80,
            "✓ All validation stages completed successfully",
            "=" * 80,
        ])

        return "\n".join(lines)

    def execute_full_pipeline(self) -> None:
        """Execute the complete validation pipeline."""
        print("\n" + "=" * 80)
        print("MINI QUANT SYSTEM - VALIDATION PIPELINE")
        print("=" * 80 + "\n")

        # Stage 1: Historical Backtesting
        print("STAGE 1: HISTORICAL BACKTESTING")
        self.run_historical_backtesting()

        # Stage 2: Walk-Forward Testing
        print("\nSTAGE 2: WALK-FORWARD TESTING")
        self.run_walk_forward_testing()

        # Stage 3: Stress Testing
        print("\nSTAGE 3: STRESS TESTING")
        self.run_stress_testing_suite()

        # Stage 4: Live Paper Trading
        print("\nSTAGE 4: LIVE PAPER TRADING SIMULATION")
        self.run_live_paper_trading_simulation(duration_seconds=100)

        # Save reports
        print("\nSAVING REPORTS...")
        self.save_reports_to_csv()
        self.save_reports_to_json()

        # Print summary
        print("\n" + self.generate_summary_report())


if __name__ == "__main__":
    pipeline = ValidationPipeline(output_dir="validation_reports")
    pipeline.execute_full_pipeline()
