"""Price helpers for CKW Dynamic Pricing."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("Europe/Zurich")

# CKW publishes tomorrow's prices from noon; poll more often from then on
PUBLISH_HOUR = 12
NORMAL_INTERVAL = timedelta(hours=6)
TOMORROW_RETRY_INTERVAL = timedelta(minutes=15)


class Slot(NamedTuple):
    """One price slot."""

    start: datetime
    end: datetime
    value: float


class Window(NamedTuple):
    """A run of consecutive slots with its average price."""

    start: datetime
    end: datetime
    avg_price: float


def parse_timestamp(value: str) -> datetime | None:
    """Parse an API timestamp; naive values are interpreted as Swiss local time."""
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TIMEZONE)
    return parsed


def entry_value(entry: dict[str, Any]) -> float | None:
    """Return the integrated price of an API entry, or None if it is malformed."""
    try:
        return float(entry["integrated"][0]["value"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def parse_slots(prices: list[dict[str, Any]]) -> list[Slot]:
    """Return the valid slots sorted by start time."""
    slots = []
    for entry in prices:
        start = parse_timestamp(entry.get("start_timestamp"))
        end = parse_timestamp(entry.get("end_timestamp"))
        value = entry_value(entry)
        if start is None or end is None or value is None or end <= start:
            continue
        slots.append(Slot(start, end, value))
    return sorted(slots)


def to_hourly(prices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge the 15-minute entries of each hour into one hourly entry.

    CKW only changes its prices once per hour, so the four quarter-hour values
    are identical. An hour whose values differ (or that is incomplete) is left
    as the original entries, so no information is ever dropped.
    """
    groups: dict[datetime, list[tuple[datetime, datetime, dict[str, Any]]]] = {}
    passthrough = []
    for entry in prices:
        start = parse_timestamp(entry.get("start_timestamp"))
        end = parse_timestamp(entry.get("end_timestamp"))
        if start is None or end is None or entry_value(entry) is None:
            passthrough.append(entry)
            continue
        hour = start.astimezone(TIMEZONE).replace(minute=0, second=0, microsecond=0)
        groups.setdefault(hour, []).append((start, end, entry))
    result = list(passthrough)
    for hour, items in groups.items():
        items.sort(key=lambda item: item[0])
        values = {entry_value(item[2]) for item in items}
        contiguous = all(a[1] == b[0] for a, b in zip(items, items[1:]))
        covers_hour = (
            items[0][0] == hour and items[-1][1] - items[0][0] == timedelta(hours=1)
        )
        if len(items) > 1 and len(values) == 1 and contiguous and covers_hour:
            first, last = items[0][2], items[-1][2]
            result.append(
                {
                    **first,
                    "start_timestamp": first["start_timestamp"],
                    "end_timestamp": last["end_timestamp"],
                }
            )
        else:
            result.extend(item[2] for item in items)
    return result


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
        return entry_value(entry)
    return None


def get_day_prices(prices: list[dict[str, Any]], day: date) -> list[dict[str, Any]]:
    """Return the slots starting on the given Swiss local date."""
    result = []
    for entry in prices:
        start = parse_timestamp(entry.get("start_timestamp"))
        if start is not None and start.astimezone(TIMEZONE).date() == day:
            result.append(entry)
    return result


def day_stats(entries: list[dict[str, Any]]) -> dict[str, float] | None:
    """Return min/max/avg price of the entries, or None if there is no valid price."""
    values = [v for v in map(entry_value, entries) if v is not None]
    if not values:
        return None
    return {
        "min_price": round(min(values), 4),
        "max_price": round(max(values), 4),
        "avg_price": round(sum(values) / len(values), 4),
    }


def get_next_slot(prices: list[dict[str, Any]], now: datetime) -> Slot | None:
    """Return the first slot that starts after now."""
    for slot in parse_slots(prices):
        if slot.start > now:
            return slot
    return None


def find_window(
    prices: list[dict[str, Any]], hours: float, now: datetime, cheapest: bool = True
) -> Window | None:
    """Return the cheapest (or most expensive) run of consecutive slots lasting `hours`.

    Only slots that have not ended yet are considered, so the window may have
    started already (it contains the current slot).
    """
    slots = [s for s in parse_slots(prices) if s.end > now]
    target = timedelta(hours=hours)
    best: Window | None = None
    for i, first in enumerate(slots):
        total = timedelta()
        cost = 0.0
        last = first
        for slot in slots[i:]:
            if slot is not first and slot.start != last.end:
                break  # gap in the data
            length = slot.end - slot.start
            total += length
            cost += slot.value * length.total_seconds()
            last = slot
            if total >= target:
                avg = round(cost / total.total_seconds(), 4)
                candidate = Window(first.start, last.end, avg)
                if (
                    best is None
                    or (cheapest and avg < best.avg_price)
                    or (not cheapest and avg > best.avg_price)
                ):
                    best = candidate
                break
    return best


def rank_percent(prices: list[dict[str, Any]], now: datetime) -> float | None:
    """Return where the current price sits among today's slots (0 = cheapest, 100 = dearest)."""
    current = get_current_price(prices, now)
    if current is None:
        return None
    day = [
        v
        for v in map(entry_value, get_day_prices(prices, now.astimezone(TIMEZONE).date()))
        if v is not None
    ]
    if len(day) < 2:
        return 0.0
    cheaper = sum(1 for v in day if v < current)
    return round(100 * cheaper / (len(day) - 1), 1)


def next_refresh_interval(now: datetime, has_tomorrow: bool) -> timedelta:
    """Return the time until the next API fetch after a successful one."""
    if has_tomorrow:
        return NORMAL_INTERVAL
    publish = now.astimezone(TIMEZONE).replace(
        hour=PUBLISH_HOUR, minute=0, second=0, microsecond=0
    )
    if now >= publish:
        return TOMORROW_RETRY_INTERVAL
    return min(NORMAL_INTERVAL, publish - now)
