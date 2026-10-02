"""Shared base entity for CKW Dynamic Pricing."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN, CKWPricingCoordinator


class CKWEntity(CoordinatorEntity[CKWPricingCoordinator]):
    """Base class: one device, translated names, availability from the price cache."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CKWPricingCoordinator,
        entry: ConfigEntry,
        description: EntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        # unique ids stay as in earlier versions so entity ids are kept
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="CKW",
            manufacturer="CKW",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        """Stay available while cached prices exist, even if the last fetch failed."""
        return bool(self.coordinator.data)
