from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch

from src.miniqs.config.asset import resolve_asset_config
from src.miniqs.config.alpaca import AlpacaConfig
from src.miniqs.execution.alpaca_client import AlpacaClient


class TestAlpacaClient(unittest.TestCase):
    def test_get_market_data_uses_correct_market_path(self) -> None:
        cfg = AlpacaConfig(api_key_id="key", api_secret_key="secret")
        client = AlpacaClient(cfg)
        asset = resolve_asset_config(symbol="BTC/USD")

        payload = {"bars": {"BTC/USD": [{"t": "2026-04-10T00:00:00Z", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10}]}}
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps(payload).encode("utf-8")
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=fake_response) as mocked_urlopen:
            rows = client.get_market_data(asset, limit=1)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["close"], 1.5)
        request = mocked_urlopen.call_args.args[0]
        self.assertIn("/v1beta3/crypto/us/bars", request.full_url)

    def test_place_order_and_positions_delegate_to_rest_client(self) -> None:
        cfg = AlpacaConfig(api_key_id="key", api_secret_key="secret")
        client = AlpacaClient(cfg)
        client._http.submit_market_order = MagicMock(return_value={"id": "order-1"})  # type: ignore[attr-defined]
        client._http.get_positions = MagicMock(return_value=[{"symbol": "BTC/USD", "qty": "0.1"}])  # type: ignore[attr-defined]

        order = client.place_order("BTC/USD", 0.1, "buy", client_order_id="abc")
        positions = client.get_positions()

        self.assertEqual(order["id"], "order-1")
        self.assertEqual(positions[0]["symbol"], "BTC/USD")

    def test_stream_market_data_does_not_mutate_config(self) -> None:
        cfg = AlpacaConfig(api_key_id="key", api_secret_key="secret", symbols=["SPY"])
        client = AlpacaClient(cfg)
        asset = resolve_asset_config(symbol="BTC/USD")

        class _Tick:
            timestamp = __import__("datetime").datetime(2026, 4, 10, tzinfo=__import__("datetime").timezone.utc)
            price = 1.0
            volume = 2.0

        async def fake_stream(_cfg):
            yield _Tick()

        with patch("src.miniqs.data.stream.stream_alpaca_ticks", side_effect=fake_stream):
            async def collect() -> list[dict[str, float | int]]:
                items = []
                async for candle in client.stream_market_data(asset):
                    items.append(candle)
                return items

            rows = asyncio.run(collect())

        self.assertEqual(cfg.symbols, ["SPY"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["close"], 1.0)

    def test_subscribe_to_live_raises_inside_running_loop(self) -> None:
        cfg = AlpacaConfig(api_key_id="key", api_secret_key="secret")
        client = AlpacaClient(cfg)
        asset = resolve_asset_config(symbol="BTC/USD")

        async def run() -> None:
            with self.assertRaises(RuntimeError):
                client.subscribe_to_live(asset, lambda _candle: None)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()