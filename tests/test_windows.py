"""Tests for window search, rank, next slot, statistics and refresh interval."""
import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "price", Path(__file__).parents[1] / "custom_components/ckw_dynamic_pricing/price.py"
)
price = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(price)

BASE = datetime(2026, 7, 1, 8, 0, tzinfo=price.TIMEZONE)


def day(values, start=BASE):
    """One 15-minute slot per value, beginning at start."""
    out = []
    for i, value in enumerate(values):
        s = start + timedelta(minutes=15 * i)
        e = s + timedelta(minutes=15)
        out.append(
            {
                "start_timestamp": s.isoformat(),
                "end_timestamp": e.isoformat(),
                "integrated": [{"value": value}],
            }
        )
    return out


class WindowTest(unittest.TestCase):
    def setUp(self):
        # 16 slots = 4 hours; cheap block at slots 4-11, dear block at 0-3
        self.prices = day([0.5] * 4 + [0.1] * 8 + [0.3] * 4)

    def test_cheapest_window(self):
        w = price.find_window(self.prices, 2, BASE)
        self.assertEqual(w.start, BASE + timedelta(hours=1))
        self.assertEqual(w.end, BASE + timedelta(hours=3))
        self.assertEqual(w.avg_price, 0.1)

    def test_most_expensive_window(self):
        w = price.find_window(self.prices, 2, BASE, cheapest=False)
        self.assertEqual(w.start, BASE)
        # 0.5 for 1 h then 0.1 for 1 h
        self.assertEqual(w.avg_price, 0.3)

    def test_past_slots_are_ignored(self):
        now = BASE + timedelta(hours=3, minutes=10)
        w = price.find_window(self.prices, 2, now)
        self.assertIsNone(w)  # only ~50 min left
        w = price.find_window(self.prices, 0.5, now)
        self.assertEqual(w.avg_price, 0.3)

    def test_window_includes_current_slot(self):
        now = BASE + timedelta(hours=1, minutes=20)
        w = price.find_window(self.prices, 2, now)
        self.assertEqual(w.start, BASE + timedelta(hours=1, minutes=15))

    def test_gap_breaks_window(self):
        prices = day([0.1] * 4) + day([0.1] * 4, BASE + timedelta(hours=2))
        self.assertIsNone(price.find_window(prices, 2, BASE))

    def test_no_prices(self):
        self.assertIsNone(price.find_window([], 2, BASE))


class RankStatsTest(unittest.TestCase):
    def test_rank_percent(self):
        prices = day([0.1, 0.2, 0.3, 0.4, 0.5])
        self.assertEqual(price.rank_percent(prices, BASE), 0.0)
        self.assertEqual(price.rank_percent(prices, BASE + timedelta(hours=1)), 100.0)
        self.assertEqual(price.rank_percent(prices, BASE + timedelta(minutes=30)), 50.0)
        self.assertIsNone(price.rank_percent(prices, BASE + timedelta(days=1)))

    def test_next_slot(self):
        prices = day([0.1, 0.2, 0.3])
        slot = price.get_next_slot(prices, BASE + timedelta(minutes=5))
        self.assertEqual((slot.start, slot.value), (BASE + timedelta(minutes=15), 0.2))
        self.assertIsNone(price.get_next_slot(prices, BASE + timedelta(minutes=30)))

    def test_day_stats(self):
        stats = price.day_stats(day([0.1, 0.3]) + [{"start_timestamp": "bad"}])
        self.assertEqual(stats, {"min_price": 0.1, "max_price": 0.3, "avg_price": 0.2})
        self.assertIsNone(price.day_stats([]))


class RefreshIntervalTest(unittest.TestCase):
    def test_tomorrow_present_uses_normal_interval(self):
        now = datetime(2026, 7, 1, 19, 0, tzinfo=price.TIMEZONE)
        self.assertEqual(price.next_refresh_interval(now, True), timedelta(hours=6))

    def test_missing_tomorrow_after_publish_hour_retries(self):
        now = datetime(2026, 7, 1, 19, 0, tzinfo=price.TIMEZONE)
        self.assertEqual(price.next_refresh_interval(now, False), timedelta(minutes=30))

    def test_missing_tomorrow_before_publish_hour_wakes_at_publish_hour(self):
        now = datetime(2026, 7, 1, 16, 30, tzinfo=price.TIMEZONE)
        self.assertEqual(price.next_refresh_interval(now, False), timedelta(hours=1, minutes=30))
        now = datetime(2026, 7, 1, 6, 0, tzinfo=price.TIMEZONE)
        self.assertEqual(price.next_refresh_interval(now, False), timedelta(hours=6))

    def test_works_with_utc_now(self):
        now = datetime(2026, 7, 1, 17, 30, tzinfo=timezone.utc)  # 19:30 local
        self.assertEqual(price.next_refresh_interval(now, False), timedelta(minutes=30))


if __name__ == "__main__":
    unittest.main()
