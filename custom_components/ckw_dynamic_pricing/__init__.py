"""CKW Dynamic Pricing Integration for Home Assistant."""
import asyncio
import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Dict

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .price import TIMEZONE, day_stats, get_day_prices, next_refresh_interval

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ckw_dynamic_pricing"
PLATFORMS = ["sensor", "binary_sensor"]
SCAN_INTERVAL = timedelta(hours=6)
RETRY_INTERVAL = timedelta(minutes=15)  # used after a failed API fetch


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up CKW Dynamic Pricing from a config entry."""
    # Version 2.0.0b4 removed the below-threshold binary sensor
    registry = er.async_get(hass)
    obsolete = registry.async_get_entity_id(
        "binary_sensor", DOMAIN, f"{entry.entry_id}_below_threshold"
    )
    if obsolete:
        registry.async_remove(obsolete)

    hass.data.setdefault(DOMAIN, {})
    coordinator = CKWPricingCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Re-evaluate all price states whenever a 15-minute slot starts (no API call)
    @callback
    def _quarter_hour(now: datetime) -> None:
        coordinator.async_update_listeners()

    entry.async_on_unload(
        async_track_time_change(
            hass, _quarter_hour, minute=(0, 15, 30, 45), second=5
        )
    )
    # Switch the daily statistics over right after midnight without an API call
    entry.async_on_unload(
        async_track_time_change(
            hass, coordinator.async_midnight_rollover, hour=0, minute=0, second=5
        )
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


class CKWPricingCoordinator(DataUpdateCoordinator):
    """Coordinator for CKW pricing data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.entry = entry
        self.api_url = "https://e-ckw-public-data.de-c1.eu1.cloudhub.io/api/v1/netzinformationen/energie/dynamische-preise"

    @property
    def config(self) -> Dict[str, Any]:
        """Return the entry data overlaid with the options."""
        return {**self.entry.data, **self.entry.options}

    async def async_midnight_rollover(self, now: datetime) -> None:
        """Promote tomorrow's cached prices to today's statistics after midnight."""
        if not self.data:
            return
        today: date = datetime.now(TIMEZONE).date()
        prices_all = self.data.get("prices", [])
        prices_today = get_day_prices(prices_all, today)
        try:
            if not prices_today:
                raise UpdateFailed("No cached prices for the new day")
            data = self._process_data(prices_today, prices_all)
        except UpdateFailed:
            await self.async_request_refresh()
            return
        self.async_set_updated_data(data)

    async def _fetch_day(self, session: aiohttp.ClientSession, date) -> list:
        """Fetch prices for a specific date."""
        start = datetime.combine(date, time(0, 0), tzinfo=TIMEZONE).isoformat()
        end = datetime.combine(date, time(23, 59), tzinfo=TIMEZONE).isoformat()
        params = {
            "tariff_name": self.config.get("tariff_name", "home_dynamic"),
            "start_timestamp": start,
            "end_timestamp": end,
            "tariff_type": "integrated",
        }
        try:
            async with session.get(
                self.api_url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("CKW API returned %s for date %s", resp.status, date)
                    return []
                data = await resp.json()
                return data.get("prices", [])
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.warning("Error fetching CKW data for date %s: %r", date, err)
            return []

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data, polling again after 15 minutes if the API fails."""
        try:
            data = await self._fetch_all()
        except UpdateFailed:
            self.update_interval = RETRY_INTERVAL
            raise
        # Poll sooner while tomorrow's prices are still unpublished
        self.update_interval = next_refresh_interval(
            datetime.now(TIMEZONE), bool(data.get("tomorrow"))
        )
        return data

    async def _fetch_all(self) -> Dict[str, Any]:
        """Fetch data from CKW API for today and tomorrow."""
        today = datetime.now(TIMEZONE).date()
        tomorrow = today + timedelta(days=1)

        try:
            # Shared HA session (no new SSL context per fetch), both days in parallel
            session = async_get_clientsession(self.hass)
            prices_today, prices_tomorrow = await asyncio.gather(
                self._fetch_day(session, today),
                self._fetch_day(session, tomorrow),
            )

            if not prices_today:
                raise UpdateFailed("No price data received from CKW API for today")

            combined = prices_today + prices_tomorrow
            return self._process_data(prices_today, combined)

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error connecting to CKW API: {err}") from err

    def _process_data(self, prices_today: list, prices_all: list) -> Dict[str, Any]:
        """Process API data."""
        if not prices_today:
            return {}

        today_stats = day_stats(prices_today)
        if today_stats is None:
            raise UpdateFailed("No price data found in API response")

        tomorrow = datetime.now(TIMEZONE).date() + timedelta(days=1)
        return {
            **today_stats,
            "tomorrow": day_stats(get_day_prices(prices_all, tomorrow)),
            "prices": prices_all,
        }
