"""Coordinator tests: retry interval, cached prices for tomorrow, day rollover.

Home Assistant and aiohttp are replaced by minimal stand-ins so the coordinator
logic can run without installing them.
"""
import asyncio
import importlib.util
import sys
import types
import unittest
from datetime import datetime, time, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ckw_dynamic_pricing"


class UpdateFailed(Exception):
    """Stand-in for homeassistant's UpdateFailed."""


class DataUpdateCoordinator:
    """Stand-in for homeassistant's DataUpdateCoordinator."""

    def __init__(self, hass, logger, name, update_interval):
        self.update_interval = update_interval
        self.data = None
        self.hass = hass
        self.listener_updates = 0
        self.refresh_requests = 0

    def async_set_updated_data(self, data):
        self.data = data

    def async_update_listeners(self):
        self.listener_updates += 1

    async def async_request_refresh(self):
        self.refresh_requests += 1


def _stub(name, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    sys.modules[name] = module
    return module


def _load_package():
    _stub("aiohttp", ClientSession=object, ClientError=Exception, ClientTimeout=object)
    _stub("homeassistant")
    _stub("homeassistant.config_entries", ConfigEntry=object)
    _stub("homeassistant.core", HomeAssistant=object, callback=lambda func: func)
    _stub("homeassistant.helpers")
    _stub("homeassistant.helpers.entity_registry")
    sys.modules["homeassistant.helpers"].entity_registry = sys.modules[
        "homeassistant.helpers.entity_registry"
    ]
    _stub("homeassistant.helpers.aiohttp_client", async_get_clientsession=lambda hass: None)
    _stub("homeassistant.helpers.event", async_track_time_change=lambda *a, **k: None)
    _stub(
        "homeassistant.helpers.update_coordinator",
        DataUpdateCoordinator=DataUpdateCoordinator,
        UpdateFailed=UpdateFailed,
    )
    spec = importlib.util.spec_from_file_location(
        "ckw_pkg",
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["ckw_pkg"] = module
    spec.loader.exec_module(module)
    return module


class RetryIntervalTest(unittest.TestCase):
    def setUp(self):
        self.pkg = _load_package()
        self.coordinator = self.pkg.CKWPricingCoordinator(None, types.SimpleNamespace(data={}, options={}))

    def test_failure_switches_to_retry_interval_and_success_back(self):
        coordinator = self.coordinator
        coordinator._fetch_all = AsyncMock(side_effect=UpdateFailed("down"))
        with self.assertRaises(UpdateFailed):
            asyncio.run(coordinator._async_update_data())
        self.assertEqual(coordinator.update_interval, timedelta(minutes=15))

        coordinator._fetch_all = AsyncMock(return_value={"ok": True, "tomorrow": {"min_price": 0.1}})
        self.assertEqual(asyncio.run(coordinator._async_update_data()), {"ok": True, "tomorrow": {"min_price": 0.1}})
        self.assertEqual(coordinator.update_interval, timedelta(hours=6))


def _entries(day, values):
    """One hourly entry per value, beginning at midnight of the given day."""
    tz = sys.modules["ckw_pkg.price"].TIMEZONE
    start = datetime.combine(day, time(0, 0), tzinfo=tz)
    return [
        {
            "start_timestamp": (start + timedelta(hours=i)).isoformat(),
            "end_timestamp": (start + timedelta(hours=i + 1)).isoformat(),
            "integrated": [{"value": value}],
        }
        for i, value in enumerate(values)
    ]


class CacheAndRolloverTest(unittest.TestCase):
    def setUp(self):
        self.pkg = _load_package()
        self.coordinator = self.pkg.CKWPricingCoordinator(
            None, types.SimpleNamespace(data={}, options={})
        )
        self.today = datetime.now(self.pkg.TIMEZONE).date()
        self.tomorrow = self.today + timedelta(days=1)

    def _fetch(self, today, tomorrow):
        self.coordinator._fetch_day = AsyncMock(side_effect=[today, tomorrow])
        return asyncio.run(self.coordinator._fetch_all())

    def test_failed_tomorrow_fetch_keeps_cached_tomorrow(self):
        today = _entries(self.today, [0.2] * 24)
        self.coordinator.data = self._fetch(today, _entries(self.tomorrow, [0.1] * 24))
        self.assertEqual(self.coordinator.data["tomorrow"]["avg_price"], 0.1)
        data = self._fetch(today, [])
        self.assertEqual(data["tomorrow"]["avg_price"], 0.1)
        self.assertEqual(len(data["prices"]), 48)

    def test_missing_tomorrow_without_cache_stays_empty(self):
        data = self._fetch(_entries(self.today, [0.2] * 24), [])
        self.assertIsNone(data["tomorrow"])
        self.assertEqual(data["day"], self.today)

    def test_new_hour_on_same_day_only_updates_listeners(self):
        coordinator = self.coordinator
        coordinator.data = self._fetch(_entries(self.today, [0.2] * 24), [])
        asyncio.run(coordinator.async_new_hour(None))
        self.assertEqual(coordinator.listener_updates, 1)
        self.assertEqual(coordinator.refresh_requests, 0)

    def test_new_day_rolls_over_from_cache_and_resets_interval(self):
        coordinator = self.coordinator
        yesterday = self.today - timedelta(days=1)
        prices = _entries(yesterday, [0.3] * 24) + _entries(self.today, [0.1] * 24)
        coordinator.data = {"day": yesterday, "avg_price": 0.3, "prices": prices}
        coordinator.update_interval = timedelta(minutes=15)
        asyncio.run(coordinator.async_new_hour(None))
        self.assertEqual(coordinator.data["day"], self.today)
        self.assertEqual(coordinator.data["avg_price"], 0.1)
        self.assertIsNone(coordinator.data["tomorrow"])
        self.assertEqual(coordinator.refresh_requests, 0)
        expected = self.pkg.next_refresh_interval(
            datetime.now(self.pkg.TIMEZONE), False
        )
        self.assertAlmostEqual(
            coordinator.update_interval.total_seconds(), expected.total_seconds(), delta=5
        )

    def test_new_day_without_cached_prices_requests_refresh(self):
        coordinator = self.coordinator
        yesterday = self.today - timedelta(days=1)
        coordinator.data = {"day": yesterday, "prices": _entries(yesterday, [0.3] * 24)}
        asyncio.run(coordinator.async_new_hour(None))
        self.assertEqual(coordinator.refresh_requests, 1)
        self.assertEqual(coordinator.data["day"], yesterday)


if __name__ == "__main__":
    unittest.main()
