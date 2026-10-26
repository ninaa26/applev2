"""Air temperature and humidity from the National Weather Service, for photos whose camera has no sensor
(the ESP32s).

api.weather.gov (https://www.weather.gov/documentation/services-web-api): free, no key, US only. A photo
gets the observation nearest the time it was taken from the weather station nearest its trap or, failing
that, its hub; when that station has none within NEAREST (stations miss hours, or whole days), the next
nearest is tried. When none of the STATIONS_TRIED nearest has one (or the place is outside the US, or the
service is down), the photo gets Open-Meteo's hourly value for its location instead (https://open-meteo.com:
free, no key, a weather model rather than a measurement), once it is FALLBACK_AFTER old.

It is kept in the photo's meta["weather"], apart from temp_c / rh, so it is never taken for the trap's own
sensor (the degree days fall back on that sensor).
"""

from __future__ import annotations

import json
import logging
import math
import re
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import __version__
from .models import Capture, Trap, utcnow

log = logging.getLogger(__name__)

API = "https://api.weather.gov"
SOURCE = "National Weather Service"
# The service asks every caller to name itself in the User-Agent. Just the app's name: no link or contact.
USER_AGENT = f"OrchardSentinel/{__version__}"
# api.weather.gov keeps about a week of observations (checked Oct 25 2026: Oct 18 on, none before); older
# photos go to Open-Meteo, whose forecast API has about three months behind it.
NWS_LOOK_BACK = timedelta(days=7)
LOOK_BACK = timedelta(days=60)
# Stations post an observation up to an hour or so late: a photo waits this long for one before it gets
# Open-Meteo's value instead.
FALLBACK_AFTER = timedelta(hours=3)
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_SOURCE = "Open-Meteo"
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


def _coord(text: str) -> float:
    """"-76.4712", "76.4712 W" or "76.4712°W": the hemisphere letter signs it (S and W are negative)."""
    m = re.fullmatch(r"\s*([-+]?\d+(?:\.\d+)?)\s*°?\s*([NSEWnsew])?\s*", text)
    if m is None:
        raise ValueError(text)
    v = float(m.group(1))
    return -abs(v) if m.group(2) and m.group(2).upper() in "SW" else v


def parse_location(lat: str, lon: str) -> tuple[float | None, float | None]:
    """Form fields to (lat, lon); both empty is no location. Raises ValueError on anything else."""
    if not lat.strip() and not lon.strip():
        return None, None
    try:
        la, lo = _coord(lat), _coord(lon)
    except ValueError:
        raise ValueError("location: give both latitude and longitude as numbers, e.g. 42.4459 and -76.4712") from None
    if not (-90 <= la <= 90 and -180 <= lo <= 180):
        raise ValueError("location: latitude is -90 to 90 and longitude -180 to 180")
    return round(la, 4), round(lo, 4)


def forget(db: Session, trap: Trap) -> int:
    """The trap (or hub) moved: drop the weather looked up for its photos and its cameras' at the old
    location, so the next pass looks it up again at the new one. Returns how many photos were dropped."""
    ids = [trap.id] + list(db.scalars(select(Trap.id).where(Trap.hub_id == trap.id, Trap.lat.is_(None))))
    n = 0
    for c in db.scalars(select(Capture).where(Capture.trap_id.in_(ids), Capture.captured_at >= utcnow() - LOOK_BACK)):
        if "weather" in (c.meta or {}):
            c.meta = {k: v for k, v in c.meta.items() if k != "weather"}
            n += 1
    return n


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/geo+json"})  # noqa: S310
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:  # noqa: S310 (https URLs of the NWS and Open-Meteo APIs)
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
            at = datetime.fromisoformat(p["timestamp"]).astimezone(UTC).replace(tzinfo=None)
            out.append((at, tc, rh))
    return out


def hourly(lat: float, lon: float, first: datetime, last: datetime) -> dict[datetime, tuple[float, float]]:
    """Open-Meteo: {hour (naive UTC): (temp °C, relative humidity %)} for the days from `first` to `last`."""
    q = urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "hourly": "temperature_2m,relative_humidity_2m", "timezone": "GMT",
        "start_date": first.date().isoformat(), "end_date": last.date().isoformat(),
    })
    h = _get_json(f"{OPEN_METEO}?{q}")["hourly"]
    return {datetime.fromisoformat(t): (tc, rh)
            for t, tc, rh in zip(h["time"], h["temperature_2m"], h["relative_humidity_2m"])
            if tc is not None and rh is not None}


def needs_weather(cap: Capture) -> bool:
    return cap.temp_c is None and cap.rh is None and "weather" not in (cap.meta or {})


def fill(db: Session, limit: int = 200) -> int:
    """Look up the weather for recent photos with no sensor reading. Returns how many were filled.
    A photo nothing has been found for yet is tried again next time, until it is LOOK_BACK old."""
    since = utcnow() - LOOK_BACK
    caps = [c for c in db.scalars(select(Capture).where(
        Capture.captured_at >= since, Capture.temp_c.is_(None), Capture.rh.is_(None))
        .order_by(Capture.captured_at.desc()).limit(limit * 5)) if needs_weather(c)][:limit]
    by_place: dict[tuple[float, float], list[Capture]] = {}
    for c in caps:
        where = location(db, db.get_one(Trap, c.trap_id))
        if where is not None:
            by_place.setdefault(where, []).append(c)
    done = 0
    for (lat, lon), group in by_place.items():
        waiting = from_stations(lat, lon, group)
        if waiting:
            done += len(group) - len(waiting)
            done += from_open_meteo(lat, lon, [c for c in waiting if utcnow() - c.captured_at >= FALLBACK_AFTER])
        else:
            done += len(group)
    return done


def from_stations(lat: float, lon: float, caps: list[Capture]) -> list[Capture]:
    """Fill what the nearest National Weather Service stations reported. Returns the photos still waiting."""
    waiting = [c for c in caps if utcnow() - c.captured_at < NWS_LOOK_BACK]
    older = [c for c in caps if c not in waiting]
    if not waiting:
        return older
    try:
        near = stations(lat, lon)
    except Exception as e:  # offline, the service is down, or the place is outside the US
        log.warning("weather stations near %.4f, %.4f: %s", lat, lon, e)
        return caps
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
                "temp_c": tc, "rh": round(rh), "source": SOURCE, "station": st["id"], "station_name": st["name"],  # type: ignore[arg-type]  # at is set, so rh is too
                "km": st["km"], "at": at.isoformat()}}
        waiting = still
        if not waiting:
            break
    return waiting + older


def from_open_meteo(lat: float, lon: float, caps: list[Capture]) -> int:
    """Fill Open-Meteo's hourly value nearest each photo. Returns how many were filled."""
    if not caps:
        return 0
    try:
        hours = hourly(lat, lon, min(c.captured_at for c in caps), max(c.captured_at for c in caps))
    except Exception as e:  # offline, or the service is down: the photos wait for the next pass
        log.warning("Open-Meteo for %.4f, %.4f: %s", lat, lon, e)
        return 0
    done = 0
    for c in caps:
        hour = (c.captured_at + timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)
        if hour in hours:
            tc, rh = hours[hour]
            c.meta = {**(c.meta or {}), "weather": {
                "temp_c": tc, "rh": round(rh), "source": OPEN_METEO_SOURCE, "at": hour.isoformat()}}
            done += 1
    return done
