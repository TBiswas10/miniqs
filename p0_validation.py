"""P0 gate for strategy/evaluator freeze validation.

This script enforces a fixed validation protocol before promoting strategy logic
changes. It uses deterministic seeds and fixed tick windows to keep comparisons
stable across branches.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from event_driven_pipeline import run_event_driven_paper_trading_session
from main import run_paper_trading_session


@dataclass
class GateResult:
    name: str
    passed: bool
    details: str


def _run_pytest_gate() -> GateResult:
    cmd = [
        "pytest",
        "-q",
        "tests/test_strategy_evaluator.py",
        "tests/test_event_driven_pipeline.py",
        "tests/test_integration_pipeline.py",
        "tests/test_runner_control_state.py",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    passed = proc.returncode == 0
    output = (proc.stdout + "\n" + proc.stderr).strip()
    summary = output.splitlines()[-1] if output else "no output"
    return GateResult(name="pytest_core_suite", passed=passed, details=summary)


def _check_summary(name: str, summary: Dict[str, float]) -> List[GateResult]:
    checks: List[GateResult] = []

    checks.append(
        GateResult(
            name=f"{name}.has_executed_trades",
            passed=float(summary.get("executed_trades", 0.0)) >= 1.0,
            details=f"executed_trades={summary.get('executed_trades', 0.0)}",
        )
    )
    checks.append(
        GateResult(
            name=f"{name}.drawdown_guard",
            passed=float(summary.get("max_drawdown", 1.0)) <= 0.05,
            details=f"max_drawdown={summary.get('max_drawdown', 1.0)}",
        )
    )
    strategy_weights = summary.get("strategy_weights", {})
    if isinstance(strategy_weights, dict):
        w_sum = (
            float(strategy_weights.get("mean_reversion", 0.0))
            + float(strategy_weights.get("momentum", 0.0))
            + float(strategy_weights.get("volatility_breakout", 0.0))
        )
    else:
        # Backward compatibility for legacy summary shape.
        w_sum = (
            float(summary.get("mean_reversion_weight", 0.0))
            + float(summary.get("momentum_weight", 0.0))
            + float(summary.get("volatility_breakout_weight", 0.0))
        )
    checks.append(
        GateResult(
            name=f"{name}.weight_sum",
            passed=abs(w_sum - 1.0) <= 1e-6,
            details=f"weight_sum={w_sum:.8f}",
        )
    )

    return checks


def _git_sha() -> str:
    proc = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    if proc.returncode != 0:
        return "unknown"
    return proc.stdout.strip()


def run_p0_gate() -> Dict[str, object]:
    validation_runs = {
        "main_sim": run_paper_trading_session(num_ticks=180, seed=21),
        "event_driven": run_event_driven_paper_trading_session(num_ticks=120, seed=11),
    }

    checks: List[GateResult] = [_run_pytest_gate()]
    checks.extend(_check_summary("main_sim", validation_runs["main_sim"]))
    checks.extend(_check_summary("event_driven", validation_runs["event_driven"]))

    passed = all(c.passed for c in checks)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "status": "PASS" if passed else "FAIL",
        "checks": [asdict(c) for c in checks],
        "runs": validation_runs,
        "protocol": {
            "main_sim": {"num_ticks": 180, "seed": 21},
            "event_driven": {"num_ticks": 120, "seed": 11},
            "required_tests": [
                "tests/test_strategy_evaluator.py",
                "tests/test_event_driven_pipeline.py",
                "tests/test_integration_pipeline.py",
                "tests/test_runner_control_state.py",
            ],
        },
    }
    return report


def main() -> int:
    report = run_p0_gate()
    out_dir = Path("validation_reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"p0_gate_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"[p0_gate] status={report['status']} report={path}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
