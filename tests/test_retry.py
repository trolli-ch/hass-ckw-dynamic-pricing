"""Check that a failed fetch switches to the 15-minute retry interval.

Home Assistant and aiohttp are replaced by minimal stand-ins so the coordinator
logic can run without installing them.
"""
import asyncio
import importlib.util
import sys
import types
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ckw_dynamic_pricing"


class UpdateFailed(Exception):
    """Stand-in for homeassistant's UpdateFailed."""


class DataUpdateCoordinator:
    """Stand-in for homeassistant's DataUpdateCoordinator."""

    def __init__(self, hass, logger, name, update_interval):
        self.update_interval = update_interval


def _stub(name, **attrs):
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    sys.modules[name] = module
    return module


def _load_package():
    _stub("aiohttp", ClientSession=object, ClientError=Exception, ClientTimeout=object)
    _stub("homeassistant")
    _stub("homeassistant.config_entries", ConfigEntry=object)
    _stub("homeassistant.core", HomeAssistant=object)
    _stub("homeassistant.helpers")
    _stub("homeassistant.helpers.entity_registry")
    sys.modules["homeassistant.helpers"].entity_registry = sys.modules[
        "homeassistant.helpers.entity_registry"
    ]
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

        coordinator._fetch_all = AsyncMock(return_value={"ok": True})
        self.assertEqual(asyncio.run(coordinator._async_update_data()), {"ok": True})
        self.assertEqual(coordinator.update_interval, timedelta(hours=6))


if __name__ == "__main__":
    unittest.main()
