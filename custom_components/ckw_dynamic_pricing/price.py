"""Price helpers for CKW Dynamic Pricing."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Europe/Zurich")


def parse_timestamp(value: str) -> datetime | None:
    """Parse an API timestamp; naive values are interpreted as Swiss local time."""
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TIMEZONE)
    return parsed


def get_current_price(
    prices: list[dict[str, Any]], now: datetime | None = None
) -> float | None:
    """Return the price in CHF/kWh of the slot containing now, or None if there is none."""
    if now is None:
        now = datetime.now(TIMEZONE)
    for entry in prices:
        start = parse_timestamp(entry.get("start_timestamp"))
        end = parse_timestamp(entry.get("end_timestamp"))
        if start is None or end is None or not start <= now < end:
            continue
        try:
            return float(entry["integrated"][0]["value"])
        except (KeyError, IndexError, TypeError, ValueError):
            return None
    return None


def get_day_prices(prices: list[dict[str, Any]], day: date) -> list[dict[str, Any]]:
    """Return the slots starting on the given Swiss local date."""
    result = []
    for entry in prices:
        start = parse_timestamp(entry.get("start_timestamp"))
        if start is not None and start.astimezone(TIMEZONE).date() == day:
            result.append(entry)
    return result
