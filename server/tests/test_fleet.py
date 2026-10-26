"""Adding and updating devices from the dashboard: camera firmware sent through the hubs, cameras that pair
through a hub, and hubs that fetch their key with the code on their sticker."""
import base64
import hashlib
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from sentinel_server import fleet, services
from sentinel_server.app import create_app
from sentinel_server.db import session_scope
from sentinel_server.models import Capture, Event, HubClaim, PendingCamera, Trap


def _firmware(version: str = "0.3.0", kind: str = "release") -> bytes:
    """Enough of an ESP32 app image for the server: the magic byte and main.cpp's version marker."""
    return b"\xe9" + bytes(2000) + f"SENTINEL_FW_VERSION={version};{kind}\x00".encode() + bytes(500)


def _signed(image: bytes) -> bytes:
    """What release.sh uploads: the image, then its signature (a stand-in here: the cameras check it, not the server)."""
    sig = b"\x30\x44" + bytes(68)
    return image + fleet.SIG_MAGIC + len(sig).to_bytes(2, "big") + sig


SECRET = "K7QM3XTP9RWAB2CD"  # a camera's sticker secret (fleet.CAMERA_SECRET)


def _proof(code: str, secret: str = SECRET) -> str:
    return fleet.pairing_proof(fleet.pairing_key(code, secret))


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
        fleet.add_firmware(db, _signed(_firmware("0.3.1")))
        fleet.add_firmware(db, _signed(_firmware("0.3.1")))  # the same file again is fine
        with pytest.raises(ValueError, match="different contents"):
            fleet.add_firmware(db, _signed(_firmware("0.3.1") + b"changed"))


def test_firmware_must_be_signed_and_the_signature_goes_to_the_cameras_separately():
    image = _firmware("0.4.0")
    with pytest.raises(ValueError, match="isn't signed"):
        fleet.split_signature(image)
    with pytest.raises(ValueError, match="damaged"):
        fleet.split_signature(image + fleet.SIG_MAGIC + (70).to_bytes(2, "big") + b"\x30" + bytes(10))
    assert fleet.split_signature(_signed(image)) == (image, b"\x30\x44" + bytes(68))
    with session_scope() as db:
        fw = fleet.add_firmware(db, _signed(image))
        assert (fw.size, fw.sig) == (len(image), "3044" + "00" * 68)
        assert fleet.firmware_path("0.4.0").read_bytes() == image  # the cameras get the plain image


def test_firmware_sent_to_one_camera_goes_through_its_hub_until_the_camera_runs_it():
    hub_key, cam_key = _hub_and_camera()
    hub = {"Authorization": f"Bearer {hub_key}"}
    fw = _firmware("0.3.1")
    with TestClient(create_app()) as client:
        assert _upload(client, cam_key, "T2", "a1", "0.3.0").status_code == 201
        r = client.post("/manage/firmware", files={"file": ("firmware.bin", _signed(fw))}, data={"note": "faster upload"},
                        follow_redirects=False)
        assert r.status_code == 303
        assert client.post("/manage/firmware", files={"file": ("x.bin", _signed(_firmware(kind="dev")))}).status_code == 422
        assert "build it with release.sh, which signs it" in client.post("/manage/firmware", files={"file": ("x.bin", _firmware("0.3.2"))}).text
        assert client.get("/api/v1/hub/nodes", headers=hub).json()["firmware"] == {}  # nothing sent yet

        client.post("/manage/firmware/target", data={"version": "0.3.1", "trap_id": "T2"})
        offered = client.get("/api/v1/hub/nodes", headers=hub).json()["firmware"]
        assert offered == {"T2": {"version": "0.3.1", "size": len(fw), "md5": hashlib.md5(fw).hexdigest(),
                                  "sig": "3044" + "00" * 68}}
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


def test_a_camera_switched_on_near_a_hub_is_added_with_its_sticker_and_gets_its_key_sealed_through_the_hub():
    with session_scope() as db:
        hub_key = services.create_trap(db, "T1", kind="hub")
    hub = {"Authorization": f"Bearer {hub_key}"}
    proof = _proof("7F3A2C")
    with TestClient(create_app()) as client:
        r = client.post("/api/v1/hub/pairing", headers=hub,
                        json={"waiting": [{"code": "7f3a2c", "fw": "0.3.0", "rssi": -61, "proof": proof}]})
        assert r.status_code == 200 and r.json() == {"assigned": {}}
        page = client.get("/manage").text
        assert "New cameras waiting" in page and "7F3A2C" in page and "signal -61 dBm" in page

        # The secret on the sticker has to match the one the camera proved it has.
        r = client.post("/manage/waiting/7F3A2C", data={"trap_id": "T2", "secret": "K7QM3XTP9RWAB2CE"})
        assert r.status_code == 422 and "check the sticker" in r.text
        assert client.post("/manage/waiting/7F3A2C", data={"trap_id": "T2", "secret": "short"}).status_code == 422
        r = client.post("/manage/waiting/7F3A2C", data={"trap_id": "T2", "secret": "k7qm-3xtp-9rwa-b2cd",
                                                         "name": "Row 4", "lure": "OFM"})
        assert r.status_code == 200 and "T2 added" in r.text and "Hub T1 gives the camera its key" in r.text
        assert "New cameras waiting" not in r.text

        assigned = client.post("/api/v1/hub/pairing", headers=hub, json={"waiting": []}).json()["assigned"]
        got = assigned["7F3A2C"]
        assert got["trap_id"] == "T2" and "api_key" not in got  # the hub only sees the sealed key
        key = fleet.open_key(fleet.pairing_key("7F3A2C", SECRET), "T2", got)
        assert key and fleet.open_key(fleet.pairing_key("7F3A2C", "K7QM3XTP9RWAB2CE"), "T2", got) is None
        assert fleet.open_key(fleet.pairing_key("7F3A2C", SECRET), "T9", got) is None  # bound to its trap id
        with session_scope() as db:
            t = db.get(Trap, "T2")
            assert (t.kind, t.hub_id, t.lure, t.firmware_version) == ("esp32", "T1", "OFM", "0.3.0")
            assert t.api_key_hash == services.hash_key(key) == got["key_hash"]
            assert db.get(PendingCamera, "7F3A2C").api_key is None
        assert client.get("/api/v1/hub/nodes", headers=hub).json()["nodes"] == {"T2": services.hash_key(key)}
        assert _upload(client, key, "T2", "p1", "0.3.0").status_code == 201

        # Once the hub says the camera has it, the server forgets its sealed copy.
        assert client.post("/api/v1/hub/pairing", headers=hub, json={"handed": ["7F3A2C"]}).json() == {"assigned": {}}
        with session_scope() as db:
            assert db.get(PendingCamera, "7F3A2C") is None

        assert client.post("/manage/waiting/ABCDEF", data={"trap_id": "T3", "secret": SECRET}).status_code == 422
        bad = client.post("/api/v1/hub/pairing", headers=hub, json={
            "waiting": [{"code": "nothex", "proof": proof}, {"code": "ABCDEF"}, "x"], "handed": []})
        assert bad.status_code == 200
        with session_scope() as db:
            assert db.query(PendingCamera).count() == 0  # no proof, no waiting camera
        assert client.post("/api/v1/hub/pairing", headers={"Authorization": f"Bearer {key}"}, json={}).status_code == 403


def test_a_waiting_camera_stays_with_the_hub_it_paired_at():
    with session_scope() as db:
        k1 = services.create_trap(db, "T1", kind="hub")
        k2 = services.create_trap(db, "T5", kind="pi")  # a Pi camera can be a hub too
    h1, h2 = {"Authorization": f"Bearer {k1}"}, {"Authorization": f"Bearer {k2}"}
    proof = _proof("7F3A2C")
    with TestClient(create_app()) as client:
        client.post("/api/v1/hub/pairing", headers=h1, json={"waiting": [{"code": "7F3A2C", "proof": proof}]})
        # Another hub reporting the same code, with the right proof or another, doesn't move it.
        for p in (proof, "0" * 32):
            client.post("/api/v1/hub/pairing", headers=h2, json={"waiting": [{"code": "7F3A2C", "proof": p}]})
        with session_scope() as db:
            assert (db.get(PendingCamera, "7F3A2C").hub_id, db.get(PendingCamera, "7F3A2C").proof) == ("T1", proof)
        client.post("/manage/waiting/7F3A2C", data={"trap_id": "T2", "secret": SECRET})
        assert client.post("/api/v1/hub/pairing", headers=h2, json={}).json() == {"assigned": {}}
        assert set(client.post("/api/v1/hub/pairing", headers=h1, json={}).json()["assigned"]) == {"7F3A2C"}

        # A camera its first hub no longer hears from can pair at another (it was moved before being added).
        with session_scope() as db:
            db.add(PendingCamera(code="AAAAAA", hub_id="T1", proof=_proof("AAAAAA"),
                                 first_seen_at=fleet.utcnow() - fleet.REBIND_AFTER * 2,
                                 last_seen_at=fleet.utcnow() - fleet.REBIND_AFTER * 2))
        client.post("/api/v1/hub/pairing", headers=h2, json={"waiting": [{"code": "AAAAAA", "proof": _proof("AAAAAA")}]})
        with session_scope() as db:
            assert db.get(PendingCamera, "AAAAAA").hub_id == "T5"


def test_removing_a_hub_stops_its_cameras_keys_and_they_pair_again_keeping_their_trap():
    hub_key, cam_key = _hub_and_camera()
    with session_scope() as db:
        k3 = services.create_trap(db, "T3", kind="hub")
        other = services.create_trap(db, "T4", kind="esp32", hub_id="T3")
    with TestClient(create_app()) as client:
        assert _upload(client, cam_key, "T2", "b1", "0.3.0").status_code == 201
        assert client.post("/manage/traps/T1/remove", follow_redirects=False).status_code == 303
        assert _upload(client, cam_key, "T2", "b2", "0.3.0").status_code == 401  # its key stopped with the hub
        assert _upload(client, other, "T4", "b3", "0.3.0").status_code == 201    # another hub's camera didn't
        assert "Key stopped" in client.get("/").text
        client.post("/manage/traps/T1/restore")
        assert _upload(client, cam_key, "T2", "b4", "0.3.0").status_code == 401  # putting the hub back doesn't bring it back

        # T2 pairs again near hub T3, keeping its trap id, photos and counts.
        h3 = {"Authorization": f"Bearer {k3}"}
        client.post("/api/v1/hub/pairing", headers=h3, json={"waiting": [{"code": "7F3A2C", "proof": _proof("7F3A2C")}]})
        r = client.post("/manage/waiting/7F3A2C", data={"trap_id": "T2", "secret": SECRET})
        assert r.status_code == 200
        got = client.post("/api/v1/hub/pairing", headers=h3, json={}).json()["assigned"]["7F3A2C"]
        new_key = fleet.open_key(fleet.pairing_key("7F3A2C", SECRET), "T2", got)
        assert _upload(client, new_key, "T2", "b5", "0.3.0").status_code == 201
        with session_scope() as db:
            assert db.get(Trap, "T2").hub_id == "T3"
            assert db.query(Capture).filter_by(trap_id="T2").count() == 2
        # Only an ESP32 camera's id can be paired again.
        client.post("/api/v1/hub/pairing", headers=h3, json={"waiting": [{"code": "BBBBBB", "proof": _proof("BBBBBB")}]})
        assert client.post("/manage/waiting/BBBBBB", data={"trap_id": "T3", "secret": SECRET}).status_code == 422


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


# The firmware opens sealed keys with device/esp32-node/include/pairing.h; device/tests/test_firmware_pairing.py
# checks that against these same numbers, so the two sides can't drift apart.
VECTOR = {"code": "7F3A2C", "secret": SECRET, "trap_id": "T2", "api_key": "Zq3_x-9aLmN0pQrStUvWxYz1234567AB",
          "k": "f938e0516a199712e6091a4906609800722f5610dcc548220eed9e2d95d61701",
          "proof": "0c41d2eb390a2c08236aee5937d044fc", "nonce": "000102030405060708090a0b0c0d0e0f",
          "box": "787b8850ced2e9c63d4284e01254a1c3cb957ce7ebbe75ab752c48511344f7a1",
          "tag": "23e2d61862665a378994a28131013414"}


def test_pairing_crypto_matches_the_firmwares_test_vector():
    k = fleet.pairing_key(VECTOR["code"], VECTOR["secret"])
    assert k.hex() == VECTOR["k"] and fleet.pairing_proof(k) == VECTOR["proof"]
    sealed = fleet.seal_key(k, VECTOR["trap_id"], VECTOR["api_key"], bytes.fromhex(VECTOR["nonce"]))
    assert sealed == {key: VECTOR[key] for key in ("nonce", "box", "tag")}
    assert fleet.open_key(k, VECTOR["trap_id"], sealed) == VECTOR["api_key"]
