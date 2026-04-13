import unittest

from src.miniqs.data.data_feed import DataFeed, Tick


class TestDataFeed(unittest.TestCase):
    def test_simulated_stream_produces_ticks(self) -> None:
        feed = DataFeed(symbol="TEST", mode="simulated", seed=7)
        stream = feed.stream()

        ticks = [next(stream) for _ in range(3)]

        self.assertEqual(len(ticks), 3)
        for tick in ticks:
            self.assertIsInstance(tick, Tick)
            self.assertEqual(tick.symbol, "TEST")
            self.assertGreater(tick.price, 0)
            self.assertGreaterEqual(tick.volume, 1.0)

    def test_live_mode_blocked_by_default(self) -> None:
        with self.assertRaises(PermissionError):
            DataFeed(symbol="TEST", mode="live", allow_live=False)

    def test_invalid_mode_rejected(self) -> None:
        with self.assertRaises(ValueError):
            DataFeed(symbol="TEST", mode="paper")

    def test_start_get_stop_feed_api(self) -> None:
        feed = DataFeed(symbol="TEST", mode="simulated", seed=7)
        ticks = feed.start_feed(tick_count=5)

        self.assertEqual(len(ticks), 5)
        for tick in ticks:
            self.assertIn("timestamp", tick)
            self.assertIn("mid_price", tick)
            self.assertGreater(tick["mid_price"], 0)

        latest = feed.get_latest_tick()
        self.assertIsNotNone(latest)
        assert latest is not None
        self.assertIn("timestamp", latest)
        self.assertIn("mid_price", latest)

        feed.stop_feed()


if __name__ == "__main__":
    unittest.main()
