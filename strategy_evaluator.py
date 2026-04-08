"""Strategy evaluator module.

Input:
- signals_list: list of StrategySignal objects from strategy modules

Output:
- single chosen StrategySignal with highest confidence (v1)
- ensemble-voted StrategySignal with normalization/profile support (v2)
- None when no actionable signal meets threshold
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from event_bus import EventBus, SignalEvent
from strategies import StrategySignal


_PROFILE_THRESHOLD_SCALE: Dict[str, float] = {
    "default": 1.0,
    "strict_forward": 0.75,
}


def evaluate_signals(
    signals_list: List[StrategySignal],
    confidence_threshold: float = 0.6,
) -> Optional[StrategySignal]:
    """Choose highest-confidence actionable signal or return None.

    Input:
    - signals_list: strategy outputs with action/confidence metadata
    - confidence_threshold: minimum required confidence in [0, 1]

    Output:
    - StrategySignal if a buy/sell signal passes threshold
    - None when list is empty, only holds exist, or confidence is too low
    """
    if not 0.0 <= confidence_threshold <= 1.0:
        raise ValueError("confidence_threshold must be between 0.0 and 1.0")

    actionable = [s for s in signals_list if s.action in {"buy", "sell"}]
    if not actionable:
        return None

    best = max(actionable, key=lambda s: s.confidence)
    if best.confidence < confidence_threshold:
        return None

    return best


def _resolve_threshold(confidence_threshold: float, profile: str) -> float:
    if not 0.0 <= confidence_threshold <= 1.0:
        raise ValueError("confidence_threshold must be between 0.0 and 1.0")
    scale = _PROFILE_THRESHOLD_SCALE.get(str(profile).strip().lower(), 1.0)
    return max(0.01, min(1.0, confidence_threshold * scale))


def _normalized_confidence(signal: StrategySignal, normalization: Mapping[str, float]) -> float:
    factor = float(normalization.get(signal.strategy, 1.0))
    return max(0.0, min(1.0, float(signal.confidence) * factor))


def evaluate_signals_v2(
    signals_list: List[StrategySignal],
    confidence_threshold: float = 0.6,
    *,
    profile: str = "default",
    strategy_normalization: Optional[Mapping[str, float]] = None,
    dominance_cap: float = 0.65,
    return_telemetry: bool = False,
) -> Union[Optional[StrategySignal], Tuple[Optional[StrategySignal], Dict[str, Any]]]:
    """Choose a signal via ensemble voting with confidence normalization.

    Steps:
    - filter to actionable signals
    - apply per-strategy confidence normalization factors
    - aggregate buy and sell vote scores
    - cap single-strategy dominance on each side
    - select side with larger capped score if score passes profile-adjusted threshold
    """
    if not 0.1 <= dominance_cap <= 1.0:
        raise ValueError("dominance_cap must be between 0.1 and 1.0")

    normalization = strategy_normalization or {}
    threshold = _resolve_threshold(confidence_threshold, profile)

    actionable = [s for s in signals_list if s.action in {"buy", "sell"}]
    normalized_contributions: Dict[str, Dict[str, float]] = {}
    if not actionable:
        empty_telemetry = {
            "buy_score": 0.0,
            "sell_score": 0.0,
            "normalized_contributions": normalized_contributions,
            "applied_threshold": round(float(threshold), 6),
            "applied_profile": profile,
            "dominance_cap": float(dominance_cap),
            "actionable_count": 0,
            "max_actionable_confidence": 0.0,
            "max_side_score": 0.0,
        }
        if return_telemetry:
            return None, empty_telemetry
        return None

    buy_raw: Dict[str, float] = {}
    sell_raw: Dict[str, float] = {}
    normalized_signals: List[tuple[StrategySignal, float]] = []

    for signal in actionable:
        nconf = _normalized_confidence(signal, normalization)
        normalized_signals.append((signal, nconf))
        target = buy_raw if signal.action == "buy" else sell_raw
        target[signal.strategy] = target.get(signal.strategy, 0.0) + nconf
        strategy_bucket = normalized_contributions.setdefault(signal.strategy, {"buy": 0.0, "sell": 0.0, "total": 0.0})
        strategy_bucket[signal.action] += nconf
        strategy_bucket["total"] += nconf

    def capped_total(side_raw: Dict[str, float]) -> float:
        raw_total = sum(side_raw.values())
        if raw_total <= 0:
            return 0.0
        if len(side_raw) <= 1:
            return raw_total
        cap = dominance_cap * raw_total
        return sum(min(v, cap) for v in side_raw.values())

    buy_score = capped_total(buy_raw)
    sell_score = capped_total(sell_raw)
    telemetry = {
        "buy_score": round(float(buy_score), 6),
        "sell_score": round(float(sell_score), 6),
        "normalized_contributions": {
            name: {
                "buy": round(float(vals["buy"]), 6),
                "sell": round(float(vals["sell"]), 6),
                "total": round(float(vals["total"]), 6),
            }
            for name, vals in normalized_contributions.items()
        },
        "applied_threshold": round(float(threshold), 6),
        "applied_profile": profile,
        "dominance_cap": float(dominance_cap),
        "actionable_count": len(actionable),
        "max_actionable_confidence": round(float(max((s.confidence for s in actionable), default=0.0)), 6),
        "max_side_score": round(float(max(buy_score, sell_score)), 6),
    }

    if max(buy_score, sell_score) < threshold:
        if return_telemetry:
            return None, telemetry
        return None

    winning_action = "buy" if buy_score >= sell_score else "sell"

    winners = [(sig, nconf) for sig, nconf in normalized_signals if sig.action == winning_action]
    if not winners:
        return None

    chosen_signal, chosen_nconf = max(winners, key=lambda x: x[1])
    side_score = buy_score if winning_action == "buy" else sell_score

    chosen = StrategySignal(
        strategy=chosen_signal.strategy,
        action=winning_action,
        confidence=round(min(1.0, side_score), 4),
        reason=(
            f"ensemble_vote profile={profile} threshold={threshold:.3f} "
            f"buy={buy_score:.3f} sell={sell_score:.3f} leader_conf={chosen_nconf:.3f}"
        ),
    )
    if return_telemetry:
        return chosen, telemetry
    return chosen


def emit_signal_event(
    *,
    bus: EventBus,
    chosen: StrategySignal,
    trade: Dict[str, Any],
    risk_state: Dict[str, Any],
) -> None:
    """Emit a standardized signal event onto the event bus.

    This keeps signal publication responsibility inside the evaluator layer,
    while downstream handlers own risk checks and execution.
    """
    bus.publish(SignalEvent(strategy=chosen.strategy, trade=trade, risk_state=risk_state))
