"""Sensor platform for CKW Dynamic Pricing."""
import logging
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import CKWPricingCoordinator, DOMAIN
from .price import get_current_price

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""
    coordinator: CKWPricingCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        CKWCurrentPriceSensor(coordinator, entry),
        CKWMinPriceSensor(coordinator, entry),
        CKWMaxPriceSensor(coordinator, entry),
        CKWAvgPriceSensor(coordinator, entry),
        CKWAllPricesSensor(coordinator, entry),
    ]

    async_add_entities(entities)


class CKWPriceSensorBase(CoordinatorEntity, SensorEntity):
    """Base class for CKW price sensors."""

    def __init__(self, coordinator: CKWPricingCoordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entry = entry

    async def async_added_to_hass(self) -> None:
        """Re-evaluate the state whenever a 15-minute price slot starts."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(
                self.hass,
                self._handle_time_change,
                minute=(0, 15, 30, 45),
                second=5,
            )
        )

    @callback
    def _handle_time_change(self, now) -> None:
        """Write the state; the time-dependent value is recomputed from cached prices."""
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success


class CKWCurrentPriceSensor(CKWPriceSensorBase):
    """Sensor for current CKW price."""

    @property
    def unique_id(self) -> str:
        """Return unique id."""
        return f"{self.entry.entry_id}_current_price"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "CKW Current Price"

    @property
    def native_value(self) -> float | None:
        """Return the current price, or None if no slot covers the current time."""
        if not self.coordinator.data:
            return None
        price = get_current_price(self.coordinator.data.get("prices", []))
        return None if price is None else round(price, 4)

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return "CHF/kWh"

    @property
    def icon(self) -> str:
        """Return the icon."""
        return "mdi:lightning-bolt"

    @property
    def state_class(self) -> SensorStateClass:
        """Return the state class."""
        return SensorStateClass.MEASUREMENT


class CKWMinPriceSensor(CKWPriceSensorBase):
    """Sensor for minimum CKW price."""

    @property
    def unique_id(self) -> str:
        """Return unique id."""
        return f"{self.entry.entry_id}_min_price"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "CKW Min Price"

    @property
    def native_value(self) -> float:
        """Return the state of the sensor."""
        if self.coordinator.data:
            return round(self.coordinator.data.get("min_price", 0) / 100, 4)
        return 0

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return "CHF/kWh"

    @property
    def icon(self) -> str:
        """Return the icon."""
        return "mdi:arrow-down"


class CKWMaxPriceSensor(CKWPriceSensorBase):
    """Sensor for maximum CKW price."""

    @property
    def unique_id(self) -> str:
        """Return unique id."""
        return f"{self.entry.entry_id}_max_price"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "CKW Max Price"

    @property
    def native_value(self) -> float:
        """Return the state of the sensor."""
        if self.coordinator.data:
            return round(self.coordinator.data.get("max_price", 0) / 100, 4)
        return 0

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return "CHF/kWh"

    @property
    def icon(self) -> str:
        """Return the icon."""
        return "mdi:arrow-up"


class CKWAvgPriceSensor(CKWPriceSensorBase):
    """Sensor for average CKW price."""

    @property
    def unique_id(self) -> str:
        """Return unique id."""
        return f"{self.entry.entry_id}_avg_price"

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "CKW Avg Price"

    @property
    def native_value(self) -> float:
        """Return the state of the sensor."""
        if self.coordinator.data:
            return round(self.coordinator.data.get("avg_price", 0) / 100, 4)
        return 0

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return "CHF/kWh"

    @property
    def icon(self) -> str:
        """Return the icon."""
        return "mdi:chart-line"


class CKWAllPricesSensor(CKWPriceSensorBase):
    """Sensor for all CKW prices of the day."""

    @property
    def unique_id(self) -> str:
        return f"{self.entry.entry_id}_all_prices"

    @property
    def name(self) -> str:
        return "CKW All Prices"

    @property
    def native_value(self) -> int:
        """Return number of price entries."""
        if self.coordinator.data:
            return len(self.coordinator.data.get("prices", []))
        return 0

    @property
    def native_unit_of_measurement(self) -> str:
        return "Einträge"

    @property
    def icon(self) -> str:
        return "mdi:format-list-bulleted"

    @property
    def extra_state_attributes(self) -> dict:
        if not self.coordinator.data:
            return {}
        prices = self.coordinator.data.get("prices", [])
        formatted = []
        for entry in prices:
            try:
                formatted.append({
                    "start": entry["start_timestamp"],
                    "end": entry["end_timestamp"],
                    "price": round(entry["integrated"][0]["value"], 4),
                })
            except (KeyError, IndexError):
                continue
        return {"prices": formatted}
