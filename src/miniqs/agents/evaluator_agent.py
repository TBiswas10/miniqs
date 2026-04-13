"""Evaluator Agent: Strict validation of strategy performance."""

from typing import Dict, Any, Tuple, List

class EvaluatorAgent:
    """Gatekeeper that decides if a strategy meets production standards."""

    def __init__(self, min_sharpe: float = 1.0, max_drawdown: float = 0.20):
        self.min_sharpe = min_sharpe
        self.max_drawdown = max_drawdown

    def evaluate(self, metrics: Dict[str, float]) -> Tuple[bool, str, List[str]]:
        """
        Analyzes performance metrics and provides a verdict.
        
        Returns:
            (Approved, Reason, Improvement Suggestions)
        """
        sharpe = metrics.get("sharpe_ratio", 0.0)
        drawdown = metrics.get("max_drawdown", 1.0)
        trade_count = metrics.get("trade_count", 0)
        
        suggestions = []
        approved = True

        if sharpe < self.min_sharpe:
            approved = False
            suggestions.append(f"Sharpe Ratio {sharpe:.2f} is below {self.min_sharpe}. Try adding a trend filter.")
        
        if drawdown > self.max_drawdown:
            approved = False
            suggestions.append(f"Max Drawdown {drawdown:.2%} exceeds {self.max_drawdown:.0%}. Tighten stop-losses.")

        if trade_count < 10:
            approved = False
            suggestions.append("Insufficient trade count for statistical significance.")

        verdict = "APPROVED" if approved else "REJECTED"
        return approved, verdict, suggestions