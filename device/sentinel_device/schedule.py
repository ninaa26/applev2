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


def wake_reason(now: datetime, expected_iso: str | None, clean_halt: bool = True) -> str:
    """Why the board booted, from what the last cycle left in the state file.

    'scheduled'       close to the wake we asked for
    'manual'          earlier than that, after a cycle that powered the board off itself: someone
                      pressed the Pi 5 power button, the "new liner installed" signal in the field
    'power_restored'  later than that: with power the RTC alarm would have woken the board on time,
                      so it had none (flat battery, unplugged)
    'interrupted'     the last cycle never reached its power-off (power cut or killed mid-cycle)
    'first'           no earlier cycle on record

    Only 'manual' may start a new liner. Power that goes and comes back between two scheduled wakes,
    after a clean power-off (a battery swap), also comes out as 'manual': nothing on the board tells
    them apart. The server settles it from the photo: the old insects still in place means the liner
    was not changed (sentinel_server.pipeline.worker.same_liner_as_before).
    """
    if not expected_iso:
        return "first"
    expected = datetime.fromisoformat(expected_iso)
    if abs(now - expected) <= WAKE_TOLERANCE:
        return "scheduled"
    if not clean_halt:
        return "interrupted"
    return "power_restored" if now > expected else "manual"
