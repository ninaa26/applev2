"""Adding and updating devices from the dashboard: camera firmware sent through the hubs, cameras that pair
through a hub, and hubs that fetch their key with the code on their sticker."""
import base64
import hashlib
import io
import json
import re

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from sentinel_server import fleet, services
from sentinel_server.app import create_app
from sentinel_server.db import session_scope
from sentinel_server.models import Event, HubClaim, PendingCamera, Trap


def _firmware(version: str = "0.3.0", kind: str = "release") -> bytes:
    """Enough of an ESP32 app image for the server: the magic byte and main.cpp's version marker."""
    return b"\xe9" + bytes(2000) + f"SENTINEL_FW_VERSION={version};{kind}\x00".encode() + bytes(500)


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (230, 230, 210)).save(buf, "JPEG")
    return buf.getvalue()


def _upload(client, key, trap_id, uid, fw):
    meta = {"capture_uid": uid, "trap_id": trap_id, "captured_at": "2026-10-25T15:00:00+00:00", "device": {"sw_version": fw}}
    return client.post("/api/v1/captures", headers={"Authorization": f"Bearer {key}"},
                       files={"image": (f"{uid}.jpg", _jpeg(), "image/jpeg")}, data={"meta": json.dumps(meta)})


def _hub_and_camera():
    with session_scope() as db:
        hub_key = services.create_trap(db, "T1", kind="hub")
        cam_key = services.create_trap(db, "T2", kind="esp32", hub_id="T1")
    return hub_key, cam_key


def test_firmware_file_must_be_a_release_build_and_its_version_comes_from_the_file():
    assert fleet.read_firmware_version(_firmware("0.3.1")) == "0.3.1"
    with pytest.raises(ValueError, match="dev build"):
        fleet.read_firmware_version(_firmware(kind="dev"))
    with pytest.raises(ValueError, match="not an ESP32 firmware"):
        fleet.read_firmware_version(b"PK\x03\x04" + bytes(2000))
    with pytest.raises(ValueError, match="no Sentinel version"):
        fleet.read_firmware_version(b"\xe9" + bytes(2000))
    with session_scope() as db:
        fleet.add_firmware(db, _firmware("0.3.1"))
        fleet.add_firmware(db, _firmware("0.3.1"))  # the same file again is fine
        with pytest.raises(ValueError, match="different contents"):
            fleet.add_firmware(db, _firmware("0.3.1") + b"changed")


def test_firmware_sent_to_one_camera_goes_through_its_hub_until_the_camera_runs_it():
    hub_key, cam_key = _hub_and_camera()
    hub = {"Authorization": f"Bearer {hub_key}"}
    fw = _firmware("0.3.1")
    with TestClient(create_app()) as client:
        assert _upload(client, cam_key, "T2", "a1", "0.3.0").status_code == 201
        r = client.post("/manage/firmware", files={"file": ("firmware.bin", fw)}, data={"note": "faster upload"},
                        follow_redirects=False)
        assert r.status_code == 303
        assert client.post("/manage/firmware", files={"file": ("x.bin", _firmware(kind="dev"))}).status_code == 422
        assert client.get("/api/v1/hub/nodes", headers=hub).json()["firmware"] == {}  # nothing sent yet

        client.post("/manage/firmware/target", data={"version": "0.3.1", "trap_id": "T2"})
        offered = client.get("/api/v1/hub/nodes", headers=hub).json()["firmware"]
        assert offered == {"T2": {"version": "0.3.1", "size": len(fw), "md5": hashlib.md5(fw).hexdigest()}}
        page = client.get("/manage").text
        assert "fw 0.3.0" in page and "updating to 0.3.1" in page

        got = client.get("/api/v1/hub/firmware/0.3.1", headers=hub)
        assert got.status_code == 200 and got.content == fw
        assert client.get("/api/v1/hub/firmware/0.3.1", headers={"Authorization": f"Bearer {cam_key}"}).status_code == 403
        assert client.get("/api/v1/hub/firmware/9.9.9", headers=hub).status_code == 404
        assert client.get("/api/v1/hub/firmware/..%2Fsentinel.db", headers=hub).status_code == 404

        assert _upload(client, cam_key, "T2", "a2", "0.3.1").status_code == 201  # the camera runs it now
        assert client.get("/api/v1/hub/nodes", headers=hub).json()["firmware"] == {}
        assert "Camera updated" in client.get("/").text
        with session_scope() as db:
            assert db.get(Trap, "T2").firmware_version == "0.3.1"
            assert [e.kind for e in db.query(Event).filter(Event.kind.like("firmware%"))] == ["firmware_asked", "firmware_updated"]

        # Going back is sending an older version; "Stop sending updates" clears it for every camera.
        assert client.post("/manage/firmware/target", data={"version": "0.2.9", "trap_id": "all"}).status_code == 422
        client.post("/manage/firmware/target", data={"version": "", "trap_id": "all"})
        with session_scope() as db:
            assert db.get(Trap, "T2").firmware_target is None


def test_a_camera_switched_on_near_a_hub_is_added_from_the_dashboard_and_gets_its_key_through_the_hub():
    with session_scope() as db:
        hub_key = services.create_trap(db, "T1", kind="hub")
    hub = {"Authorization": f"Bearer {hub_key}"}
    with TestClient(create_app()) as client:
        r = client.post("/api/v1/hub/pairing", headers=hub, json={"waiting": [{"code": "7f3a2c", "fw": "0.3.0", "rssi": -61}]})
        assert r.status_code == 200 and r.json() == {"assigned": {}}
        page = client.get("/manage").text
        assert "New cameras waiting" in page and "7F3A2C" in page and "signal -61 dBm" in page

        r = client.post("/manage/waiting/7F3A2C", data={"trap_id": "T2", "name": "Row 4", "lure": "OFM"})
        assert r.status_code == 200 and "T2 added" in r.text and "Hub T1 gives the camera its key" in r.text
        assert "New cameras waiting" not in r.text
        assigned = client.post("/api/v1/hub/pairing", headers=hub, json={"waiting": []}).json()["assigned"]
        key = assigned["7F3A2C"]["api_key"]
        assert assigned["7F3A2C"]["trap_id"] == "T2"
        with session_scope() as db:
            t = db.get(Trap, "T2")
            assert (t.kind, t.hub_id, t.lure, t.firmware_version) == ("esp32", "T1", "OFM", "0.3.0")
            assert t.api_key_hash == services.hash_key(key)
        assert client.get("/api/v1/hub/nodes", headers=hub).json()["nodes"] == {"T2": services.hash_key(key)}
        assert _upload(client, key, "T2", "p1", "0.3.0").status_code == 201

        # Once the hub says the camera has it, the server forgets its copy of the key.
        assert client.post("/api/v1/hub/pairing", headers=hub, json={"handed": ["7F3A2C"]}).json() == {"assigned": {}}
        with session_scope() as db:
            assert db.get(PendingCamera, "7F3A2C") is None

        assert client.post("/manage/waiting/ABCDEF", data={"trap_id": "T3"}).status_code == 422  # not waiting
        bad = client.post("/api/v1/hub/pairing", headers=hub, json={"waiting": [{"code": "nothex"}, "x"], "handed": []})
        assert bad.status_code == 200
        assert client.post("/api/v1/hub/pairing", headers={"Authorization": f"Bearer {key}"}, json={}).status_code == 403


def test_a_hub_fetches_its_key_with_the_code_on_its_sticker():
    with TestClient(create_app()) as client:
        code = fleet.new_hub_code()
        assert client.post("/api/v1/hub/claim", json={"code": code}).status_code == 404
        r = client.post("/manage/traps", data={"trap_id": "T1", "kind": "hub", "name": "Fieldhouse",
                                               "pair_code": f"{code[:4].lower()}-{code[4:]}"})
        assert r.status_code == 200 and "fetches its key by itself" in r.text and "api_key" not in r.text
        got = client.post("/api/v1/hub/claim", json={"code": code})
        assert got.status_code == 200 and got.json()["trap_id"] == "T1"
        key = got.json()["api_key"]
        assert client.post("/manage/traps", data={"trap_id": "T9", "kind": "hub", "pair_code": code}).status_code == 422
        assert client.post("/manage/traps", data={"trap_id": "T9", "kind": "hub", "pair_code": "0000"}).status_code == 422

        assert client.get("/api/v1/hub/nodes", headers={"Authorization": f"Bearer {key}"}).status_code == 200
        with session_scope() as db:
            assert db.query(HubClaim).count() == 0  # the hub has used its key: no copy kept
        assert client.post("/api/v1/hub/claim", json={"code": code}).status_code == 404


def test_hub_endpoints_skip_the_dashboard_password(monkeypatch):
    from sentinel_server import settings as settings_mod
    monkeypatch.setenv("SENTINEL_DASHBOARD_PASSWORD", "orchard")
    settings_mod.reset_settings()
    hub_key, _ = _hub_and_camera()
    with TestClient(create_app()) as client:
        assert client.get("/manage").status_code == 401
        assert client.post("/api/v1/hub/claim", json={"code": "ABCDEFGHJK"}).status_code == 404
        assert client.post("/api/v1/hub/pairing", headers={"Authorization": f"Bearer {hub_key}"}, json={}).status_code == 200
        auth = {"Authorization": "Basic " + base64.b64encode(b"x:orchard").decode()}
        assert "Camera firmware" in client.get("/manage", headers=auth).text
