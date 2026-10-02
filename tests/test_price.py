"""Tests for the current-price helper (run: python -m unittest discover tests)."""
import importlib.util
import unittest
from datetime import date, datetime, timedelta, timezone
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

    def test_get_day_prices_filters_by_swiss_local_date(self):
        prices = [
            slot("2026-07-01T23:45:00+02:00", "2026-07-02T00:00:00+02:00", 0.1),
            slot("2026-07-02T00:00:00+02:00", "2026-07-02T00:15:00+02:00", 0.2),
            slot("2026-07-02T00:15:00", "2026-07-02T00:30:00", 0.3),
            {"start_timestamp": "bad"},
        ]
        day = price.get_day_prices(prices, date(2026, 7, 2))
        self.assertEqual([e["integrated"][0]["value"] for e in day], [0.2, 0.3])


if __name__ == "__main__":
    unittest.main()


class HourlyTest(unittest.TestCase):
    def quarters(self, hour, values):
        return [
            slot(
                f"2026-07-01T{hour:02d}:{15 * i:02d}:00+02:00",
                f"2026-07-01T{hour:02d}:{15 * i + 15:02d}:00+02:00"
                if i < 3
                else f"2026-07-01T{hour + 1:02d}:00:00+02:00",
                v,
            )
            for i, v in enumerate(values)
        ]

    def test_identical_quarters_merge(self):
        hourly = price.to_hourly(self.quarters(12, [0.2] * 4) + self.quarters(13, [0.3] * 4))
        self.assertEqual(len(hourly), 2)
        slots = price.parse_slots(hourly)
        self.assertEqual(slots[0].end - slots[0].start, timedelta(hours=1))
        self.assertEqual([s.value for s in slots], [0.2, 0.3])

    def test_differing_quarters_kept(self):
        quarters = self.quarters(12, [0.2, 0.2, 0.3, 0.3])
        self.assertEqual(len(price.to_hourly(quarters)), 4)

    def test_incomplete_hour_kept(self):
        self.assertEqual(len(price.to_hourly(self.quarters(12, [0.2] * 4)[:3])), 3)

    def test_current_price_and_window(self):
        hourly = price.to_hourly(
            self.quarters(10, [0.3] * 4) + self.quarters(11, [0.1] * 4) + self.quarters(12, [0.2] * 4)
        )
        now = datetime(2026, 7, 1, 8, 20, tzinfo=timezone.utc)  # 10:20 local
        self.assertEqual(price.get_current_price(hourly, now), 0.3)
        win = price.find_window(hourly, 2, now)
        self.assertAlmostEqual(win.avg_price, 0.15)
