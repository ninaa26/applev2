"""Air temperature and humidity from the National Weather Service, for photos whose camera has no sensor
(the ESP32s).

api.weather.gov (https://www.weather.gov/documentation/services-web-api): free, no key, US only. A photo
gets the observation nearest the time it was taken from the weather station nearest its trap or, failing
that, its hub; when that station has none within NEAREST (stations miss hours, or whole days), the next
nearest is tried. It is kept in the photo's meta["weather"], apart from temp_c / rh, so it is never taken
for the trap's own sensor (the degree days fall back on that sensor).
"""

from __future__ import annotations

import json
import logging
import math
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import __version__
from .models import Capture, Trap, utcnow

log = logging.getLogger(__name__)

API = "https://api.weather.gov"
SOURCE = "National Weather Service"
# The service asks every caller to name itself in the User-Agent, with a way to reach them.
USER_AGENT = f"OrchardSentinel/{__version__} (+https://github.com/ninaa26/applev2)"
# api.weather.gov keeps about a week of observations (checked Oct 25 2026: Oct 18 on, none before), so
# older photos can't be filled.
LOOK_BACK = timedelta(days=7)
NEAREST = timedelta(minutes=90)  # an observation further than this from the photo is not its weather
STATIONS_TRIED = 3
TIMEOUT_S = 10

_stations: dict[tuple[float, float], list[dict]] = {}  # stations near a location: they don't move


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
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.load(r)


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2, dl = math.radians(lat1), math.radians(lat2), math.radians(lon2 - lon1)
    return 6371 * math.acos(min(1.0, math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(dl)))


def stations(lat: float, lon: float) -> list[dict]:
    """The nearest weather stations, nearest first: [{"id", "name", "km"}]. The service's own list is not
    in order of distance."""
    if (lat, lon) not in _stations:
        url = _get_json(f"{API}/points/{lat:.4f},{lon:.4f}")["properties"]["observationStations"]
        found = [{"id": f["properties"]["stationIdentifier"], "name": f["properties"]["name"],
                  "km": round(_km(lat, lon, f["geometry"]["coordinates"][1], f["geometry"]["coordinates"][0]), 1)}
                 for f in _get_json(url)["features"]]
        _stations[(lat, lon)] = sorted(found, key=lambda s: s["km"])[:STATIONS_TRIED]
    return _stations[(lat, lon)]


def observations(station: str, first: datetime, last: datetime) -> list[tuple[datetime, float, float]]:
    """[(time, naive UTC; temp °C; relative humidity %)] the station reported from `first` to `last`."""
    q = urllib.parse.urlencode({"start": first.strftime("%Y-%m-%dT%H:%M:%SZ"), "end": last.strftime("%Y-%m-%dT%H:%M:%SZ")})
    out = []
    for f in _get_json(f"{API}/stations/{station}/observations?{q}")["features"]:
        p = f["properties"]
        tc, rh = (p.get("temperature") or {}).get("value"), (p.get("relativeHumidity") or {}).get("value")
        if tc is not None and rh is not None:
            at = datetime.fromisoformat(p["timestamp"]).astimezone(timezone.utc).replace(tzinfo=None)
            out.append((at, tc, rh))
    return out


def needs_weather(cap: Capture) -> bool:
    return cap.temp_c is None and cap.rh is None and "weather" not in (cap.meta or {})


def fill(db: Session, limit: int = 200) -> int:
    """Look up the weather for recent photos with no sensor reading. Returns how many were filled.
    A photo no station has reported for yet is tried again next time, until it is LOOK_BACK old."""
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
            near = stations(lat, lon)
        except Exception as e:  # offline, the service is down, or the place is outside the US
            log.warning("weather stations near %.4f, %.4f: %s", lat, lon, e)
            continue
        waiting = group
        for st in near:
            try:  # one request per day of photos keeps each reply to a day of observations
                obs = [o for day in sorted({c.captured_at.date() for c in waiting})
                       for o in observations(st["id"], datetime.combine(day, datetime.min.time()) - NEAREST,
                                             datetime.combine(day, datetime.max.time()) + NEAREST)]
            except Exception as e:
                log.warning("weather from %s: %s", st["id"], e)
                continue
            still = []
            for c in waiting:
                at, tc, rh = min(obs, key=lambda o: abs(o[0] - c.captured_at), default=(None, None, None))
                if at is None or abs(at - c.captured_at) > NEAREST:
                    still.append(c)
                    continue
                c.meta = {**(c.meta or {}), "weather": {
                    "temp_c": tc, "rh": round(rh), "source": SOURCE, "station": st["id"], "station_name": st["name"],
                    "km": st["km"], "at": at.isoformat()}}
                done += 1
            waiting = still
            if not waiting:
                break
    return done
