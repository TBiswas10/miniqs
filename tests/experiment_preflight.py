"""Preflight runner before starting a frozen paper-trading experiment.

- Runs P0 gate
- Captures runtime config snapshot
- Emits immutable experiment manifest artifact
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from src.miniqs.config.alpaca import AlpacaConfig
from tests.p0_validation import run_p0_gate


def _git_sha() -> str:
    proc = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    if proc.returncode != 0:
        return "unknown"
    return proc.stdout.strip()


def _config_snapshot(cfg: AlpacaConfig) -> Dict[str, Any]:
    return {
        "symbols": cfg.symbols,
        "evaluation_profile": cfg.evaluation_profile,
        "confidence_threshold": cfg.confidence_threshold,
        "mr_threshold": cfg.mr_threshold,
        "mom_threshold": cfg.mom_threshold,
        "vb_breakout_factor": cfg.vb_breakout_factor,
        "max_position_size": cfg.max_position_size,
        "cooldown_seconds": cfg.cooldown_seconds,
        "max_loss_per_session": cfg.max_loss_per_session,
        "trade_size": cfg.trade_size,
    }


def main() -> int:
    p0 = run_p0_gate()
    if p0["status"] != "PASS":
        print("[preflight] blocked: P0 gate failed")
        for check in p0.get("checks", []):
            if not check.get("passed", False):
                print(f"[preflight] fail {check.get('name')}: {check.get('details', '')}")
        return 1

    config_path = Path(os.environ.get("ALPACA_CONFIG_FILE", "src.miniqs.config/alpaca_config.json"))
    cfg = AlpacaConfig.from_env()

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "config_path": str(config_path),
        "src.miniqs.config": _config_snapshot(cfg),
        "p0_gate": {
            "status": p0["status"],
            "checks": p0["checks"],
            "protocol": p0["protocol"],
        },
        "instructions": [
            "Do not change strategy/evaluator code during experiment window.",
            "Do not change config thresholds mid-run unless experiment is explicitly restarted.",
            "Archive this manifest with daily monitoring snapshots.",
        ],
    }

    out_dir = Path("validation_reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"experiment_manifest_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"[preflight] PASS manifest={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
