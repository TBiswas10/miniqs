"""Run comparable validation modes and emit reproducible JSON artifacts.

Modes:
1) historical backtest
2) event-driven simulation
3) strict-forward (walk-forward OOS aggregation)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backtest import run_backtest, run_walk_forward_backtest
from event_driven_pipeline import run_event_driven_paper_trading_session


DEFAULT_CONFIG: Dict[str, float] = {
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


@dataclass(frozen=True)
class AcceptanceThresholds:
    min_pnl: float = -2000.0
    max_drawdown: float = 0.25
    min_win_rate: float = 0.35
    min_trade_count: int = 3
    max_risk_block_rate: float = 0.85
    max_strategy_domination: float = 1.0
    strict_forward_min_trade_count: int = 2


@dataclass(frozen=True)
class FailFastConfig:
    forward_trade_drought_limit: int = -1
    max_strategy_domination: float = 1.0


class ValidationFailure(RuntimeError):
    pass


def _git_sha() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _generate_prices(base_price: float, num_ticks: int, trend: float, volatility: float, seed: int) -> List[float]:
    import random

    random.seed(seed)
    prices = [base_price]
    for _ in range(num_ticks - 1):
        change = random.gauss(trend, volatility)
        prices.append(max(1.0, prices[-1] * (1.0 + change)))
    return prices


def _domination_ratio(selection_counts: Dict[str, int]) -> float:
    total = sum(selection_counts.values())
    if total <= 0:
        return 0.0
    return max(selection_counts.values()) / total


def _check_fail_fast(run_type: str, selection_counts: Dict[str, int], trade_count: int, cfg: FailFastConfig) -> None:
    domination = _domination_ratio(selection_counts)
    if domination > cfg.max_strategy_domination:
        raise ValidationFailure(
            f"[{run_type}] fail-fast: strategy domination {domination:.2%} exceeded {cfg.max_strategy_domination:.2%}"
        )

    if run_type == "strict_forward" and trade_count <= cfg.forward_trade_drought_limit:
        raise ValidationFailure(
            f"[strict_forward] fail-fast: forward trade drought (trade_count={trade_count}, limit={cfg.forward_trade_drought_limit})"
        )


def _evaluate_acceptance(metrics: Dict[str, Any], thresholds: AcceptanceThresholds) -> Dict[str, Any]:
    failures: List[str] = []

    if float(metrics["pnl"]) < thresholds.min_pnl:
        failures.append(f"pnl {metrics['pnl']:.2f} < {thresholds.min_pnl:.2f}")
    if float(metrics["drawdown"]) > thresholds.max_drawdown:
        failures.append(f"drawdown {metrics['drawdown']:.4f} > {thresholds.max_drawdown:.4f}")
    if float(metrics["win_rate"]) < thresholds.min_win_rate:
        failures.append(f"win_rate {metrics['win_rate']:.4f} < {thresholds.min_win_rate:.4f}")
    if int(metrics["trade_count"]) < thresholds.min_trade_count:
        failures.append(f"trade_count {metrics['trade_count']} < {thresholds.min_trade_count}")
    if float(metrics["risk_block_rate"]) > thresholds.max_risk_block_rate:
        failures.append(
            f"risk_block_rate {metrics['risk_block_rate']:.4f} > {thresholds.max_risk_block_rate:.4f}"
        )

    domination = _domination_ratio(metrics["strategy_selection_counts"])
    if domination > thresholds.max_strategy_domination:
        failures.append(f"strategy domination {domination:.2%} > {thresholds.max_strategy_domination:.2%}")

    return {
        "passed": len(failures) == 0,
        "failures": failures,
        "strategy_domination": domination,
    }


def _build_artifact(
    run_type: str,
    metrics: Dict[str, Any],
    parameter_sheet: Dict[str, Any],
    git_sha: str,
    thresholds: AcceptanceThresholds,
) -> Dict[str, Any]:
    return {
        "run_type": run_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_sha": git_sha,
        "parameter_sheet": parameter_sheet,
        "metrics": metrics,
        "acceptance": _evaluate_acceptance(metrics, thresholds),
    }


def _run_backtest(config: Dict[str, float], prices: List[float], git_sha: str, thresholds: AcceptanceThresholds) -> Dict[str, Any]:
    result = run_backtest(prices, config=config)
    metrics = {
        "pnl": float(result["pipeline"]["total_pnl"]),
        "drawdown": float(result["pipeline"]["max_drawdown"]),
        "win_rate": float(result["pipeline"]["win_rate"]),
        "trade_count": int(result["pipeline"]["trade_count"]),
        "strategy_selection_counts": result.get("strategy_selection_counts", {}),
        "risk_block_rate": float(result.get("risk_block_rate", 0.0)),
    }
    params = {"mode": "backtest", "config": config, "num_ticks": len(prices)}
    return _build_artifact("backtest", metrics, params, git_sha, thresholds)


def _run_event_driven(num_ticks: int, seed: int, git_sha: str, thresholds: AcceptanceThresholds) -> Dict[str, Any]:
    result = run_event_driven_paper_trading_session(num_ticks=num_ticks, seed=seed)
    metrics = {
        "pnl": float(result["total_pnl"]),
        "drawdown": float(result["max_drawdown"]),
        "win_rate": float(result["win_rate"]),
        "trade_count": int(result.get("trade_count", result["executed_trades"])),
        "strategy_selection_counts": result.get("strategy_selection_counts", {}),
        "risk_block_rate": float(result.get("risk_block_rate", 0.0)),
    }
    params = {"mode": "event_driven", "num_ticks": num_ticks, "seed": seed}
    return _build_artifact("event_driven", metrics, params, git_sha, thresholds)


def _run_strict_forward(
    prices: List[float],
    config: Dict[str, float],
    window_size: int,
    step_size: int,
    git_sha: str,
    thresholds: AcceptanceThresholds,
) -> Dict[str, Any]:
    wf = run_walk_forward_backtest(prices, window_size=window_size, step_size=step_size, config=config)

    pnl = 0.0
    drawdown = 0.0
    wins_weighted = 0.0
    total_trades = 0
    selection_counts: Dict[str, int] = {}
    risk_checks = 0.0
    risk_blocks = 0.0

    for fold in wf["folds"]:
        out = fold["out_of_sample"]
        details = fold.get("out_of_sample_details", {})
        fold_trades = int(out.get("trade_count", 0.0))
        total_trades += fold_trades
        pnl += float(out.get("total_pnl", 0.0))
        drawdown = max(drawdown, float(out.get("max_drawdown", 0.0)))
        wins_weighted += float(out.get("win_rate", 0.0)) * fold_trades

        for strategy, count in details.get("strategy_selection_counts", {}).items():
            selection_counts[strategy] = selection_counts.get(strategy, 0) + int(count)

        risk_checks += float(details.get("risk_checks", 0.0))
        risk_blocks += float(details.get("risk_blocks", 0.0))

    win_rate = wins_weighted / total_trades if total_trades > 0 else 0.0
    metrics = {
        "pnl": pnl,
        "drawdown": drawdown,
        "win_rate": win_rate,
        "trade_count": total_trades,
        "strategy_selection_counts": selection_counts,
        "risk_block_rate": (risk_blocks / risk_checks) if risk_checks > 0 else 0.0,
    }

    params = {
        "mode": "strict_forward",
        "config": config,
        "window_size": window_size,
        "step_size": step_size,
        "num_ticks": len(prices),
        "num_folds": wf["num_folds"],
    }
    artifact = _build_artifact("strict_forward", metrics, params, git_sha, thresholds)
    artifact["folds"] = wf["folds"]
    return artifact


def _save_json(output_dir: Path, artifact: Dict[str, Any]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = output_dir / f"{artifact['run_type']}_{stamp}.json"
    path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Execute miniqs validation pipeline.")
    parser.add_argument("--output-dir", default="validation_reports", help="Artifact output directory")
    parser.add_argument("--price-ticks", type=int, default=500)
    parser.add_argument("--event-ticks", type=int, default=240)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--window-size", type=int, default=100)
    parser.add_argument("--step-size", type=int, default=50)
    parser.add_argument("--max-strategy-domination", type=float, default=1.0)
    parser.add_argument("--forward-drought-limit", type=int, default=-1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    prices = _generate_prices(
        base_price=100.0,
        num_ticks=args.price_ticks,
        trend=0.0001,
        volatility=0.005,
        seed=args.seed,
    )
    cfg = dict(DEFAULT_CONFIG)
    git_sha = _git_sha()

    thresholds = AcceptanceThresholds(max_strategy_domination=args.max_strategy_domination)
    fail_fast = FailFastConfig(
        forward_trade_drought_limit=args.forward_drought_limit,
        max_strategy_domination=args.max_strategy_domination,
    )

    output_dir = Path(args.output_dir)
    artifacts: List[Path] = []

    backtest = _run_backtest(cfg, prices, git_sha, thresholds)
    _check_fail_fast("backtest", backtest["metrics"]["strategy_selection_counts"], backtest["metrics"]["trade_count"], fail_fast)
    artifacts.append(_save_json(output_dir, backtest))

    event_driven = _run_event_driven(args.event_ticks, args.seed, git_sha, thresholds)
    _check_fail_fast(
        "event_driven",
        event_driven["metrics"]["strategy_selection_counts"],
        event_driven["metrics"]["trade_count"],
        fail_fast,
    )
    artifacts.append(_save_json(output_dir, event_driven))

    strict_forward = _run_strict_forward(
        prices=prices,
        config=cfg,
        window_size=args.window_size,
        step_size=args.step_size,
        git_sha=git_sha,
        thresholds=thresholds,
    )
    _check_fail_fast(
        "strict_forward",
        strict_forward["metrics"]["strategy_selection_counts"],
        strict_forward["metrics"]["trade_count"],
        fail_fast,
    )
    artifacts.append(_save_json(output_dir, strict_forward))

    summary_path = output_dir / "validation_summary.json"
    summary_path.write_text(
        json.dumps({"artifacts": [str(p) for p in artifacts], "git_sha": git_sha}, indent=2), encoding="utf-8"
    )
    print(f"Validation artifacts written: {[str(p) for p in artifacts]}")
    print(f"Summary written: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
