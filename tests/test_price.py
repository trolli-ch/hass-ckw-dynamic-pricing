"""Tests for the current-price helper (run: python -m unittest discover tests)."""
import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "price", Path(__file__).parents[1] / "custom_components/ckw_dynamic_pricing/price.py"
)
price = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(price)


def slot(start, end, value):
    return {
        "start_timestamp": start,
        "end_timestamp": end,
        "integrated": [{"value": value}],
    }


class CurrentPriceTest(unittest.TestCase):
    def test_summer_time_slot(self):
        prices = [
            slot("2026-07-01T12:00:00+02:00", "2026-07-01T12:15:00+02:00", 0.12),
            slot("2026-07-01T12:15:00+02:00", "2026-07-01T12:30:00+02:00", 0.34),
        ]
        now = datetime(2026, 7, 1, 10, 20, tzinfo=timezone.utc)  # 12:20 local
        self.assertEqual(price.get_current_price(prices, now), 0.34)

    def test_no_matching_slot_returns_none(self):
        prices = [slot("2026-07-01T12:00:00+02:00", "2026-07-01T12:15:00+02:00", 0.12)]
        now = datetime(2026, 7, 1, 13, 0, tzinfo=timezone.utc)
        self.assertIsNone(price.get_current_price(prices, now))

    def test_empty_and_malformed(self):
        now = datetime.now(timezone.utc)
        self.assertIsNone(price.get_current_price([], now))
        self.assertIsNone(
            price.get_current_price([{"start_timestamp": "x", "end_timestamp": "y"}], now)
        )

    def test_naive_timestamps_are_swiss_local_time(self):
        prices = [slot("2026-07-01T12:00:00", "2026-07-01T12:15:00", 0.5)]
        now = datetime(2026, 7, 1, 10, 5, tzinfo=timezone.utc)  # 12:05 CEST
        self.assertEqual(price.get_current_price(prices, now), 0.5)

    def test_fetch_window_uses_zurich_offset(self):
        summer = datetime.combine(datetime(2026, 7, 1).date(), datetime.min.time(), tzinfo=price.TIMEZONE)
        winter = datetime.combine(datetime(2026, 12, 1).date(), datetime.min.time(), tzinfo=price.TIMEZONE)
        self.assertEqual(summer.utcoffset(), timedelta(hours=2))
        self.assertEqual(winter.utcoffset(), timedelta(hours=1))


if __name__ == "__main__":
    unittest.main()
