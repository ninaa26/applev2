"""Work out when to wake next and why we woke this time."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

# An RTC wake that lands within this window of the expected time counts as scheduled.
WAKE_TOLERANCE = timedelta(minutes=5)


def parse_times(times: list[str]) -> list[time]:
    parsed = []
    for t in times:
        hh, mm = t.split(":")
        parsed.append(time(int(hh), int(mm)))
    return sorted(parsed)


def next_wake(now: datetime, times: list[str], tz: str, min_gap: timedelta = timedelta(minutes=2)) -> datetime:
    """Next scheduled local time strictly after now + min_gap, returned as an aware UTC datetime."""
    zone = ZoneInfo(tz)
    local_now = now.astimezone(zone)
    earliest = local_now + min_gap
    slots = parse_times(times)
    for day_offset in range(0, 3):
        day = (local_now + timedelta(days=day_offset)).date()
        for slot in slots:
            candidate = datetime.combine(day, slot, tzinfo=zone)
            if candidate > earliest:
                return candidate.astimezone(ZoneInfo("UTC"))
    raise ValueError("schedule has no times")


def wake_reason(now: datetime, expected_iso: str | None) -> str:
    """'scheduled' if we are close to the wake we asked for, otherwise 'manual'.

    A manual wake on the Pi 5 means someone pressed the power button, which we
    use as the "new liner installed" signal in the field.
    """
    if not expected_iso:
        return "manual"
    expected = datetime.fromisoformat(expected_iso)
    return "scheduled" if abs(now - expected) <= WAKE_TOLERANCE else "manual"
