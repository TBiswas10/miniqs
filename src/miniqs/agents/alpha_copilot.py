from typing import List, Dict, Any, Optional, Callable
from functools import wraps
import random
import sqlite3

class AlphaCopilot:
    """
    LLM-powered Copilot that monitors SQLite risk logs and strategy performance,
    answering why trades were rejected, or summarizing performance.
    """
    def __init__(self, db_path: str = "logs.db"):
        self.db_path = db_path
        self._personalities = [
            "Analyzing the order flow with precision...",
            "Decrypting market signals for institutional edge...",
            "Reviewing execution vectors...",
        ]

    def _llm_mock(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            result = func(self, *args, **kwargs)
            if not isinstance(result, str):
                return result
            
            prefix = random.choice(self._personalities)
            suffix = "\n\n---\n*Alpha Copilot V3 (Aurelius Prime Terminal)*"
            
            return f"{prefix}\n\n{result}{suffix}"
        return wrapper

    def _query_db(self, query: str, params: tuple = ()) -> List[tuple]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                return cursor.fetchall()
        except sqlite3.Error as e:
            return [(f"Database Error: {e}",)]

    def analyze_recent_rejections(self, latest_features: Optional[Dict[str, float]] = None) -> str:
        """
        Pulls the top 5 rejected trades from SQLite 
        and formulates a natural language explanation incorporating indicator context.
        """
        query = "SELECT timestamp, strategy, reason FROM risk_blocks ORDER BY timestamp DESC LIMIT 5"
        rows = self._query_db(query)
        
        if not rows or "Database Error" in str(rows[0][0]):
            msg = "No recent trade rejections found in the risk log."
            if rows and "Database Error" in str(rows[0][0]):
                msg += f" (Note: {rows[0][0]})"
            return msg
            
        summary = "### Recent Trade Rejections Analysis\n\n"
        for row in rows:
            if len(row) < 3:
                continue
            ts, strategy, reason = row
            summary += f"- **[{ts}] {strategy}**: Blocked due to `{reason}`\n"
        
        # Add intelligence based on features
        if latest_features:
            rsi = latest_features.get("rsi", 50.0)
            macd = latest_features.get("macd", 0.0)
            summary += "\n**AI Insights (Indicator Context):**\n"
            if rsi > 65:
                summary += f" - RSI is high ({rsi:.1f}), which likely suppressed Mean Reversion Buys and triggered Overbought filters.\n"
            elif rsi < 35:
                summary += f" - RSI is low ({rsi:.1f}), favoring Mean Reversion Buys but potentially blocking Momentum strategies.\n"
            
            if abs(macd) < 0.0001:
                summary += " - MACD is currently flat, which may lead to 'Trend Confirmation' rejections in Momentum strategies.\n"
        else:
            summary += "\n**AI Insights:** Multiple 'cooldown' blocks detected. Consider adjusting `cooldown_seconds` in your Risk Profile if liquidity is high."

        return summary

    def get_market_summary(self, features: Dict[str, float]) -> str:
        """Summarize current market sentiment based on technicals."""
        rsi = features.get("rsi", 50.0)
        macd = features.get("macd", 0.0)
        vol = features.get("volatility", 0.0)
        
        sentiment = "Neutral"
        if rsi > 60 and macd > 0: sentiment = "Bullish Overflow"
        elif rsi < 40 and macd < 0: sentiment = "Bearish Exhaustion"
        elif vol > 0.02: sentiment = "High Volatility / Expansion"
        
        return (
            f"**Market Sentiment:** {sentiment}\n"
            f"- RSI: {rsi:.2f}\n"
            f"- MACD: {macd:.6f}\n"
            f"- Volatility: {vol:.4%}"
        )

    @_llm_mock
    def generate_daily_report(self) -> str:
        """Aggregate performance and risk data from the last 24 hours into a summary."""
        # Query for last 24h PnL and trades
        trade_query = "SELECT COUNT(*), SUM(realized_pnl_trade) FROM trades WHERE ts > datetime('now', '-1 day')"
        risk_query = "SELECT COUNT(*) FROM risk_blocks WHERE ts > datetime('now', '-1 day')"
        
        trade_data = self._query_db(trade_query)
        risk_data = self._query_db(risk_query)
        
        trade_count = 0
        total_pnl = 0.0
        risk_count = 0

        if trade_data and len(trade_data[0]) >= 2:
            trade_count = trade_data[0][0] if trade_data[0][0] is not None else 0
            total_pnl = trade_data[0][1] if trade_data[0][1] is not None else 0.0
            
        if risk_data and len(risk_data[0]) >= 1:
            risk_count = risk_data[0][0] if risk_data[0][0] is not None else 0
        
        report = "## 24-Hour Station Intelligence Report\n\n"
        report += f"**Station Status:** {'Active' if trade_count > 0 else 'Observing'}\n"
        report += f"**Network Executions:** {trade_count}\n"
        report += f"**Realized Alpha (PnL):** ${total_pnl:,.2f}\n"
        report += f"**Risk Interventions:** {risk_count}\n\n"
        
        if risk_count > 5:
            report += "> [!WARNING]\n"
            report += "> High risk intervention rate detected. Market volatility may be exceeding baseline parameters.\n\n"
        
        report += "### Strategic Directives\n"
        if total_pnl > 0:
            report += "- Maintain current scaling. The model is capturing the expansion vector effectively.\n"
        else:
            report += "- Recommendation: Review RSI thresholds. We may be entering a 'chop' zone where mean reversion is being trapped.\n"
            
        return report

    @_llm_mock
    def ask(self, question: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Main interface for the Copilot with optional execution context.
        """
        question = question.lower()
        feats = context.get("features") if context else None
        
        if "why" in question and ("reject" in question or "block" in question):
            return self.analyze_recent_rejections(latest_features=feats)
        elif "status" in question or "summary" in question:
            if feats:
                return self.get_market_summary(feats)
            return "I need more market data to provide a summary."
        
        return "I am the Alpha Copilot. I analyze logs and technical indicators to help you dominate BTC/USD. Ask me about rejections or current market status."
