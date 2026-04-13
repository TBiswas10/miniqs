"""Research Agent: Automated Alpha Generation & Parameter Tuning."""

import random
from typing import Dict, Any, List

class AlphaResearcher:
    """Implements the Research Agent logic for strategy discovery and numerical optimization.
    Runs Monte Carlo permutations over the active parameters to recommend tomorrow's bounds.
    """

    def __init__(self):
        self.discovered_alphas = []
        self.base_perturbation = 0.05

    def generate_strategy_proposal(
        self, market_metrics: Dict[str, Any], feedback: List[str] = None
    ) -> Dict[str, Any]:
        """
        Research Agent logic: Generate or mutate a strategy parameters.
        """
        volatility = market_metrics.get("realized_volatility", 0.01)
        
        mr_threshold = 0.003
        if feedback and any("high drawdown" in f.lower() for f in feedback):
            mr_threshold *= 1.2
            print("[ResearchAgent] Tuning MR threshold aggressively due to Drawdown.")

        # Monte Carlo Perturbation Simulation
        simulated_mr_threshold = mr_threshold * (1.0 + random.uniform(-self.base_perturbation, self.base_perturbation))
        simulated_breakout = 1.5 * (1.0 + random.uniform(-self.base_perturbation, self.base_perturbation))

        if volatility > 0.02:
            return {
                "logic_name": "volatility_breakout",
                "parameters": {"breakout_factor": round(simulated_breakout, 4)},
                "rationale": f"High vol ({volatility:.3f}); tuning breakout constraint to {simulated_breakout:.2f}"
            }
        else:
            return {
                "logic_name": "mean_reversion",
                "parameters": {"entry_threshold": round(simulated_mr_threshold, 5)},
                "rationale": f"Stable market; tightening MR constraint to {simulated_mr_threshold:.5f}"
            }