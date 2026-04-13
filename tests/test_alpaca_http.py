import json
import unittest
from unittest.mock import MagicMock, patch

from src.miniqs.execution.http import AlpacaPaperClient


class TestAlpacaPaperClient(unittest.TestCase):
    def test_versioned_trading_paths_use_v2_prefix(self) -> None:
        client = AlpacaPaperClient("key", "secret", base_url="https://paper-api.alpaca.markets", trading_api_version="V2")
        self.assertEqual(client.trading_api_version, "v2")
        self.assertEqual(client._trading_path("account"), "/v2/account")
        self.assertEqual(client._trading_path("orders/abc123"), "/v2/orders/abc123")

    def test_get_positions_uses_versioned_rest_path(self) -> None:
        client = AlpacaPaperClient("key", "secret", base_url="https://paper-api.alpaca.markets", trading_api_version="v2")
        response = [{"symbol": "BTC/USD", "qty": "0.01"}]
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps(response).encode("utf-8")
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=fake_response) as mocked_urlopen:
            result = client.get_positions()

        self.assertEqual(result, response)
        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://paper-api.alpaca.markets/v2/positions")

    def test_submit_market_order_uses_versioned_rest_path(self) -> None:
        client = AlpacaPaperClient("key", "secret", base_url="https://paper-api.alpaca.markets", trading_api_version="v2")
        response = {"id": "order-1"}
        fake_response = MagicMock()
        fake_response.read.return_value = json.dumps(response).encode("utf-8")
        fake_response.__enter__.return_value = fake_response
        fake_response.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=fake_response) as mocked_urlopen:
            result = client.submit_market_order("btc/usd", 0.01, "BUY")

        self.assertEqual(result, response)
        request = mocked_urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://paper-api.alpaca.markets/v2/orders")
        headers = {str(key).lower(): value for key, value in request.headers.items()}
        self.assertIn("apca-api-key-id", headers)
        self.assertIn("apca-api-secret-key", headers)


if __name__ == "__main__":
    unittest.main()
