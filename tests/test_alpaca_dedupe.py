import unittest

from src.miniqs.data.stream import dedupe_key_for_message


class TestAlpacaDedupe(unittest.TestCase):
    def test_trade_key(self) -> None:
        k = dedupe_key_for_message({"T": "t", "S": "SPY", "i": 12345})
        self.assertEqual(k, "trade:SPY:12345")

    def test_quote_key(self) -> None:
        k = dedupe_key_for_message({"T": "q", "S": "SPY", "bp": 100.0, "ap": 101.0, "t": "2024-01-01T00:00:00Z"})
        self.assertTrue(k.startswith("quote:SPY:"))


if __name__ == "__main__":
    unittest.main()
