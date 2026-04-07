# 🚀 Mini Quant System – A Modular Algorithmic Trading Framework

A **solo-developer-friendly**, fully modular mini quant system for paper trading, backtesting, and performance analytics. This system demonstrates professional quant engineering practices: modular design, risk management, feedback loops, and comprehensive logging.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [System Architecture](#system-architecture)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Running the System](#running-the-system)
- [Module Descriptions](#module-descriptions)
- [Configuration Guide](#configuration-guide)
- [Performance Metrics Explained](#performance-metrics-explained)
- [Backtesting & Optimization](#backtesting--optimization)
- [Stress Testing](#stress-testing)
- [Alpaca Paper Trading](#alpaca-paper-trading)
- [Paper Trading & Feedback Loops](#paper-trading--feedback-loops)
- [Logs & Debugging](#logs--debugging)
- [Scaling to Real Capital](#scaling-to-real-capital)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

---

## Overview

This mini quant system is a **production-ready framework** for:

- **Live paper trading** with simulated ticks or live Binance WebSocket feeds
- **Backtesting** on historical price data with parameter optimization
- **Stress testing** with market shocks (spikes, volatility, downtrends, illiquidity)
- **Feedback-driven adaptation** where strategy weights adjust based on performance
- **Comprehensive logging** for post-session analysis and audit trails

### Key Principles

✅ **Safety First**: Paper-only by default; no real capital enabled without explicit safeguards
✅ **Modularity**: Each component (data feed, features, strategies, risk) is isolated and testable
✅ **Transparency**: All trades, signals, and portfolio snapshots logged to SQLite for inspection
✅ **Solo-Developer Friendly**: Clear documentation, examples, and error handling throughout
✅ **Scalable**: Architecture supports adding new strategies, features, and risk rules incrementally

---

## Features


| Feature                    | Description                                                      |
| -------------------------- | ---------------------------------------------------------------- |
| **Live & Simulated Data**  | Connect to Binance WebSocket or use synthetic price ticks        |
| **Feature Engineering**    | Rolling averages (20/50-period), volatility, momentum            |
| **Multi-Strategy**         | Mean reversion and momentum strategies with confidence scoring   |
| **Risk Management**        | Max position size, trade cooldown, daily loss limits             |
| **Paper Trading**          | Execute trades in paper mode with full portfolio tracking        |
| **Performance Analytics**  | Win rate, Sharpe ratio, max drawdown, avg trade PnL              |
| **Backtesting**            | Full pipeline replay on historical prices                        |
| **Parameter Optimization** | Conservative parameter sweep (±5% bounds) to avoid overfitting   |
| **Stress Testing**         | 8+ scenarios: spikes, volatility, downtrends, liquidity shocks   |
| **Feedback Loops**         | Automatic strategy weight adaptation based on recent performance |
| **SQLite Persistence**     | All signals, trades, and metrics persisted for analysis          |


---

## System Architecture

```
Data Feed (Ticks) 
       ↓
Feature Engine (Rolling Windows)
       ↓
Strategies (Mean Reversion + Momentum)
       ↓
Strategy Evaluator (Confidence-Based Selection)
       ↓
Risk Manager (Validation Gates)
       ↓
Execution Engine → Portfolio (PnL Tracking)
       ↓
Logger (SQLite Persistence)
       ↓
Performance Tracker (Metrics)
       ↓
Feedback Loop (Weight Adaptation)
```

**Data Flow**: Market ticks → features → signals → best signal selection → risk validation → paper trade execution → logging → metrics → feedback

### 📐 Visual Blueprints

For detailed architecture diagrams (Mermaid), data flow charts, module interfaces, risk gates, and testing coverage, see [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md).

---

## Quick Start

### 1. Clone or Set Up the Repository

```bash
cd c:/Users/tirth/Desktop/Coding/miniqs
python -m venv .venv
.venv/Scripts/Activate.ps1   # Windows PowerShell
source .venv/bin/activate     # Unix/Linux/Mac
pip install pandas numpy
```

### 2. Run a Paper Trading Simulation (100 ticks)

```bash
python -m unittest tests.test_feedback_loop.TestFeedbackLoop.test_feedback_simulation -v
```

### 3. Run Full Integration Test (180 ticks with feedback loop)

```bash
python -m unittest tests.test_integration_pipeline -v
```

### 4. Run Stress Suite (8 scenarios)

```bash
python stress_testing.py
```

### 5. Backtest on Synthetic Historical Data

```bash
python -c "from main import run_backtest_demo; run_backtest_demo()"
```

---

## Installation

### Requirements

- **Python**: 3.9+
- **Core**: pandas, numpy, sqlite3 (stdlib)
- **Optional**: websockets (for live Binance feed)

### Step 1: Create Virtual Environment

```bash
cd /path/to/miniqs
python -m venv .venv
```

### Step 2: Activate Environment

**Windows (PowerShell)**:

```powershell
.venv\Scripts\Activate.ps1
```

**Windows (CMD)**:

```cmd
.venv\Scripts\activate.bat
```

**Unix/Linux/macOS**:

```bash
source .venv/bin/activate
```

### Step 3: Install Dependencies

```bash
pip install pandas numpy
```

### Step 4: Optional – Install Live Feed Support

```bash
pip install websockets   # For live Binance tickertape
```

---

## Running the System

### A. Simulated Paper Trading (Default Mode)

*Generates synthetic random-walk price ticks and executes the full pipeline.*

```python
from main import run_paper_trading_session

result = run_paper_trading_session(num_ticks=200, seed=42)

print(f"Executed Trades: {result['executed_trades']}")
print(f"Total PnL: ${result['total_pnl']:.2f}")
print(f"Win Rate: {result['win_rate']:.2%}")
print(f"Max Drawdown: ${result['max_drawdown']:.2f}")
print(f"Sharpe Ratio: {result['sharpe_ratio']:.3f}")
```

**Output**:

```
Executed Trades: 12
Total PnL: $487.34
Win Rate: 58.3%
Max Drawdown: $120.50
Sharpe Ratio: 1.245
```

### B. Backtest on Historical Data

*Replay the full pipeline on a series of historical prices.*

```python
from backtest import run_backtest

prices = [100.0, 101.5, 102.2, 101.8, 103.5, ...]  # Historical price series
result = run_backtest(prices)

print("Pipeline Results:")
print(result['pipeline'])

print("\nBaseline Comparisons:")
print(f"Naive Mean Reversion: {result['baseline_naive_mean_reversion']['total_pnl']:.2f}")
print(f"Pure Momentum: {result['baseline_pure_momentum']['total_pnl']:.2f}")
```

### C. Parameter Optimization

*Run a conservative parameter sweep to find better thresholds.*

```python
from backtest import optimize_parameters

prices = [100.0, 101.5, 102.2, ...]
base_config = {
    "mr_threshold": 0.003,
    "mom_threshold": 0.002,
    "confidence_threshold": 0.6,
}

opt_result = optimize_parameters(prices, base_config)

best_config = opt_result['best_config']
best_pnl = opt_result['results'][0]['pipeline']['total_pnl']

print(f"Best Config: {best_config}")
print(f"Best PnL: ${best_pnl:.2f}")
```

### D. Stress Testing

*Simulate market shocks and verify risk manager enforcement.*

```bash
python stress_testing.py
```

**Scenarios**:

1. **Spike Up (5%)** – Sudden gap up
2. **Spike Down (10%)** – Sudden gap down
3. **High Volatility (2x)** – Elevated market swings
4. **Extreme Volatility (3x)** – Flash crash regime
5. **Downtrend (20%)** – Slow grinding loss
6. **Severe Downtrend (40%)** – Bear market
7. **Low Liquidity (2%)** – Wide bid-ask spreads
8. **Extreme Low Liquidity (5%)** – Illiquid asset

**Output**:

```
STRESS TEST SUITE RESULTS
================================================================================

spike_5pct:
  System Stable: True
  Risk Blocks: 3
  Total PnL: $-125.34
  Win Rate: 40%
  Max Drawdown: $450.00
  Sharpe Ratio: -0.123

...
```

### E. Live Paper Trading (Binance WebSocket)

*Optional: Connect to live Binance mid-prices (paper-observation only).*

```python
from data_feed import live_binance_midprice_stream
import asyncio

async def live_paper_trade():
    async for tick in live_binance_midprice_stream(symbol="btcusdt", max_messages=1000):
        # tick = {"timestamp": "2025-04-07T...", "mid_price": 45234.50}
        # Integrate with main pipeline...
        pass

await live_paper_trade()
```

**Note**: This stream is for **observation only**. No real orders are executed. The system remains in paper mode.

---

## Module Descriptions

### 1. **data_feed.py** – Market Data Ingestion

**Purpose**: Provide streaming price ticks {timestamp, mid_price, volume}.

**Functions**:

- `DataFeed.start_feed(tick_count)` → List[Tick] – Generate simulated ticks
- `DataFeed.get_latest_tick()` → Tick – Get current market price
- `DataFeed.stop_feed()` → None – Gracefully close feed
- `live_binance_midprice_stream(symbol, max_messages)` ↦ AsyncIterator – Optional live Binance feed

**Config**:

```python
feed = DataFeed(symbol="BTCUSDT", mode="simulated")
ticks = feed.start_feed(tick_count=200)
```

### 2. **feature_engine.py** – Feature Extraction

**Purpose**: Compute rolling features from price ticks.

**Outputs**:

- `rolling_avg_20`: 20-period moving average
- `rolling_avg_50`: 50-period moving average
- `volatility`: High – Low over vol_window
- `momentum`: % change over momentum_window

**Functions**:

- `FeatureEngine.update(tick)` → FeatureSnapshot | None – Compute features
- `FeatureEngine.get_latest_features()` → FeatureSnapshot | None – Get last features

**Example**:

```python
features = FeatureEngine(ma_window=20, long_ma_window=50, vol_window=20)
snap = features.update(tick)
if snap:
    print(f"20-MA: {snap.rolling_avg_20}, Vol: {snap.volatility}")
```

### 3. **strategies/** – Signal Generation

**Purpose**: Generate buy/sell signals with confidence scores.

#### **mean_reversion.py**

```python
from strategies.mean_reversion import generate_signal

signal = generate_signal(features, entry_threshold=0.003)
# Returns: StrategySignal(strategy="mean_reversion", action="buy"/"sell"/"hold", confidence=0.78, reason="...")
```

**Logic**: Buy when price >> rolling average; sell when price << rolling average.

#### **momentum.py**

```python
from strategies.momentum import generate_signal

signal = generate_signal(features, momentum_threshold=0.002)
# Returns: StrategySignal(strategy="momentum", action="buy"/"sell"/"hold", confidence=0.65, reason="...")
```

**Logic**: Buy when momentum > threshold; sell when momentum < -threshold.

### 4. **strategy_evaluator.py** – Multi-Strategy Selection

**Purpose**: Choose the single best signal from multiple strategies.

**Function**:

```python
from strategy_evaluator import evaluate_signals

signals = [mr_signal, mo_signal]
best_signal = evaluate_signals(signals, confidence_threshold=0.6)
# Returns: StrategySignal | None
```

**Logic**: Filters out low-confidence signals, returns highest-confidence buy/sell.

### 5. **risk_manager.py** – Pre-Trade Validation

**Purpose**: Enforce position, cooldown, and loss limits.

**Function**:

```python
from risk_manager import check_risk

allow, reason = check_risk(trade, portfolio_state)
# (True, "allowed") or (False, "blocked: max position size exceeded")
```

**Rules**:

1. **Max Position Size**: Prevents position from exceeding max limit (e.g., 5.0 units)
2. **Cooldown**: Blocks rapid-fire trades (e.g., min 5 seconds between trades)
3. **Max Session Loss**: Stops trading if cumulative loss exceeds daily limit (e.g., -$500)

### 6. **execution.py & portfolio.py** – Trade Execution & Portfolio Tracking

**Purpose**: Execute paper trades, track position, PnL, and persist to SQLite.

**ExecutionEngine**:

```python
execution = ExecutionEngine(portfolio=portfolio, paper_mode=True)
result = execution.execute_trade(trade)
# Returns: {realized_pnl_trade, total_pnl, position_size, ...}
```

**Portfolio**:

```python
portfolio = Portfolio(initial_cash=100000.0)
state = portfolio.get_portfolio_state()
# Returns: {cash, position_size, avg_entry_price, equity, total_pnl, ...}
```

**Database**:
SQLite table `trades`:

- id, timestamp, action (buy/sell), size, price, fee, realized_pnl

### 7. **logger.py** – Comprehensive Logging

**Purpose**: Persist all pipeline artifacts (signals, trades, portfolio snapshots, metrics).

**Functions**:

```python
logger = QuantLogger(db_path="portfolio.db")
logger.log_signal(signal)
logger.log_trade(trade, execution_result)
logger.log_portfolio_snapshot(portfolio_state)
logger.log_performance_metrics(metrics)
```

**SQLite Tables**:

- `signals`: {id, timestamp, strategy, action, confidence, reason}
- `trades`: {id, timestamp, action, size, price, fee, realized_pnl}
- `portfolio_snapshots`: {id, timestamp, cash, position_size, equity, total_pnl}
- `performance_metrics`: {id, timestamp, total_pnl, win_rate, max_drawdown, sharpe_ratio}

### 8. **performance.py** – Metrics Computation

**Purpose**: Calculate portfolio and per-strategy performance metrics.

**Function**:

```python
perf = PerformanceTracker(initial_equity=100000.0)
perf.record_trade(pnl)
perf.record_equity(40000.0)
metrics = perf.compute_metrics(latest_total_pnl=1250.0)
```

**Metrics**:

```python
{
    "total_pnl": 1250.0,
    "win_rate": 0.583,
    "avg_trade_pnl": 104.17,
    "max_drawdown": 450.0,
    "sharpe_ratio": 1.245,
    "trade_count": 12
}
```

### 9. **backtest.py** – Historical Backtesting

**Purpose**: Replay full pipeline on historical prices with baseline comparisons.

**Functions**:

```python
result = run_backtest(prices, config={...})
# Returns: {"pipeline": {...}, "baseline_naive_mean_reversion": {...}, "baseline_pure_momentum": {...}}

opt = optimize_parameters(prices, base_config)
# Returns: {"best_config": {...}, "results": [(...), ...]}
```

### 10. **main.py** – Feedback Loop & Orchestration

**Purpose**: Integrate all modules; adjust strategy weights based on recent performance.

**Classes**:

```python
class FeedbackLoop:
    def update(self, metrics: Dict[str, float]) -> Dict[str, float]:
        # Conservative weight adjustment (learning_rate=0.02, max_delta=0.01)
        return {"mean_reversion": 0.51, "momentum": 0.49}

def run_paper_trading_session(num_ticks: int, seed: int = None) -> Dict:
    # Full end-to-end orchestration with in-session feedback
    pass
```

**Behavior**: Every 10 trades, feedback loop adjusts strategy weights by up to ±1% per step.

### 11. **stress_testing.py** – Market Shock Simulation

**Purpose**: Test system resilience against market anomalies.

**Scenarios**:

- Price spikes (gaps)
- Elevated volatility
- Downtrends
- Low liquidity

**Function**:

```python
results = run_stress_suite(config={...})
# Returns: {scenario_name: {system_stable, risk_blocks, metrics, ...}, ...}
```

---

## Configuration Guide

### Default Configuration

```python
config = {
    # Data Feed
    "symbol": "BTCUSDT",
    
    # Feature Engineering
    "ma_window": 20,
    "long_ma_window": 50,
    "vol_window": 20,
    "momentum_window": 10,
    
    # Strategy Thresholds
    "mr_threshold": 0.003,          # Mean reversion entry threshold (0.3%)
    "mom_threshold": 0.002,         # Momentum entry threshold (0.2%)
    "confidence_threshold": 0.6,    # Min confidence to execute
    
    # Risk Management
    "max_position_size": 5.0,       # Max units to hold
    "cooldown_seconds": 5,          # Seconds between trades
    "max_loss_per_session": 500.0,  # Max daily loss in $
    
    # Portfolio
    "initial_cash": 100000.0,
    "trade_size": 1.0,              # Units per trade
    "fee_rate": 0.001,              # 0.1% per trade
    
    # Feedback Loop
    "feedback_learning_rate": 0.02, # Conservative weight adjustment
    "feedback_freq": 10,            # Update weights every N trades
}
```

### Tuning Tips

**Conservative (Less Trading)**:

```python
config["confidence_threshold"] = 0.75   # Higher threshold
config["mr_threshold"] = 0.005          # Larger moves only
config["cooldown_seconds"] = 10         # Wider cooldown
```

**Aggressive (More Trading)**:

```python
config["confidence_threshold"] = 0.4    # Lower threshold
config["mr_threshold"] = 0.001          # Smaller moves OK
config["cooldown_seconds"] = 1          # Tight cooldown
```

**Risk-Averse**:

```python
config["max_position_size"] = 2.0       # Smaller positions
config["max_loss_per_session"] = 100.0  # Tight loss limit
```

---

## Performance Metrics Explained

### Win Rate

- **Definition**: % of trades with positive PnL
- **Formula**: (# winning trades) / (# total trades)
- **Target**: > 50% for profitable strategy

### Average Trade PnL

- **Definition**: Mean profit/loss per trade
- **Formula**: (total PnL) / (# trades)
- **Interpretation**: Larger is better; watch for negative values (losing strategy)

### Max Drawdown

- **Definition**: Peak-to-trough decline in cumulative equity
- **Example**: Portfolio goes from $100K peak → $80K trough = $20K drawdown
- **Target**: < 30% of initial capital for conservative strategies

### Sharpe Ratio

- **Definition**: Return per unit of volatility
- **Formula**: (avg trade PnL) / (std dev of trade PnL)
- **Target**: > 1.0 indicates good risk-adjusted returns

### Interpreting Results


| Metric            | Signal               | Action                                  |
| ----------------- | -------------------- | --------------------------------------- |
| Win Rate 60%+     | Good strategy        | Keep and optimize                       |
| Win Rate <40%     | Poor strategy        | Review logic; increase thresholds       |
| Max Drawdown >50% | Too risky            | Reduce position size; increase cooldown |
| Sharpe Ratio <0.5 | High noise           | Tighten parameter thresholds            |
| Sharpe Ratio >2.0 | Possible overfitting | Backtest on unseen data                 |


---

## Backtesting & Optimization

### Running a Backtest

```python
from backtest import run_backtest
import pandas as pd

# Load historical prices
prices = pd.read_csv("historical_prices.csv")["close"].tolist()

config = {
    "initial_cash": 100000.0,
    "mr_threshold": 0.003,
    "confidence_threshold": 0.6,
    "max_position_size": 5.0,
}

result = run_backtest(prices, config)

print(f"Pipeline PnL: ${result['pipeline']['total_pnl']:.2f}")
print(f"Pipeline Sharpe: {result['pipeline']['sharpe_ratio']:.3f}")
```

### Parameter Optimization

```python
from backtest import optimize_parameters

opt = optimize_parameters(prices, base_config)

best_config = opt["best_config"]
results = opt["results"]  # Sorted by PnL descending

print(f"Best Config: {best_config}")
print(f"Best PnL: ${results[0]['pipeline']['total_pnl']:.2f}")

# Display top 3 results
for i, result in enumerate(results[:3]):
    print(f"\n#{i+1}: {result['config']['mr_threshold']:.4f} → ${result['pipeline']['total_pnl']:.2f}")
```

**Note**: Optimization uses **small bounded deltas** (±5% on thresholds, ±2% on confidence) to avoid overfitting.

---

## Stress Testing

### Run Full Stress Suite

```bash
python stress_testing.py
```

### Run Individual Scenario

```python
from stress_testing import run_stress_test, generate_spike_scenario

prices = generate_spike_scenario(base_price=100.0, spike_percent=0.05, num_ticks=100)
result = run_stress_test("my_spike_test", prices, config)

print(f"System Stable: {result['system_stable']}")
print(f"Risk Blocks: {result['risk_blocks']}")
print(f"Total PnL: ${result['metrics']['total_pnl']:.2f}")
```

### Interpreting Stress Results

**Good Signs**:

- ✅ System Stable: True (no crashes)
- ✅ Risk Blocks > 0 (risk manager is enforcing rules)
- ✅ Drawdowns contained within max_loss_per_session

**Red Flags**:

- ❌ System Stable: False (unhandled exception)
- ❌ Risk Blocks = 0 (risk manager not activating)
- ❌ Sharpe Ratio < 0 (strategy losing money in stress)

---

## Alpaca Paper Trading

Run the fully validated Mini Quant pipeline against **Alpaca Paper Trading**. When you run `python alpaca_paper_runner.py`, the bot loads Alpaca credentials and symbols from `.env`, connects to the Alpaca market-data websocket and trading stream, and then starts processing live ticks.
1. Loads `AlpacaConfig` from environment variables.
2. Builds the live pipeline for each configured symbol.
3. Subscribes to Alpaca market data and order-update streams.
4. For each tick on the primary symbol, updates features and computes mean reversion and momentum signals.
5. Selects the strongest signal, applies risk checks, and submits a paper order when allowed.
6. Waits for fills, updates the local portfolio, records performance metrics, and writes dashboard/log output.
7. Stops when you hit Ctrl+C or when `ALPACA_MAX_TICKS` is reached.

Important notes:
- The runner uses the first entry in `ALPACA_SYMBOLS` as the primary execution symbol.
- If the market is closed, an order may be accepted but not filled until the market opens.
- All trades are paper-only through Alpaca's paper API.

### Quick Start

1. Create/edit `.env` in the project root with:

```bash
ALPACA_API_KEY_ID=your_key
ALPACA_API_SECRET_KEY=your_secret
```

1. (Optional) Set symbols and bound the run:

```bash
ALPACA_SYMBOLS=SPY
ALPACA_MAX_TICKS=500
```

You can also tune the live status confirmations with:

```bash
ALPACA_STATUS_HEARTBEAT_TICKS=50
```

1. Start the paper run:

```bash
python alpaca_paper_runner.py
```

### Start Paper Run: Monitor JSONL/CSV Dashboards and SQLite

Watch while the session runs:

- JSONL dashboard (append-only): `logs/live_dashboard.jsonl`
- Latest snapshot (quick view): `logs/live_dashboard_snapshot.json`
- CSV dashboard (easy charting): `logs/live_dashboard.csv`
- Console heartbeat logs every `ALPACA_STATUS_HEARTBEAT_TICKS` primary ticks, showing the current stage, equity, PnL, and trade count.
- Console output will also show connection status, trade execution, and any risk blocks or reconnect events.

And inspect SQLite DBs (created in `db_dir`, default `.`):

- `alpaca_logs.db` (runtime artifacts)
- Tables in `alpaca_logs.db`: `portfolio_snapshots`, `performance_metrics`, `ws_events`, `connection_events` (connect/reconnect behavior), `risk_blocks` (blocked trades + reasons), `feedback_log` (feedback-loop updates/weights)
- `alpaca_portfolio.db` (trade history from `Portfolio`)

### Validate Strategy Performance

Compare the live-paper run metrics against historical backtesting:

1. Run backtests using `backtest.py` (e.g., `run_backtest` and `optimize_parameters`).
2. Compare against the paper-run metrics stored in `alpaca_logs.db` (`performance_metrics`):
  - `PnL`: `total_pnl`
  - win rate: `win_rate`
  - drawdown: `max_drawdown`
  - Sharpe: `sharpe_ratio`
3. Compare feedback-adjusted weights via:
  - runner summary fields (`mean_reversion_weight`, `momentum_weight`)
  - `feedback_log` (weight update reasoning per update cycle)

If paper performance diverges from backtest, tune thresholds first (`mr_threshold`, `mom_threshold`, `confidence_threshold`) before changing feedback.

### Tune Feedback Loop

If adaptation is too slow/fast:

- Adjust `feedback_trade_interval` (where the feedback loop updates; see `AlpacaConfig` in `alpaca_config.py`).
- Adjust clamping/learning behavior:
- `FeedbackLoop.learning_rate`
- `FeedbackLoop.max_delta_per_step`
These are defined in `main.py` and are used by the runner when constructing `FeedbackLoop()`.

### Optional Multi-symbol Scaling

To smoke-test streaming + throttling across symbols:

```bash
ALPACA_SYMBOLS=SPY,QQQ
```

Note: the current runner trades the first symbol in `ALPACA_SYMBOLS` as the primary execution symbol, while computing features for each subscribed symbol.

Throttling behavior is controlled by:

- `ALPACA_MIN_TICK_INTERVAL` (smaller => more ticks processed, larger => fewer).

### Stress Testing (Reconnect + Extremes)

For simulated strategy resilience (spikes, volatility, downtrends, illiquidity), run:

```bash
python stress_testing.py
```

For WebSocket reconnect/exceptions in the live run:

- Temporarily disrupt internet connectivity and confirm:
- reconnects automatically (see `connection_events`)
- continues to enforce risk gates during reconnect gaps (`risk_blocks`)

---

## Paper Trading & Feedback Loops

### Running a Paper Trading Session

```python
from main import run_paper_trading_session

result = run_paper_trading_session(num_ticks=500, seed=42)

print(f"Final Strategy Weights: {result['final_strategy_weights']}")
print(f"Executed Trades: {result['executed_trades']}")
print(f"Total PnL: ${result['total_pnl']:.2f}")
print(f"Feedback Adjustments: {result.get('feedback_iterations', 0)}")
```

### How Feedback Works

1. **Initialization**: mean_reversion=0.50, momentum=0.50 (equal weight)
2. **Every 10 trades**: Compute performance metrics
3. **Adapt weights**:
  - If mean_reversion performs better → increase its weight (+1% up to ±1% per step)
  - If momentum outperforms → shift weight to momentum
4. **Conservative**: Learning rate=0.02, max delta per step=0.01 (prevents wild swings)

**Example**:

```
After 10 trades: mean_reversion=0.52, momentum=0.48 (MR slightly better)
After 20 trades: mean_reversion=0.54, momentum=0.46 (MR continues outperforming)
After 30 trades: mean_reversion=0.55, momentum=0.45 (max delta hit, stabilizing)
```

---

## Logs & Debugging

### Access SQLite Databases

```python
import sqlite3

# Portfolio trades
conn = sqlite3.connect("portfolio_database.db")
trades = conn.execute("SELECT * FROM trades ORDER BY timestamp DESC LIMIT 10").fetchall()
for trade in trades:
    print(trade)

# Signals
signals = conn.execute("SELECT * FROM signals ORDER BY timestamp DESC LIMIT 10").fetchall()

# Performance metrics
metrics = conn.execute("SELECT * FROM performance_metrics ORDER BY timestamp DESC LIMIT 5").fetchall()

conn.close()
```

### Debug Output

Enable debug logging in feature_engine or execution:

```python
features = FeatureEngine(ma_window=20, debug=True)
# Output:
# [feature_engine] avg20=100.50 avg50=100.30 vol=2.10 mom=0.015

execution = ExecutionEngine(portfolio, paper_mode=True, debug=True)
# Output:
# [execution] action=buy size=1.0 price=100.50 fee=0.10
```

### Interpreting Log Entries

**Signal Log**:

```
strategy: "mean_reversion" | "momentum"
action: "buy" | "sell" | "hold"
confidence: 0.0-1.0 confidence score
reason: Human-readable explanation
```

**Trade Log**:

```
action: "buy" | "sell"
size: Units traded
price: Execution price
fee: Transaction fee ($)
realized_pnl: Profit/loss on closed position
```

**Portfolio Log**:

```
cash: Available cash balance
position_size: Current position (units)
equity: Total account value
total_pnl: Cumulative profit/loss
```

---

## Scaling to Real Capital

### ⚠️ Important: Safety Guidelines

**DO NOT enable real trading without**:

1. ✅ 100+ hours of paper trading with positive Sharpe ratio > 0.5
2. ✅ Passing all stress test scenarios with contained drawdowns
3. ✅ Backtesting on out-of-sample data with consistent results
4. ✅ Code review by another engineer or trading mentor
5. ✅ Starting with **micro-position sizes** (0.01 contracts, not 1.0)

### Progression Path

**Phase 1: Simulated Testing (Current)**

- Run `run_paper_trading_session()` with synthetic ticks
- Goal: Positive PnL, Sharpe > 0.5, stable feedback loop
- Duration: 100+ simulated market days

**Phase 2: Backtesting**

- Load real historical prices
- Run `optimize_parameters()` to refine config
- Goal: Consistent edge across multiple time periods
- Duration: Test on 6+ months of data

**Phase 3: Stress Testing**

- Run full `run_stress_suite()` 
- Verify risk manager blocks dangerous trades
- Goal: Max drawdown < 20% of account
- Duration: Complete all 8 scenarios

**Phase 4: Paper Live (Optional)**

```python
from data_feed import live_binance_midprice_stream
from main import run_paper_trading_session

# Connect to live Binance feed (paper observation only)
async def monitor_live():
    async for tick in live_binance_midprice_stream("btcusdt"):
        # Manually record market prices; observe behavior
        pass
```

- Duration: 1-2 weeks minimum

**Phase 5: Micro Real Trading (If Approved)**

```python
# Enable real execution with smallest position size
config["trade_size"] = 0.01  # 0.01 BTC, not 1.0
config["max_position_size"] = 0.05  # Max 0.05 BTC position
config["max_loss_per_session"] = 50.0  # Max $50 daily loss
```

### Implementation Checklist

- Paper trading PnL > 0 for 30+ days
- Sharpe ratio > 0.5 in live conditions
- All 8 stress tests passed
- Backtest results confirm edge (win rate > 52%)
- Risk manager actively blocking trades
- Code audit completed
- Position size set to micro (0.01 units)
- Daily loss limit set to conservative level
- Monitoring infrastructure in place (logs, alerts)

---

## Best Practices

### ✅ Do's

- **Run tests before each modification** (`python -m unittest discover -s tests`)
- **Review logs after every session** (SQLite tables tell the story)
- **Backtest before live deployment** (catch edge cases early)
- **Stress test regularly** (markets will behave unexpectedly)
- **Keep position sizes small** (safer to learn)
- **Monitor Sharpe ratio, not just PnL** (high PnL with high risk is not a win)
- **Document config changes** (track what worked and why)
- **Save historical logs** (post-mortem analysis is invaluable)

### ❌ Don'ts

- **Don't skip the feedback loop tests** (missed a growth step)
- **Don't ignore risk manager blocks** (they're there for safety)
- **Don't overtrade** (tight cooldown is better than fast feedback)
- **Don't optimize on a single time period** (overfitting disaster)
- **Don't increase position size after one winning trade** (regress to the mean)
- **Don't deploy to real capital before Phase 3** (ask a mentor first)
- **Don't disable logging** (black box trading is dangerous)
- **Don't assume past performance predicts future results** (always backtest new data)

---

## Troubleshooting

### Test Failures

`**ModuleNotFoundError: No module named 'pandas'`**

```bash
pip install pandas numpy
```

`**sqlite3.OperationalError: database is locked**`

- Ensure only one process is writing to the database at a time
- Check for stale database connections

`**ValueError: cannot sell more than current position**`

- Long-only portfolio constraint; backtest guard skips invalid sells
- Check that `run_backtest` handles this (it does by default)

### Performance Issues

**Slow stress suite execution**

- Reduce num_ticks per scenario: `generate_spike_scenario(..., num_ticks=50)`
- Serial execution; stress tests run one-by-one for stability

**High RAM usage**

- Limit backtest size: backtest on 1-year chunks instead of full history
- Use tempfile for intermediate databases

### Feedback Loop Not Adapting

**Weights aren't changing**

- Check `feedback_freq`: default is every 10 trades; may take >10 trades to see change
- Verify metrics are being recorded: check SQLite `performance_metrics` table
- Learning rate too low? (default=0.02); increase slightly for testing

**Weights oscillating wildly**

- Lower feedback_learning_rate: 0.02 is safe; 0.005 is conservative
- Increase feedback_freq: every 20 trades instead of 10

---

## Example Workflows

### Workflow 1: Find Winning Parameters

```python
from backtest import optimize_parameters
import pandas as pd

# Load 6 months of data
prices = pd.read_csv("btc_history.csv")["close"].tolist()

# Base config
config = {"mr_threshold": 0.003, "mom_threshold": 0.002, "confidence_threshold": 0.6}

# Optimize
opt = optimize_parameters(prices, config)
best = opt["results"][0]

print(f"Best PnL: ${best['pipeline']['total_pnl']:.2f}")
print(f"Best Config: {best['config']}")

# Deploy best config to paper trading
```

### Workflow 2: Stress-Test a New Strategy

```python
from stress_testing import run_stress_suite

# New config
new_config = {"mr_threshold": 0.004, "confidence_threshold": 0.55, ...}

results = run_stress_suite(new_config)

for scenario, result in results.items():
    if result["system_stable"] and result["metrics"]["sharpe_ratio"] > 0.5:
        print(f"✅ {scenario}: PASSED")
    else:
        print(f"❌ {scenario}: FAILED")
```

### Workflow 3: Monitor Live Paper Trades

```python
from main import run_paper_trading_session

result = run_paper_trading_session(num_ticks=1000, seed=42)

# Analyze the result
trades = result["executed_trades"]
pnl = result["total_pnl"]
win_rate = result["win_rate"]
sharpe = result["sharpe_ratio"]

print(f"Trades: {trades} | PnL: ${pnl:.2f} | Win Rate: {win_rate:.1%} | Sharpe: {sharpe:.2f}")

# Save config for next run
import json
with open("last_config.json", "w") as f:
    json.dump(result["final_strategy_weights"], f)
```

---

## Summary

This mini quant system gives you a **production-ready framework** for learning algorithmic trading:

- 📊 **10 core modules** handling every aspect of a trading pipeline
- 📈 **Backtesting & optimization** to find your edge
- 🛡️ **Risk management** with cooldown, position limits, and loss gates
- 🔄 **Feedback loops** that adapt strategy weights in real time
- 📝 **Comprehensive logging** for transparency and audit trails
- ✅ **33 unit tests** ensuring reliability
- 💪 **8 stress scenarios** validating robustness

**Next Steps**:

1. Run the paper trading session: `python -m unittest tests.test_integration_pipeline -v`
2. Analyze the logs: `sqlite3 portfolio_database.db`
3. Optimize parameters: `run_backtest()` with your own prices
4. Stress test: `python stress_testing.py`
5. Scale responsibly: Follow Phase 1→5 progression before real capital

---

## Support & Questions

- **Debugging**: Enable `debug=True` on FeatureEngine or ExecutionEngine
- **Performance**: Review SQLite logs; Sharpe ratio is your north star
- **Safety**: Always verify risk manager is blocking bad trades (check risk_blocks count)
- **Scaling**: Contact a trading mentor before Phase 5; no solo deployment of real capital

Good luck! 🚀