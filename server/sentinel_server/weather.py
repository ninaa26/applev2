"""Air temperature and humidity from a weather service, for photos whose camera has no sensor (the ESP32s).

Open-Meteo (https://open-meteo.com): free, no key. The reading for a photo is the service's hourly value
nearest the time it was taken, at the location of its trap or, failing that, of its hub. It is kept in the
photo's meta["weather"], apart from temp_c / rh, so it is never taken for the trap's own sensor (the degree
days fall back on that sensor).
"""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Capture, Trap, utcnow

log = logging.getLogger(__name__)

URL = "https://api.open-meteo.com/v1/forecast"
SOURCE = "Open-Meteo"
LOOK_BACK = timedelta(days=60)  # older photos are left as they are: the backfill is for recent ones
TIMEOUT_S = 10


def location(db: Session, trap: Trap) -> tuple[float, float] | None:
    """Where the trap is: its own location, or its hub's (ESP32 cameras are in Wi-Fi range of their hub)."""
    if trap.lat is not None and trap.lon is not None:
        return trap.lat, trap.lon
    hub = db.get(Trap, trap.hub_id) if trap.hub_id else None
    if hub is not None and hub.lat is not None and hub.lon is not None:
        return hub.lat, hub.lon
    return None


def parse_location(lat: str, lon: str) -> tuple[float | None, float | None]:
    """Form fields to (lat, lon); both empty is no location. Raises ValueError on anything else."""
    if not lat.strip() and not lon.strip():
        return None, None
    try:
        la, lo = float(lat), float(lon)
    except ValueError:
        raise ValueError("location: give both latitude and longitude as numbers, e.g. 42.45 and -76.48")
    if not (-90 <= la <= 90 and -180 <= lo <= 180):
        raise ValueError("location: latitude is -90 to 90 and longitude -180 to 180")
    return round(la, 4), round(lo, 4)


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=TIMEOUT_S) as r:
        return json.load(r)


def hourly(lat: float, lon: float, first: datetime, last: datetime) -> dict[datetime, tuple[float, float]]:
    """{hour (naive UTC): (temp °C, relative humidity %)} for the days from `first` to `last`."""
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "hourly": "temperature_2m,relative_humidity_2m", "timezone": "GMT",
        "start_date": first.date().isoformat(), "end_date": last.date().isoformat(),
    })
    h = _get_json(f"{URL}?{q}")["hourly"]
    return {datetime.fromisoformat(t): (tc, rh)
            for t, tc, rh in zip(h["time"], h["temperature_2m"], h["relative_humidity_2m"])
            if tc is not None and rh is not None}


def needs_weather(cap: Capture) -> bool:
    return cap.temp_c is None and cap.rh is None and "weather" not in (cap.meta or {})


def fill(db: Session, limit: int = 200) -> int:
    """Look up the weather for recent photos with no sensor reading. Returns how many were filled.
    A photo whose hour the service has no value for yet (it is still current) is tried again next time."""
    since = utcnow() - LOOK_BACK
    caps = [c for c in db.scalars(select(Capture).where(
        Capture.captured_at >= since, Capture.temp_c.is_(None), Capture.rh.is_(None))
        .order_by(Capture.captured_at.desc()).limit(limit * 5)) if needs_weather(c)][:limit]
    by_place: dict[tuple[float, float], list[Capture]] = {}
    for c in caps:
        where = location(db, db.get(Trap, c.trap_id))
        if where is not None:
            by_place.setdefault(where, []).append(c)
    done = 0
    for (lat, lon), group in by_place.items():
        try:
            hours = hourly(lat, lon, min(c.captured_at for c in group), max(c.captured_at for c in group))
        except Exception as e:  # offline, or the service is down: the photos wait for the next pass
            log.warning("weather for %.4f, %.4f: %s", lat, lon, e)
            continue
        for c in group:
            hour = (c.captured_at + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)
            if hour in hours and hour <= utcnow():
                tc, rh = hours[hour]
                c.meta = {**(c.meta or {}), "weather": {
                    "temp_c": tc, "rh": rh, "source": SOURCE, "at": hour.isoformat(), "lat": lat, "lon": lon}}
                done += 1
    return done
