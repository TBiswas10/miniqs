# MiniQS: Quant Control and Analysis Stack

MiniQS is a modular quant research and paper-trading project with three integrated layers:

- Core strategy pipeline for simulation, backtesting, and stress validation
- Alpaca paper-trading runner for live market data and paper execution
- Decision Intelligence Terminal for real-time monitoring, diagnostics, and control

It is built for iterative strategy development: design, validate, observe, and tune before using real capital.

## What You Get

- Event-driven signal pipeline via central bus: market -> signal -> risk -> order -> fill
- Baseline strategies: mean reversion, momentum, and volatility breakout
- Common strategy interface + hot-swappable strategy registry
- Historical backtesting and conservative parameter optimization
- Stress testing under volatility, spikes, downtrends, and liquidity shocks
- DataFeed supports both simulated ticks and live Binance mid-price streaming
- Live Alpaca paper runner with detailed brain-trace and execution logs
- Centralized configuration from JSON/YAML with optional environment overrides
- Structured JSON event logging for replay/reconstruction of live and backtest runs
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
- `alpaca_config.py`: centralized Alpaca config loader (JSON/YAML + env override)
- `config/alpaca_config.json`: default centralized runtime config
- `quant_control_state.py`: persisted shared control state
- `decision_terminal/backend/main.py`: FastAPI backend + websocket stream + control APIs
- `decision_terminal/frontend/`: Next.js frontend terminal
- `event_bus.py`: shared in-memory event types, queue, and dispatcher
- `risk_manager.py`: combined per-trade + portfolio-level risk gatekeeper
- `logger.py`: SQLite + JSONL structured event logger
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

### 3.1) Configure project behavior from centralized config

Edit:

- `config/alpaca_config.json`

You can tune market-data, strategy, risk, and execution settings here without code edits.

Optional override:

```powershell
$env:ALPACA_CONFIG_FILE="config/alpaca_config.json"
```

Supported file types for `ALPACA_CONFIG_FILE`:

- `.json`
- `.yaml` or `.yml` (requires `PyYAML`)

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

Set credentials in that same shell (or place them in config file):

```powershell
$env:ALPACA_API_KEY_ID="your_paper_key"
$env:ALPACA_API_SECRET_KEY="your_paper_secret"
```

Or load them from `.env` via the existing config loader.

Optional:

```powershell
$env:ALPACA_SYMBOLS="SPY"
$env:ALPACA_MAX_TICKS="500"
$env:ALPACA_CONFIG_FILE="config/alpaca_config.json"
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
- `http://127.0.0.1:8000/health`

## Core Workflows

### Simulated session

```powershell
python main.py
```

### Event-driven async session

```powershell
python event_driven_pipeline.py
```

Event-driven flow is implemented as decoupled async workers connected by queues:

- market data ingestion
- strategy evaluation
- risk check
- execution

This prevents a slow stage from blocking the full trading loop.

### Live and backtest architecture parity

`main.py`, `alpaca_paper_runner.py`, and `backtest.py` all follow event-driven dispatch flow:

- MarketEvent -> SignalEvent -> Risk gate -> OrderEvent -> FillEvent

This keeps risk/execution semantics consistent across simulation, backtest, and live paper mode.

### Strategy interface and hot-swapping

All strategies follow a common interface and are run via a strategy registry.

- Built-ins: mean reversion, momentum, volatility breakout
- Strategies are weighted by iteration/feedback engine outputs
- You can hot-swap a strategy implementation in the registry without changing pipeline logic

### Risk controls now combined in one gate

The risk manager combines per-trade and portfolio-level checks before execution:

- confidence threshold
- risk per trade
- max exposure
- max concurrent positions
- cooldown
- max position size
- daily loss limit / kill switch
- drawdown limits

### Realistic execution simulation

Backtests and simulated paper sessions now use an order-state machine and realistic fill model.

Order state path supports:

- created -> submitted -> acknowledged -> partial -> filled
- created -> submitted -> acknowledged -> partial -> canceled
- created -> submitted -> acknowledged -> rejected

Execution realism includes:

- spread crossing
- slippage
- size-based market impact
- partial fills and remainder cancellation
- transaction fees via portfolio accounting

Backtest fills additionally include realistic simulated latency and slippage:

- latency: 50-200ms per order
- slippage/impact applied to fill price

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

Risk limits include:

- `confidence_threshold`
- `max_position_size`
- `max_daily_loss`
- `risk_per_trade`
- `daily_loss_limit`
- `max_exposure`
- `max_concurrent_positions`
- `cooldown_seconds`
- `max_loss_per_session`
- `portfolio_drawdown_limit`
- `per_strategy_drawdown_limit`
- `extreme_loss_kill_switch`
- `strategy_kill_loss`
- `vol_target`
- `vol_floor`
- `vol_ceiling`
- `low_vol_multiplier`
- `high_vol_multiplier`
- `min_trade_size`
- `max_trade_size`

Shared state file:

- `logs/terminal_control_state.json`

This keeps responsibilities clean:

- Frontend = presentation and operator controls
- Backend = API, stream, control persistence
- Runner = strategy/risk/execution engine that applies controls each tick

## API Surface

Read endpoints:

- `GET /api/health`
- `GET /health`
- `GET /api/decision/snapshot`
- `WS /ws/decisions`

`/ws/decisions` is event-driven (pushes on event bus updates), not fixed-interval polling.

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

## Logging and Replay

The logger writes two synchronized formats:

- SQLite tables (`signals`, `trades`, `risk_blocks`, snapshots, etc.)
- Structured JSON event stream (`*.events.jsonl`) with run id + sequence

These logs are sufficient to reconstruct timeline behavior for backtests and live paper sessions.
