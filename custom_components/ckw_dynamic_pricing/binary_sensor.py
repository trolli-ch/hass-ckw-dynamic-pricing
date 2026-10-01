"""Binary sensor platform for CKW Dynamic Pricing."""
import logging
from homeassistant.components.binary_sensor import BinarySensorEntity
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
    """Set up binary sensor platform."""
    coordinator: CKWPricingCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        CKWBelowThresholdBinarySensor(coordinator, entry),
    ]

    async_add_entities(entities)


class CKWBelowThresholdBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for CKW price below threshold."""

    def __init__(self, coordinator: CKWPricingCoordinator, entry: ConfigEntry) -> None:
        """Initialize the binary sensor."""
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
        """Write the state; the current price is recomputed from cached prices."""
        self.async_write_ha_state()

    @property
    def _current_price(self) -> float | None:
        """Return the current price in Rp./kWh, or None if unknown."""
        if not self.coordinator.data:
            return None
        price = get_current_price(self.coordinator.data.get("prices", []))
        return None if price is None else round(price * 100, 4)

    @property
    def unique_id(self) -> str:
        """Return unique id."""
        return f"{self.entry.entry_id}_below_threshold"

    @property
    def name(self) -> str:
        """Return the name of the binary sensor."""
        return "CKW Below Threshold"

    @property
    def is_on(self) -> bool:
        """Return True if price is below threshold; False if the price is unknown."""
        current_price = self._current_price
        if current_price is None:
            return False
        threshold = self.coordinator.data.get("threshold", 10)
        return current_price < threshold

    @property
    def icon(self) -> str:
        """Return the icon."""
        return "mdi:check-circle" if self.is_on else "mdi:close-circle"

    @property
    def extra_state_attributes(self) -> dict:
        """Return extra state attributes."""
        if self.coordinator.data:
            return {
                "current_price": self._current_price,
                "threshold": self.coordinator.data.get("threshold", 10),
            }
        return {}

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success
