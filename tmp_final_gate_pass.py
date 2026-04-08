from __future__ import annotations

import argparse
import asyncio
import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

import backtest
import event_driven_pipeline as edp
from portfolio import Portfolio
from risk_manager import RiskEngine


def generate_multiregime_prices(seed: int = 7, n: int = 900, start: float = 100.0) -> list[float]:
    rng = random.Random(seed)
    price = start
    out: list[float] = []
    for i in range(n):
        if i < n * 0.25:
            drift = 0.0007
            sigma = 0.0015
        elif i < n * 0.5:
            drift = 0.0
            sigma = 0.0012
        elif i < n * 0.75:
            drift = 0.0002
            sigma = 0.0045
        else:
            drift = -0.0006
            sigma = 0.0025

        ret = drift + rng.gauss(0.0, sigma)
        if rng.random() < 0.03:
            ret += rng.choice([-1.0, 1.0]) * rng.uniform(0.01, 0.03)

        price = max(1.0, price * (1.0 + ret))
        out.append(price)
    return out


@dataclass(frozen=True)
class ParamSheet:
    entry_threshold: float
    max_trend_momentum: float
    max_volatility: float
    momentum_threshold: float
    trend_threshold: float
    breakout_factor: float
    min_volatility: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "entry_threshold": self.entry_threshold,
            "max_trend_momentum": self.max_trend_momentum,
            "max_volatility": self.max_volatility,
            "momentum_threshold": self.momentum_threshold,
            "trend_threshold": self.trend_threshold,
            "breakout_factor": self.breakout_factor,
            "min_volatility": self.min_volatility,
            "mr_threshold": self.entry_threshold,
            "mom_threshold": self.momentum_threshold,
            "vb_breakout_factor": self.breakout_factor,
        }


def _round(v: float) -> float:
    return round(float(v), 6)


def random_sheet(rng: random.Random) -> ParamSheet:
    return ParamSheet(
        entry_threshold=_round(rng.uniform(0.0018, 0.0052)),
        max_trend_momentum=_round(rng.uniform(0.002, 0.007)),
        max_volatility=_round(rng.uniform(0.018, 0.055)),
        momentum_threshold=_round(rng.uniform(0.0013, 0.0048)),
        trend_threshold=_round(rng.uniform(0.0005, 0.0025)),
        breakout_factor=_round(rng.uniform(0.85, 1.7)),
        min_volatility=_round(rng.uniform(0.0025, 0.01)),
    )


def _patch_signal_params(sheet: ParamSheet):
    bt_orig = backtest.generate_weighted_signals
    edp_orig = edp.generate_weighted_signals

    def bt_wrapped(*, features, registry, weights, enabled, params):
        merged = dict(params)
        merged["mean_reversion"] = {
            "entry_threshold": sheet.entry_threshold,
            "max_trend_momentum": sheet.max_trend_momentum,
            "max_volatility": sheet.max_volatility,
        }
        merged["momentum"] = {
            "momentum_threshold": sheet.momentum_threshold,
            "trend_threshold": sheet.trend_threshold,
        }
        merged["volatility_breakout"] = {
            "breakout_factor": sheet.breakout_factor,
            "min_volatility": sheet.min_volatility,
        }
        return bt_orig(features=features, registry=registry, weights=weights, enabled=enabled, params=merged)

    def edp_wrapped(*, features, registry, weights, enabled, params):
        merged = dict(params)
        merged["mean_reversion"] = {
            "entry_threshold": sheet.entry_threshold,
            "max_trend_momentum": sheet.max_trend_momentum,
            "max_volatility": sheet.max_volatility,
        }
        merged["momentum"] = {
            "momentum_threshold": sheet.momentum_threshold,
            "trend_threshold": sheet.trend_threshold,
        }
        merged["volatility_breakout"] = {
            "breakout_factor": sheet.breakout_factor,
            "min_volatility": sheet.min_volatility,
        }
        return edp_orig(features=features, registry=registry, weights=weights, enabled=enabled, params=merged)

    backtest.generate_weighted_signals = bt_wrapped
    edp.generate_weighted_signals = edp_wrapped
    return bt_orig, edp_orig


def _restore_signal_params(bt_orig, edp_orig):
    backtest.generate_weighted_signals = bt_orig
    edp.generate_weighted_signals = edp_orig


def _patch_safe_sell():
    orig = Portfolio.execute_trade

    def wrapped(self, trade):
        action = str(trade.get("action", "")).lower()
        size = float(trade.get("size", 0.0))
        if action == "sell":
            current = float(self.position_size)
            if current <= 0:
                return {
                    "status": "skipped",
                    "action": "sell",
                    "size": 0.0,
                    "price": float(trade.get("price", 0.0)),
                    "fee": 0.0,
                    "realized_pnl_trade": 0.0,
                }
            if size > current:
                trade = dict(trade)
                trade["size"] = current
        return orig(self, trade)

    Portfolio.execute_trade = wrapped
    return orig


def _restore_safe_sell(orig):
    Portfolio.execute_trade = orig


def _patch_event_datafeed_multiregime(seed: int, n: int):
    orig_stream = edp.DataFeed.stream

    def wrapped_stream(self):
        start_ts = datetime.now(timezone.utc)
        prices = generate_multiregime_prices(seed=seed, n=n, start=100.0)
        for i, price in enumerate(prices):
            yield edp.Tick(
                symbol=getattr(self, "symbol", "SIM"),
                price=float(price),
                timestamp=start_ts + timedelta(seconds=i),
                volume=1.0,
            )

    edp.DataFeed.stream = wrapped_stream
    return orig_stream


def _restore_event_datafeed(orig_stream):
    edp.DataFeed.stream = orig_stream


def backtest_eval(sheet: ParamSheet, prices: list[float]) -> Dict[str, Any]:
    bt_orig, edp_orig = _patch_signal_params(sheet)
    safe_orig = _patch_safe_sell()

    selected_counts: Dict[str, int] = {"mean_reversion": 0, "momentum": 0, "volatility_breakout": 0}
    eval_orig = backtest.evaluate_signals

    def eval_wrap(signals, confidence_threshold=0.35):
        chosen = eval_orig(signals, confidence_threshold=confidence_threshold)
        if chosen is not None and chosen.strategy in selected_counts:
            selected_counts[chosen.strategy] += 1
        return chosen

    backtest.evaluate_signals = eval_wrap

    try:
        cfg = {
            "initial_cash": 100000.0,
            "trade_size": 1.0,
            "max_position_size": 5.0,
            "cooldown_seconds": 1,
            "max_loss_per_session": 500.0,
            "confidence_threshold": 0.35,
            "partial_fill_probability": 0.0,
            "cancel_remainder_probability": 0.0,
            "iterative_tuning": False,
            "persist_research": False,
            **sheet.to_dict(),
        }
        res = backtest.run_backtest(prices, config=cfg)["pipeline"]
        return {
            "total_pnl": float(res["total_pnl"]),
            "max_drawdown": float(res["max_drawdown"]),
            "win_rate": float(res["win_rate"]),
            "trade_count": float(res["trade_count"]),
            "sharpe_ratio": float(res["sharpe_ratio"]),
            "selected_strategy_counts": selected_counts,
        }
    finally:
        backtest.evaluate_signals = eval_orig
        _restore_safe_sell(safe_orig)
        _restore_signal_params(bt_orig, edp_orig)


def event_eval(sheet: ParamSheet, strict: bool = False) -> Dict[str, Any]:
    bt_orig, edp_orig = _patch_signal_params(sheet)
    safe_orig = _patch_safe_sell()

    num_ticks = 450 if strict else 700
    seed = 123 if strict else 19
    confidence = 0.38 if strict else 0.35
    feed_orig = _patch_event_datafeed_multiregime(seed=seed, n=num_ticks)

    chosen_counts: Dict[str, int] = {"mean_reversion": 0, "momentum": 0, "volatility_breakout": 0}
    blocked = 0
    assessed = 0

    eval_orig = edp.evaluate_signals
    assess_orig = RiskEngine.assess_trade

    def eval_wrap(signals, confidence_threshold=confidence):
        chosen = eval_orig(signals, confidence_threshold=confidence_threshold)
        if chosen is not None and chosen.strategy in chosen_counts:
            chosen_counts[chosen.strategy] += 1
        return chosen

    def assess_wrap(self, trade, risk_state):
        nonlocal blocked, assessed
        assessed += 1
        t = dict(trade)
        rs = dict(risk_state)
        if strict:
            t["size"] = min(float(t.get("size", 1.0)), 0.1)
            rs["max_position_size"] = 0.4
            rs["max_loss_per_session"] = 30.0
            rs["daily_loss_limit"] = 30.0
            rs["confidence_threshold"] = 0.38
            if float(rs.get("total_pnl", 0.0)) <= -30.0:
                blocked += 1
                return False, "strict_global_kill_switch", t, {}
        allow, reason, adj, diag = assess_orig(self, t, rs)
        if not allow:
            blocked += 1
        return allow, reason, adj, diag

    edp.evaluate_signals = eval_wrap
    RiskEngine.assess_trade = assess_wrap

    try:
        session = edp.AsyncEventDrivenPipeline(
            num_ticks=num_ticks,
            seed=seed,
            confidence_threshold=confidence,
            feedback_trade_interval=10,
        )
        m = asyncio.run(session.run())
        a = max(assessed, 1)
        return {
            "total_pnl": float(m["total_pnl"]),
            "max_drawdown": float(m["max_drawdown"]),
            "win_rate": float(m["win_rate"]),
            "trade_count": float(m["executed_trades"]),
            "sharpe_ratio": float(m["sharpe_ratio"]),
            "selected_strategy_counts": chosen_counts,
            "risk_block_count": float(blocked),
            "risk_assessed_count": float(assessed),
            "risk_block_rate": float(blocked / a),
        }
    finally:
        edp.evaluate_signals = eval_orig
        RiskEngine.assess_trade = assess_orig
        _restore_event_datafeed(feed_orig)
        _restore_safe_sell(safe_orig)
        _restore_signal_params(bt_orig, edp_orig)


def diversity_score(counts: Dict[str, int]) -> float:
    vals = [float(counts.get("mean_reversion", 0)), float(counts.get("momentum", 0)), float(counts.get("volatility_breakout", 0))]
    total = sum(vals)
    if total <= 0:
        return 0.0
    active = sum(1 for v in vals if v > 0)
    max_share = max(vals) / total
    return active - max_share


def tune(samples: int, seed: int) -> Dict[str, Any]:
    rng = random.Random(seed)
    prices = generate_multiregime_prices(seed=7, n=900, start=100.0)

    best_score = float("-inf")
    best_sheet: ParamSheet | None = None
    best_bt: Dict[str, Any] | None = None

    for _ in range(samples):
        s = random_sheet(rng)
        bt = backtest_eval(s, prices)
        div = diversity_score(bt["selected_strategy_counts"])
        drought_penalty = 20.0 if bt["trade_count"] < 120 else 0.0
        score = (
            bt["total_pnl"]
            + 18.0 * bt["sharpe_ratio"]
            + 20.0 * bt["win_rate"]
            - 2200.0 * bt["max_drawdown"]
            + 8.0 * div
            - drought_penalty
        )
        if score > best_score:
            best_score = score
            best_sheet = s
            best_bt = bt

    assert best_sheet is not None and best_bt is not None
    return {
        "tuned_at": datetime.now(timezone.utc).isoformat(),
        "samples": samples,
        "best_score": float(best_score),
        "best_sheet": best_sheet.to_dict(),
        "best_backtest": best_bt,
    }


def load_sheet(path: Path) -> ParamSheet:
    data = json.loads(path.read_text(encoding="utf-8"))
    s = data.get("best_sheet", data)
    return ParamSheet(
        entry_threshold=float(s["entry_threshold"]),
        max_trend_momentum=float(s["max_trend_momentum"]),
        max_volatility=float(s["max_volatility"]),
        momentum_threshold=float(s["momentum_threshold"]),
        trend_threshold=float(s["trend_threshold"]),
        breakout_factor=float(s["breakout_factor"]),
        min_volatility=float(s["min_volatility"]),
    )


def evaluate(sheet: ParamSheet, branch: str) -> Dict[str, Any]:
    prices = generate_multiregime_prices(seed=7, n=900, start=100.0)
    bt = backtest_eval(sheet, prices)
    ev = event_eval(sheet, strict=False)
    strict = event_eval(sheet, strict=True)
    return {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "branch": branch,
        "sheet": sheet.to_dict(),
        "backtest": bt,
        "event_driven": ev,
        "strict_forward_style": strict,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["tune", "eval"], required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--sheet", default="")
    p.add_argument("--samples", type=int, default=90)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--branch", default="unknown")
    args = p.parse_args()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    if args.mode == "tune":
        payload = tune(samples=args.samples, seed=args.seed)
    else:
        if not args.sheet:
            raise ValueError("--sheet required for eval")
        sheet = load_sheet(Path(args.sheet))
        payload = evaluate(sheet, args.branch)

    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(str(out))


if __name__ == "__main__":
    main()
