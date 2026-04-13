import os
import sys
import json
import urllib.request
from datetime import datetime, timezone
import pathlib
import sqlite3
import time

# Add src to sys.path
sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from src.miniqs.engine.pipeline import PipelineRuntime, on_market_event
from src.miniqs.engine.event_bus import EventBus, MarketEvent
from src.miniqs.data.data_feed import Tick
from src.miniqs.risk.portfolio import Portfolio
from src.miniqs.execution import ExecutionEngine
from src.miniqs.utils.logger import QuantLogger
from src.miniqs.utils.performance import PerformanceTracker
from src.miniqs.risk.engine import RiskConfig, RiskEngine
from src.miniqs.engine.feature_engine import FeatureEngine
from src.miniqs.engine.iteration import AutoTuner, ExperimentLogger, RegimeDetector
from src.miniqs.agents.alpha_copilot import AlphaCopilot
from src.miniqs.strategies import default_strategy_registry

def fetch_binance_klines(symbol="BTCUSDT", interval="1m", limit=1000):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    print(f"[backtest] API Request: {url}")
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"[backtest] Fetch failed: {e}")
        return None

def run_backtest():
    print("[backtest] Initializing Aurelius Prime backtest environment...")
    temp_db = f"backtest_{int(time.time())}.db"
    
    portfolio = Portfolio(db_path=temp_db, initial_cash=100000.0)
    execution = ExecutionEngine(portfolio=portfolio, paper_mode=True, debug=False)
    logger = QuantLogger(db_path=temp_db)
    perf = PerformanceTracker(initial_equity=100000.0)
    
    # RISK CONFIG: Loosened for Hyper-Scalping
    risk_engine = RiskEngine(
        initial_equity=100000.0,
        config=RiskConfig(
            base_trade_size=0.1,    # 10% anchor
            max_position_size=10.0,  # 10x leverage permitted for paper
            cooldown_seconds=0,      # High frequency
            confidence_threshold=0.01,
            max_concurrent_positions=5
        )
    )
    
    runtime = PipelineRuntime(
        portfolio=portfolio,
        execution=execution,
        logger=logger,
        perf=perf,
        feedback=None,
        risk_engine=risk_engine,
        features=FeatureEngine(debug=False),
        regime_detector=RegimeDetector(),
        auto_tuner=AutoTuner(),
        iteration_logger=ExperimentLogger(db_path=temp_db),
        strategy_registry=default_strategy_registry(),
        confidence_threshold=0.01,
        run_id="historical_v5_run",
        copilot=AlphaCopilot(db_path=temp_db),
    )
    
    # High-weight to Hyper-V5
    class DummyFeedback:
        def __init__(self):
            self.strategy_weights = {
                "mean_reversion": 0.01, 
                "momentum": 0.01, 
                "volatility_breakout": 0.01,
                "trend_robust": 0.07,
                "hyper_v5": 0.9
            }
        def is_enabled(self, name): return True
    runtime.feedback = DummyFeedback()
    
    bus = EventBus()
    klines = fetch_binance_klines(limit=1000)
    if not klines: return

    print(f"[backtest] Starting deep simulation on {len(klines)} samples...")
    
    for i, k in enumerate(klines):
        ts = datetime.fromtimestamp(k[0]/1000, tz=timezone.utc)
        tick = Tick(symbol="BTC/USD", price=float(k[4]), timestamp=ts, volume=float(k[5]))
        event = MarketEvent(tick=tick)
        
        on_market_event(event, bus, runtime)
        
        if i % 100 == 0:
            state = portfolio.get_portfolio_state()
            print(f"[backtest] {i:04d} | Price: {tick.price:.2f} | Equity: ${state['equity']:.2f} | Trades: {runtime.executed_trades}")

    # Final Summary
    state = portfolio.get_portfolio_state()
    print("\n" + "="*50)
    print("           STATION PERFORMANCE SUMMARY")
    print("="*50)
    print(f"Total Cycles:      {len(klines)}")
    print(f"Executed Trades:   {runtime.executed_trades}")
    print(f"Final Equity:      ${state['equity']:,.2f}")
    print(f"Realized PnL:      ${state['total_pnl']:,.2f}")
    print(f"ROI:               {(state['equity']/100000.0 - 1)*100:.4f}%")
    
    # Rejection Analysis
    with sqlite3.connect(temp_db) as conn:
        rejections = conn.execute("SELECT reason, COUNT(*) FROM risk_blocks GROUP BY reason").fetchall()
    
    if rejections:
        print("\n[Risk Rejections]")
        for reason, count in rejections:
            print(f" - {reason}: {count}")
    else:
        print("\n[Risk Rejections] None. Strategies were silent.")
    print("="*50)

if __name__ == "__main__":
    run_backtest()
