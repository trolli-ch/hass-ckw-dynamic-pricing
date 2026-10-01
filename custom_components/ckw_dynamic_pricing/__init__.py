"""CKW Dynamic Pricing Integration for Home Assistant."""
import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Dict

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .price import TIMEZONE, get_day_prices

_LOGGER = logging.getLogger(__name__)

DOMAIN = "ckw_dynamic_pricing"
PLATFORMS = ["sensor", "binary_sensor"]
SCAN_INTERVAL = timedelta(hours=6)
DEFAULT_THRESHOLD = 0.25  # CHF/kWh


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up CKW Dynamic Pricing from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    coordinator = CKWPricingCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Switch the daily statistics over right after midnight without an API call
    entry.async_on_unload(
        async_track_time_change(
            hass, coordinator.async_midnight_rollover, hour=0, minute=0, second=5
        )
    )
    # Reload when the options (e.g. the price threshold) change
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry so changed options take effect."""
    await hass.config_entries.async_reload(entry.entry_id)


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
            data = self._process_data(
                prices_today, prices_all, self.data.get("threshold", DEFAULT_THRESHOLD)
            )
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
        except aiohttp.ClientError as err:
            _LOGGER.warning("Error fetching CKW data for date %s: %s", date, err)
            return []

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from CKW API for today and tomorrow."""
        threshold = float(self.config.get("price_threshold", DEFAULT_THRESHOLD))

        today = datetime.now(TIMEZONE).date()
        tomorrow = today + timedelta(days=1)

        try:
            async with aiohttp.ClientSession() as session:
                prices_today = await self._fetch_day(session, today)
                prices_tomorrow = await self._fetch_day(session, tomorrow)

            if not prices_today:
                raise UpdateFailed("No price data received from CKW API for today")

            combined = prices_today + prices_tomorrow
            return self._process_data(prices_today, combined, threshold)

        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error connecting to CKW API: {err}") from err

    def _process_data(self, prices_today: list, prices_all: list, threshold: float = DEFAULT_THRESHOLD) -> Dict[str, Any]:
        """Process API data."""
        if not prices_today:
            return {}

        today_prices = [
            entry["integrated"][0]["value"]
            for entry in prices_today
            if "integrated" in entry and entry["integrated"]
        ]

        if not today_prices:
            raise UpdateFailed("No price data found in API response")

        return {
            "min_price": round(min(today_prices) * 100, 4),
            "max_price": round(max(today_prices) * 100, 4),
            "avg_price": round(sum(today_prices) / len(today_prices) * 100, 4),
            "threshold": threshold,
            "prices": prices_all,
        }
