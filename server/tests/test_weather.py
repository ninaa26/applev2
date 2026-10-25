"""A hub's location, and the weather service's temperature and humidity on its ESP32 cameras' photos."""
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from sentinel_server import weather
from sentinel_server.app import create_app
from sentinel_server.db import session_scope
from sentinel_server.models import Capture, Trap

from test_manage import _add, _upload


def _fake_service(monkeypatch, temp_c=11.5, rh=64.0):
    """Open-Meteo's reply: every hour of the days asked for. Records the requests."""
    asked = []

    def get_json(url):
        q = parse_qs(urlparse(url).query)
        asked.append(q)
        day = datetime.fromisoformat(q["start_date"][0])
        hours = [day + timedelta(hours=i) for i in range(24 * 3)]
        return {"hourly": {"time": [h.strftime("%Y-%m-%dT%H:%M") for h in hours],
                           "temperature_2m": [temp_c] * len(hours), "relative_humidity_2m": [rh] * len(hours)}}

    monkeypatch.setattr(weather, "_get_json", get_json)
    return asked


def test_hub_location_on_add_and_on_its_page():
    with TestClient(create_app()) as client:
        assert _add(client, trap_id="T1", kind="hub", lat="91", lon="0")[0] == 422
        assert _add(client, trap_id="T1", kind="hub", lat="42.45343", lon="-76.47351")[0] == 200
        assert _add(client, trap_id="T2", kind="esp32", hub_id="T1", lat="1", lon="1")[0] == 200
        with session_scope() as db:
            assert (db.get(Trap, "T1").lat, db.get(Trap, "T1").lon) == (42.4534, -76.4735)
            assert db.get(Trap, "T2").lat is None  # a camera goes by its hub's location
            assert weather.location(db, db.get(Trap, "T2")) == (42.4534, -76.4735)

        assert "42.4534, -76.4735" in client.get("/traps/T1").text
        assert client.post("/traps/T1/location", data={"lat": "42.5", "lon": ""}).status_code == 422
        client.post("/traps/T1/location", data={"lat": "", "lon": ""})
        with session_scope() as db:
            assert db.get(Trap, "T1").lat is None
        assert "Not set" in client.get("/traps/T1").text


def test_photos_without_a_sensor_get_the_weather_at_their_hub(monkeypatch):
    asked = _fake_service(monkeypatch)
    with TestClient(create_app()) as client:
        _add(client, trap_id="T1", kind="hub")
        _, key = _add(client, trap_id="T2", kind="esp32", hub_id="T1")
        when = datetime.now(timezone.utc) - timedelta(hours=3)
        assert _upload(client, key, "T2", "a1", when).status_code == 201
        with session_scope() as db:
            cap_id = db.query(Capture).one().id
            assert weather.fill(db) == 0 and asked == []  # no location yet: nothing to ask
        assert "Set T1's location" in client.get(f"/captures/{cap_id}").text

        client.post("/traps/T1/location", data={"lat": "42.45", "lon": "-76.47"})
        with session_scope() as db:
            assert weather.fill(db) == 1
        assert asked[0]["latitude"] == ["42.45"]
        with session_scope() as db:
            cap = db.get(Capture, cap_id)
            assert cap.temp_c is None and cap.meta["weather"]["temp_c"] == 11.5  # never taken for a sensor
            assert weather.fill(db) == 0  # done once
        page = client.get(f"/captures/{cap_id}").text
        assert "11.5 °C" in page and "64%" in page and "Open-Meteo" in page


def test_a_sensor_reading_is_kept_and_not_looked_up(monkeypatch):
    asked = _fake_service(monkeypatch)
    with TestClient(create_app()) as client:
        _, key = _add(client, trap_id="T1", kind="pi", lat="42.45", lon="-76.47")
        meta = {"capture_uid": "s1", "trap_id": "T1", "captured_at": datetime.now(timezone.utc).isoformat(),
                "env": {"temp_c": 20.0, "rh": 50.0}}
        from test_manage import _jpeg
        client.post("/api/v1/captures", headers={"Authorization": f"Bearer {key}"},
                    files={"image": ("s1.jpg", _jpeg(), "image/jpeg")}, data={"meta": json.dumps(meta)})
        with session_scope() as db:
            assert weather.fill(db) == 0 and asked == []
            cap_id = db.query(Capture).one().id
        page = client.get(f"/captures/{cap_id}").text
        assert "20.0 °C" in page and "Open-Meteo" not in page


def test_service_down_leaves_the_photo_for_next_time(monkeypatch):
    def down(url):
        raise OSError("no network")

    monkeypatch.setattr(weather, "_get_json", down)
    with TestClient(create_app()) as client:
        _add(client, trap_id="T1", kind="hub", lat="42.45", lon="-76.47")
        _, key = _add(client, trap_id="T2", kind="esp32", hub_id="T1")
        _upload(client, key, "T2", "a1", datetime.now(timezone.utc) - timedelta(hours=2))
        with session_scope() as db:
            assert weather.fill(db) == 0
        _fake_service(monkeypatch)
        with session_scope() as db:
            assert weather.fill(db) == 1
