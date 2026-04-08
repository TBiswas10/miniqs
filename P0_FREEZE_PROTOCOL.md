# P0 Freeze Protocol

Purpose: lock strategy/evaluator logic for a fixed validation window and only
promote changes when deterministic gates pass.

## Required command

```bash
python p0_validation.py
```

## What this enforces

- fixed deterministic simulation windows:
  - `run_paper_trading_session(num_ticks=180, seed=21)`
  - `run_event_driven_paper_trading_session(num_ticks=120, seed=11)`
- core pytest suite must pass:
  - `tests/test_strategy_evaluator.py`
  - `tests/test_event_driven_pipeline.py`
  - `tests/test_integration_pipeline.py`
  - `tests/test_runner_control_state.py`

## Gate rules

- all required tests pass
- executed trades >= 1 for both fixed simulation runs
- max drawdown <= 5%
- strategy weights sum to 1.0

## Output

- JSON artifact in `validation_reports/p0_gate_*.json`
- includes timestamp, git SHA, pass/fail status, individual check details
