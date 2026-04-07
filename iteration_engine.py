"""Iteration engine for self-improving strategy/risk behavior."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
from statistics import mean, pstdev
from typing import Dict, List, Mapping


@dataclass
class MarketConditions:
    regime: str
    realized_volatility: float
    trend_slope: float
    momentum: float


class RegimeDetector:
    """Lightweight regime classifier from recent price action."""

    def __init__(self, window: int = 40, vol_high: float = 0.012, trend_threshold: float = 0.0004) -> None:
        self.window = int(window)
        self.vol_high = float(vol_high)
        self.trend_threshold = float(trend_threshold)

    def detect(self, prices: List[float]) -> MarketConditions:
        if len(prices) < 3:
            return MarketConditions(
                regime="unknown",
                realized_volatility=0.0,
                trend_slope=0.0,
                momentum=0.0,
            )

        recent = prices[-self.window :]
        returns: List[float] = []
        for i in range(1, len(recent)):
            prev = recent[i - 1]
            curr = recent[i]
            if prev != 0:
                returns.append((curr / prev) - 1.0)

        if not returns:
            return MarketConditions(
                regime="unknown",
                realized_volatility=0.0,
                trend_slope=0.0,
                momentum=0.0,
            )

        vol = float(pstdev(returns)) if len(returns) > 1 else 0.0
        slope = float((recent[-1] - recent[0]) / max(abs(recent[0]), 1e-9) / len(recent))
        mom = float(mean(returns[-min(5, len(returns)) :]))

        if vol >= self.vol_high:
            regime = "volatile"
        elif slope >= self.trend_threshold:
            regime = "trending_up"
        elif slope <= -self.trend_threshold:
            regime = "trending_down"
        else:
            regime = "range"

        return MarketConditions(regime=regime, realized_volatility=vol, trend_slope=slope, momentum=mom)


class ExperimentLogger:
    """Persist iteration history (params, market conditions, outcomes)."""

    def __init__(self, db_path: str = "experiment_history.db") -> None:
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experiments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    iteration INTEGER NOT NULL,
                    parameter_set TEXT NOT NULL,
                    market_conditions TEXT NOT NULL,
                    outcomes TEXT NOT NULL,
                    recommendations TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def log_experiment(
        self,
        *,
        run_id: str,
        iteration: int,
        parameter_set: Mapping[str, object],
        market_conditions: Mapping[str, object],
        outcomes: Mapping[str, object],
        recommendations: Mapping[str, object],
    ) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO experiments (ts, run_id, iteration, parameter_set, market_conditions, outcomes, recommendations)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    str(run_id),
                    int(iteration),
                    json.dumps(dict(parameter_set), default=str),
                    json.dumps(dict(market_conditions), default=str),
                    json.dumps(dict(outcomes), default=str),
                    json.dumps(dict(recommendations), default=str),
                ),
            )
            conn.commit()
        finally:
            conn.close()


class AutoTuner:
    """Auto-tune strategy weights and risk controls from outcomes + regime."""

    def __init__(
        self,
        learning_rate: float = 0.08,
        max_weight_shift: float = 0.08,
        min_weight: float = 0.05,
    ) -> None:
        self.learning_rate = float(learning_rate)
        self.max_weight_shift = float(max_weight_shift)
        self.min_weight = float(min_weight)

    def recommend(
        self,
        *,
        current_weights: Mapping[str, float],
        risk_params: Mapping[str, float],
        market_conditions: MarketConditions,
        outcomes: Mapping[str, float],
        strategy_metrics: Mapping[str, Mapping[str, float]],
    ) -> Dict[str, object]:
        regime_bias = self._regime_bias(market_conditions.regime)

        updated_weights: Dict[str, float] = {}
        for strategy, w in current_weights.items():
            m = strategy_metrics.get(strategy, {})
            hit_rate = float(m.get("hit_rate", m.get("win_rate", 0.5)))
            avg_pnl = float(m.get("avg_trade_pnl", 0.0))
            sharpe = float(m.get("sharpe_ratio", 0.0))
            max_dd = float(m.get("max_drawdown", 0.0))

            score = (hit_rate - 0.5) + (avg_pnl * 0.01) + (sharpe * 0.06) - (max_dd * 0.02)
            score += regime_bias.get(strategy, 0.0)

            raw_delta = self.learning_rate * score
            delta = max(-self.max_weight_shift, min(self.max_weight_shift, raw_delta))
            updated_weights[strategy] = max(self.min_weight, float(w) + delta)

        updated_weights = self._normalize(updated_weights)

        equity_delta = float(outcomes.get("equity_delta", 0.0))
        drawdown = float(outcomes.get("drawdown", 0.0))
        realized_vol = float(market_conditions.realized_volatility)

        trade_size = float(risk_params.get("base_trade_size", 1.0))
        if equity_delta > 0 and drawdown < 0.08:
            trade_size *= 1.05
        elif equity_delta < 0 or drawdown > 0.12:
            trade_size *= 0.9

        if realized_vol > 0.015:
            trade_size *= 0.85
        elif realized_vol < 0.006:
            trade_size *= 1.08

        max_position = float(risk_params.get("max_position_size", 5.0))
        if drawdown > 0.12:
            max_position *= 0.9
        elif equity_delta > 0 and drawdown < 0.05:
            max_position *= 1.03

        cooldown = int(risk_params.get("cooldown_seconds", 5))
        if market_conditions.regime == "volatile":
            cooldown = min(20, cooldown + 1)
        elif market_conditions.regime in {"trending_up", "trending_down"}:
            cooldown = max(1, cooldown - 1)

        return {
            "strategy_weights": updated_weights,
            "risk_params": {
                "base_trade_size": float(max(0.1, min(2.5, trade_size))),
                "max_position_size": float(max(1.0, min(12.0, max_position))),
                "cooldown_seconds": int(cooldown),
            },
            "market_conditions": asdict(market_conditions),
        }

    def _regime_bias(self, regime: str) -> Dict[str, float]:
        if regime == "trending_up":
            return {"momentum": 0.12, "mean_reversion": -0.03, "volatility_breakout": 0.06}
        if regime == "trending_down":
            return {"momentum": 0.08, "mean_reversion": -0.05, "volatility_breakout": 0.08}
        if regime == "volatile":
            return {"momentum": -0.03, "mean_reversion": 0.06, "volatility_breakout": 0.12}
        return {"momentum": 0.0, "mean_reversion": 0.02, "volatility_breakout": 0.0}

    def _normalize(self, weights: Mapping[str, float]) -> Dict[str, float]:
        total = float(sum(max(0.0, float(v)) for v in weights.values()))
        if total <= 0:
            n = max(1, len(weights))
            return {k: 1.0 / n for k in weights}
        return {k: max(0.0, float(v)) / total for k, v in weights.items()}
