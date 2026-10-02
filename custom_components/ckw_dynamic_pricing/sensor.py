"""Sensor platform for CKW Dynamic Pricing."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import DOMAIN, CKWPricingCoordinator
from .entity import CKWEntity
from .price import (
    TIMEZONE,
    entry_value,
    find_window,
    get_current_price,
    get_next_slot,
    rank_percent,
)

UNIT = "CHF/kWh"


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _window(data: dict, now: datetime, hours: int, cheapest: bool):
    return find_window(data["prices"], hours, now, cheapest)


def _window_start(hours: int, cheapest: bool) -> Callable[[dict, datetime], Any]:
    def value(data: dict, now: datetime) -> datetime | None:
        window = _window(data, now, hours, cheapest)
        return window.start if window else None

    return value


def _window_attrs(hours: int, cheapest: bool) -> Callable[[dict, datetime], dict]:
    def attrs(data: dict, now: datetime) -> dict:
        window = _window(data, now, hours, cheapest)
        if window is None:
            return {}
        return {
            "end": window.end.astimezone(TIMEZONE).isoformat(),
            "avg_price": window.avg_price,
        }

    return attrs


def _next_price(data: dict, now: datetime) -> float | None:
    slot = get_next_slot(data["prices"], now)
    return None if slot is None else _round(slot.value)


def _next_price_attrs(data: dict, now: datetime) -> dict:
    slot = get_next_slot(data["prices"], now)
    if slot is None:
        return {}
    return {"starts_at": slot.start.astimezone(TIMEZONE).isoformat()}


def _all_prices_attrs(data: dict, now: datetime) -> dict:
    formatted = []
    for entry in data["prices"]:
        value = entry_value(entry)
        if value is None or "start_timestamp" not in entry or "end_timestamp" not in entry:
            continue
        formatted.append(
            {
                "start": entry["start_timestamp"],
                "end": entry["end_timestamp"],
                "price": round(value, 4),
            }
        )
    return {"prices": formatted}


def _tomorrow(key: str) -> Callable[[dict, datetime], float | None]:
    return lambda data, now: (data.get("tomorrow") or {}).get(key)


@dataclass(frozen=True, kw_only=True)
class CKWSensorDescription(SensorEntityDescription):
    """Sensor description with value and attribute functions."""

    value_fn: Callable[[dict, datetime], Any]
    attrs_fn: Callable[[dict, datetime], dict] | None = None


def _price(key: str, icon: str, value_fn, **kwargs) -> CKWSensorDescription:
    return CKWSensorDescription(
        key=key,
        translation_key=key,
        icon=icon,
        native_unit_of_measurement=UNIT,
        value_fn=value_fn,
        **kwargs,
    )


SENSORS: tuple[CKWSensorDescription, ...] = (
    _price(
        "current_price",
        "mdi:lightning-bolt",
        lambda d, n: _round(get_current_price(d["prices"], n)),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    _price("min_price", "mdi:arrow-down", lambda d, n: d.get("min_price")),
    _price("max_price", "mdi:arrow-up", lambda d, n: d.get("max_price")),
    _price("avg_price", "mdi:chart-line", lambda d, n: d.get("avg_price")),
    _price("min_price_tomorrow", "mdi:arrow-down", _tomorrow("min_price")),
    _price("max_price_tomorrow", "mdi:arrow-up", _tomorrow("max_price")),
    _price("avg_price_tomorrow", "mdi:chart-line", _tomorrow("avg_price")),
    _price(
        "next_price",
        "mdi:skip-next",
        _next_price,
        attrs_fn=_next_price_attrs,
    ),
    _price(
        "price_in_one_hour",
        "mdi:clock-fast",
        lambda d, n: _round(get_current_price(d["prices"], n + timedelta(hours=1))),
    ),
    CKWSensorDescription(
        key="price_rank",
        translation_key="price_rank",
        icon="mdi:podium",
        native_unit_of_measurement="%",
        value_fn=lambda d, n: rank_percent(d["prices"], n),
    ),
    *(
        CKWSensorDescription(
            key=key,
            translation_key=key,
            icon=icon,
            device_class=SensorDeviceClass.TIMESTAMP,
            value_fn=_window_start(hours, cheapest),
            attrs_fn=_window_attrs(hours, cheapest),
        )
        for key, icon, hours, cheapest in (
            ("cheapest_2h_window", "mdi:clock-check", 2, True),
            ("cheapest_4h_window", "mdi:clock-check", 4, True),
            ("most_expensive_2h_window", "mdi:clock-alert", 2, False),
        )
    ),
    CKWSensorDescription(
        key="all_prices",
        translation_key="all_prices",
        icon="mdi:format-list-bulleted",
        value_fn=lambda d, n: len(d["prices"]),
        attrs_fn=_all_prices_attrs,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor platform."""
    coordinator: CKWPricingCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(CKWSensor(coordinator, entry, d) for d in SENSORS)


class CKWSensor(CKWEntity, SensorEntity):
    """A CKW price sensor computed from the cached prices."""

    entity_description: CKWSensorDescription
    # Up to ~192 slots; keep them out of the recorder database
    _unrecorded_attributes = frozenset({"prices"})

    @property
    def native_value(self) -> Any:
        """Return the state computed for the current time."""
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(
            self.coordinator.data, datetime.now(TIMEZONE)
        )

    @property
    def extra_state_attributes(self) -> dict | None:
        """Return the attributes for sensors that have any."""
        if not self.coordinator.data or self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(
            self.coordinator.data, datetime.now(TIMEZONE)
        )
