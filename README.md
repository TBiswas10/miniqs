# MiniQS: Quant Control and Analysis Stack

MiniQS is a modular quant research and paper-trading project with three integrated layers:

- Core strategy pipeline for simulation, backtesting, and stress validation
- Alpaca paper-trading runner for live market data and paper execution
- Decision Intelligence Terminal for real-time monitoring, diagnostics, and control

It is built for iterative strategy development: design, validate, observe, and tune before using real capital.

## What You Get

- Feature-driven signal pipeline: features -> strategies -> evaluator -> risk -> execution -> portfolio
- Baseline strategies: mean reversion and momentum
- Historical backtesting and conservative parameter optimization
- Stress testing under volatility, spikes, downtrends, and liquidity shocks
- Live Alpaca paper runner with detailed brain-trace and execution logs
- Real-time terminal with:
  - decision stream and reasoning
  - risk gate visibility and why-not-trade diagnostics
  - execution and portfolio state monitoring
  - replay and recent alerts
  - control actions (start/stop, kill switch, strategy toggles, risk thresholds)

## Repository Structure

- `main.py`: simulated paper-session pipeline entrypoint
- `backtest.py`: historical backtest + parameter optimization
- `stress_testing.py`: stress scenario generation and stress runner
- `execute_validation_pipeline.py`: end-to-end validation reporting pipeline
- `alpaca_paper_runner.py`: live paper trading runner (Alpaca)
- `alpaca_config.py`: Alpaca config and environment parsing
- `quant_control_state.py`: persisted shared control state
- `decision_terminal/backend/main.py`: FastAPI backend + websocket stream + control APIs
- `decision_terminal/frontend/`: Next.js frontend terminal
- `tests/`: unit and integration tests
- `validation_reports/`: generated validation outputs

## Prerequisites

- Windows PowerShell
- Python 3.11+
- Node.js 18+
- npm 9+

## Installation

### 1) Create and activate Python environment

```powershell
cd C:/Users/tirth/Desktop/Coding/miniqs
python -m venv .venv
.venv/Scripts/Activate.ps1
```

### 2) Install Python dependencies

```powershell
python -m pip install -r requirements.txt
```

### 3) Create local environment file

```powershell
Copy-Item .env.example .env
```

Then fill in your Alpaca paper credentials in `.env`.

### 4) Install frontend dependencies

```powershell
cd decision_terminal/frontend
npm install
cd ../../
```

## Run The Full Stack

Start from the project root in three terminals. Activate `.venv` in each terminal.

### Terminal A: Decision backend

```powershell
python -m uvicorn decision_terminal.backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### Terminal B: Alpaca paper runner

Set credentials in that same shell:

```powershell
$env:ALPACA_API_KEY_ID="your_paper_key"
$env:ALPACA_API_SECRET_KEY="your_paper_secret"
```

Or load them from `.env` via the existing config loader.

Optional:

```powershell
$env:ALPACA_SYMBOLS="SPY"
$env:ALPACA_MAX_TICKS="500"
```

Run:

```powershell
python alpaca_paper_runner.py
```

### Terminal C: Frontend terminal

```powershell
cd decision_terminal/frontend
if (Test-Path .next) { Remove-Item -Recurse -Force .next }
npm run dev
```

Open the exact URL printed by Next.js (commonly `http://localhost:3000`, or `3001` if `3000` is busy).

Health endpoint:

- `http://127.0.0.1:8000/api/health`

## Core Workflows

### Simulated session

```powershell
python main.py
```

### Backtest quick example

```powershell
python -c "from backtest import run_backtest; print(run_backtest([100,101,99,102,103,101]))"
```

### Stress tests

```powershell
python stress_testing.py
```

### Full validation pipeline

```powershell
python execute_validation_pipeline.py
```

Outputs are generated in `validation_reports/`.

## Tests

Run all tests:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Run one test module:

```powershell
python -m unittest tests.test_integration_pipeline -v
```

## Control-State Wiring

Live control actions from the terminal are persisted and consumed by the runner loop.

Behavior that updates in-process:

- Trading on/off
- Kill switch
- Strategy enable/disable
- Confidence threshold and risk limits

Shared state file:

- `logs/terminal_control_state.json`

This keeps responsibilities clean:

- Frontend = presentation and operator controls
- Backend = API, stream, control persistence
- Runner = strategy/risk/execution engine that applies controls each tick

## API Surface

Read endpoints:

- `GET /api/health`
- `GET /api/decision/snapshot`
- `WS /ws/decisions`

Control endpoints:

- `POST /api/control/trading`
- `POST /api/control/strategy`
- `POST /api/control/risk`
- `POST /api/control/kill-switch`

## Troubleshooting

### Frontend static asset 404 or missing CSS/chunks

Usually stale Next build artifacts or wrong localhost port.

```powershell
cd decision_terminal/frontend
if (Test-Path .next) { Remove-Item -Recurse -Force .next }
npm run dev
```

Then hard refresh browser and use the exact URL shown in terminal.

### Hydration mismatch warnings

1. Stop frontend dev server
2. Remove `.next`
3. Restart `npm run dev`
4. Hard refresh browser

### Alpaca auth errors

Confirm these environment variables are set in the same shell running the runner:

- `ALPACA_API_KEY_ID`
- `ALPACA_API_SECRET_KEY`

### UI connected but no decision data

Check:

1. Runner process is active
2. `logs/alpaca_brain_trace.jsonl` is being updated
3. Backend is running on `127.0.0.1:8000`

## Additional Documentation

- `decision_terminal/README.md`
- `SYSTEM_ARCHITECTURE.md`
- `VALIDATION_REPORT.md`
- `COMPLETION_SUMMARY.md`
