from __future__ import annotations

from dataclasses import dataclass

from src.miniqs.execution.paper import AlpacaPaperExecutionEngine
from src.miniqs.risk.portfolio import Portfolio


@dataclass
class _FakeClient:
    submitted_ids: list[str]

    def submit_market_order(self, symbol, qty, side, client_order_id=None):
        self.submitted_ids.append(str(client_order_id))
        return {"id": f"order-{len(self.submitted_ids)}"}

    def wait_for_fill(self, order_id, timeout_seconds=45.0, poll_interval=0.5):
        return {"filled_avg_price": 100.0, "filled_qty": 0.01, "filled_at": "2026-04-09T00:00:00Z"}


def test_stable_client_order_id_is_deterministic() -> None:
    engine = AlpacaPaperExecutionEngine(portfolio=Portfolio(initial_cash=100000.0), client=_FakeClient([]))
    trade = {
        "action": "buy",
        "symbol": "BTC/USD",
        "size": 0.01,
        "price": 100.0,
        "timestamp": "2026-04-09T00:00:00Z",
        "strategy": "momentum",
        "confidence": 0.9,
    }

    first = engine._stable_client_order_id(trade)
    second = engine._stable_client_order_id(dict(trade))

    assert first == second
    assert first.startswith("mq-")
    assert len(first) <= 48


def test_execute_trade_reuses_same_client_order_id_for_same_trade() -> None:
    client = _FakeClient([])
    engine = AlpacaPaperExecutionEngine(portfolio=Portfolio(initial_cash=100000.0), client=client)
    trade = {
        "action": "buy",
        "symbol": "BTC/USD",
        "size": 0.01,
        "price": 100.0,
        "timestamp": "2026-04-09T00:00:00Z",
        "strategy": "momentum",
        "confidence": 0.9,
    }

    engine.execute_trade(dict(trade))
    engine.execute_trade(dict(trade))

    assert len(client.submitted_ids) == 2
    assert client.submitted_ids[0] == client.submitted_ids[1]
