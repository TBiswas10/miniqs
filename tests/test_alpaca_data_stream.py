import unittest

from alpaca_data_stream import alpaca_message_to_tick


class TestAlpacaMessageToTick(unittest.TestCase):
    def test_quote_fields_are_preserved(self) -> None:
        tick = alpaca_message_to_tick(
            {
                "T": "q",
                "S": "SPY",
                "bp": 500.10,
                "ap": 500.14,
                "bs": 12,
                "as": 20,
                "t": "2026-01-01T12:00:00.123456Z",
            }
        )

        self.assertIsNotNone(tick)
        assert tick is not None
        self.assertEqual(tick.message_type, "q")
        self.assertEqual(tick.bid_price, 500.10)
        self.assertEqual(tick.ask_price, 500.14)
        self.assertEqual(tick.bid_size, 12.0)
        self.assertEqual(tick.ask_size, 20.0)
        self.assertIsNone(tick.trade_size)
        self.assertAlmostEqual(tick.price, 500.12, places=6)


if __name__ == "__main__":
    unittest.main()
