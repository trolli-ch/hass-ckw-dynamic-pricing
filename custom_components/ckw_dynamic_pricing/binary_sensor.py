"""Binary sensor platform for CKW Dynamic Pricing."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, CKWPricingCoordinator
from .entity import CKWEntity
from .price import TIMEZONE, find_window


@dataclass(frozen=True, kw_only=True)
class CKWBinarySensorDescription(BinarySensorEntityDescription):
    """Binary sensor that is on while inside a price window."""

    hours: int
    cheapest: bool


BINARY_SENSORS: tuple[CKWBinarySensorDescription, ...] = (
    CKWBinarySensorDescription(
        key="in_cheapest_2h_window",
        translation_key="in_cheapest_2h_window",
        icon="mdi:clock-check",
        hours=2,
        cheapest=True,
    ),
    CKWBinarySensorDescription(
        key="in_cheapest_4h_window",
        translation_key="in_cheapest_4h_window",
        icon="mdi:clock-check",
        hours=4,
        cheapest=True,
    ),
    CKWBinarySensorDescription(
        key="in_most_expensive_2h_window",
        translation_key="in_most_expensive_2h_window",
        icon="mdi:clock-alert",
        hours=2,
        cheapest=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensor platform."""
    coordinator: CKWPricingCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(CKWWindowBinarySensor(coordinator, entry, d) for d in BINARY_SENSORS)


class CKWWindowBinarySensor(CKWEntity, BinarySensorEntity):
    """On while the current time lies inside the cheapest / most expensive window."""

    entity_description: CKWBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        """Return True inside the window; unknown if there are no prices to rank."""
        if not self.coordinator.data:
            return None
        now = datetime.now(TIMEZONE)
        description = self.entity_description
        window = find_window(
            self.coordinator.data["prices"], description.hours, now, description.cheapest
        )
        if window is None:
            return None
        return window.start <= now < window.end
