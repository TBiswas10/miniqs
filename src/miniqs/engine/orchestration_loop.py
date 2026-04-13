"""Orchestrator: Manages the IDEA -> BUILD -> TEST -> EVALUATE loop."""

from src.miniqs.data.data_feed import DataFeed
from src.miniqs.agents.alpha_researcher import AlphaResearcher
from src.miniqs.agents.evaluator_agent import EvaluatorAgent
from backtest import run_backtest
import time

def run_autonomous_research_loop(symbol: str = "AAPL", iterations: int = 5):
    print(f"🧠 [Orchestrator] Starting research loop for {symbol}")
    
    # Initialize Agents
    researcher = AlphaResearcher()
    evaluator = EvaluatorAgent(min_sharpe=1.0, max_drawdown=0.20)
    
    # 1. DATA AGENT: Generate/Fetch synthetic historical data for research
    feed = DataFeed(symbol=symbol, mode="simulated", seed=42)
    # Generate a baseline price series (500 ticks)
    prices = [t.price for t in feed.stream()]
    prices = prices[:500] 
    
    current_feedback = []
    
    for i in range(iterations):
        print(f"\n--- Iteration {i+1} ---")
        
        # 2. RESEARCH AGENT: Generate IDEA
        # We assume a fixed volatility for this demo
        market_metrics = {"realized_volatility": 0.015} 
        proposal = researcher.generate_strategy_proposal(market_metrics, feedback=current_feedback)
        print(f"🔬 [ResearchAgent] Proposed: {proposal['logic_name']} ({proposal['rationale']})")
        
        # 3. CODE AGENT: Map proposal to Backtester config
        config = {
            "symbol": symbol,
            "initial_cash": 100000.0,
            "persist_research": False
        }
        
        if proposal["logic_name"] == "mean_reversion":
            config["mr_threshold"] = proposal["parameters"]["entry_threshold"]
        elif proposal["logic_name"] == "volatility_breakout":
            config["vb_breakout_factor"] = proposal["parameters"]["breakout_factor"]

        # 4. BACKTESTER AGENT: TEST
        try:
            results = run_backtest(prices, config=config)
            metrics = results["pipeline"]
            print(f"📈 [Backtester] Sharpe: {metrics['sharpe_ratio']:.2f}, DD: {metrics['max_drawdown']:.2%}")
            
            # 5. EVALUATOR AGENT: EVALUATE
            approved, verdict, suggestions = evaluator.evaluate(metrics)
            
            if approved:
                print(f"✅ [Evaluator] Strategy Approved! Logic: {proposal['logic_name']}")
                break
            else:
                print(f"❌ [Evaluator] {verdict}. Suggestions: {suggestions}")
                # 6. IMPROVE: Feed suggestions back into the next iteration
                current_feedback = suggestions
                
        except Exception as e:
            print(f"⚠️ Error during backtest: {e}")
            break

    print("\n🏁 [Orchestrator] Research session complete.")

if __name__ == "__main__":
    run_autonomous_research_loop()