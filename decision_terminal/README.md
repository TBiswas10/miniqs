# Decision Intelligence Terminal

A Bloomberg-style terminal for bot cognition transparency, built with:
- FastAPI + WebSocket backend
- Next.js + Tailwind + shadcn-style components frontend
- Recharts for confidence, equity, and strategy trend visualizations

## Architecture

- Backend: `decision_terminal/backend/main.py`
  - `GET /api/decision/snapshot`
  - `GET /api/health`
  - `WS /ws/decisions`
  - Control APIs:
    - `POST /api/control/trading`
    - `POST /api/control/strategy`
    - `POST /api/control/risk`
    - `POST /api/control/kill-switch`
  - SQLite logging: `logs/decision_terminal.db`
- Frontend: `decision_terminal/frontend`
  - Consumes `decision` object directly
  - Panels:
    - Brain Panel
    - Why Not Trade
    - Thought Stream
    - Decision History
    - State Panel
    - Execution Tracker
    - System Control Panel
    - Strategy Intelligence Panel
    - Decision Inspector Panel
    - Counterfactual Engine Panel
    - Performance Analytics Panel
    - Replay System Panel
    - Alerts Banner System

## Run

## 1) Install Python deps (root project)
```powershell
c:/Users/tirth/Desktop/Coding/miniqs/.venv/Scripts/python.exe -m pip install -r requirements.txt
```

## 2) Start backend

```powershell
c:/Users/tirth/Desktop/Coding/miniqs/.venv/Scripts/python.exe -m uvicorn decision_terminal.backend.main:app --host 127.0.0.1 --port 8000 --reload
```

## 3) Start frontend

```powershell
cd decision_terminal/frontend
npm install
npm run dev
```

Open: `http://127.0.0.1:3000`

## Optional env overrides

Create `decision_terminal/frontend/.env.local`:

```bash
NEXT_PUBLIC_DECISION_API_BASE=http://127.0.0.1:8000
NEXT_PUBLIC_DECISION_WS_BASE=ws://127.0.0.1:8000/ws/decisions
```

## Feature coverage against requested spec

- Dark mode default with high-contrast terminal palette
- Existing layout preserved and upgraded:
  - Top row: Brain + Why Not Trade
  - Middle row: Thought Stream
  - Bottom row: Decision History + State + Execution Tracker
  - Added rows: Controls + Strategy Intelligence + Advanced Analysis Tabs
- Brain panel now includes strategy, confidence, timestamp, and signal trendline
- Why Not Trade now supports failed/executed filtering with pass/fail reasons per check
- Thought Stream supports log filters (errors / strategy events / blocked trades)
- Decision History supports click-to-inspect with extra columns: strategy and PnL
- State Panel now includes cash, positions, PnL, open orders, and PnL sparkline
- Execution tracker shows the pipeline with step status tooltips
- New panels: System Control, Strategy Intelligence, Decision Inspector,
  Counterfactual Engine, Performance Analytics, Replay System, Alerts
- Color coding:
  - BUY positive green
  - SELL negative red
  - BLOCKED orange
  - neutral blue
- Interactive controls: start/stop, strategy toggles, risk parameter updates, kill switch
- Control actions are now wired into the live runner loop (in-process effect):
  - `trading_enabled=false` stops order submission while keeping monitoring alive
  - `kill_switch=true` immediately halts trading logic
  - strategy toggles are synced to the app strategy registry (no hardcoded terminal-only list)
  - risk updates now expose the expanded app risk contract (including drawdown, exposure, volatility sizing, cooldown, and kill-switch thresholds)
- Debug toggle and history filters (all/executed/blocked)
- Tooltips for metrics and status context
- Smooth confidence bar transitions and table hover transitions
- Snapshot metadata now includes `meta.app_contract` with:
  - `strategy_registry`
  - `risk_parameters`
  - `missing_strategy_controls`

## Control API examples

```bash
curl -X POST http://127.0.0.1:8000/api/control/trading -H "Content-Type: application/json" -d "{\"enabled\": true}"
curl -X POST http://127.0.0.1:8000/api/control/strategy -H "Content-Type: application/json" -d "{\"strategy\": \"momentum\", \"enabled\": false}"
curl -X POST http://127.0.0.1:8000/api/control/risk -H "Content-Type: application/json" -d "{\"confidence_threshold\": 0.62, \"max_position_size\": 0.12}"
curl -X POST http://127.0.0.1:8000/api/control/risk -H "Content-Type: application/json" -d "{\"risk_per_trade\": 0.008, \"portfolio_drawdown_limit\": 0.1, \"vol_target\": 0.012, \"cooldown_seconds\": 8}"
curl -X POST http://127.0.0.1:8000/api/control/kill-switch -H "Content-Type: application/json" -d "{\"engage\": true}"
```

## Runner Wiring Notes

- Shared control state file: `logs/terminal_control_state.json`
- Backend control APIs persist updates to this file.
- `alpaca_paper_runner.py` reloads and applies this state every tick.

## Troubleshooting `_next/static` 404 in local dev

If you see errors like `GET /_next/static/css/app/layout.css 404`:

1. Stop any running Next server.
2. From `decision_terminal/frontend`, clear build cache:
  - PowerShell: `Remove-Item -Recurse -Force .next`
3. Start dev server again: `npm run dev`
4. Hard refresh browser (`Ctrl+F5`) to clear stale build-id asset references.

## Example screenshot descriptions

1. Hero / top row:
- Left panel shows `BUY` and `EXECUTE` in large green typography with a confidence progress bar at ~72%.
- Right panel checklist shows three green checks and one red cross for failed cooldown.

2. Thought stream center:
- Monospace scrolling log with timestamps in muted gray, warning lines in amber, and error lines in red.
- Operators can quickly scan stage-by-stage bot thought transitions.

3. Bottom row terminal operations:
- Left decision history table with color-coded action badges and hover-highlighted rows.
- Middle compact state cards for position, cash, and PnL with PnL turning green/red based on sign.
- Right execution tracker pipeline (`Signal -> Decision -> Sent -> Filled`) with status dots and confidence mini-chart.
