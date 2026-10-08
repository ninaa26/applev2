"""Adding and removing cameras on the dashboard, the hub's node list, and the orchard and per-trap pages."""
import io
import json
import re
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from PIL import Image

from sentinel_server import services
from sentinel_server.app import create_app
from sentinel_server.db import session_scope
from sentinel_server.models import Trap


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (230, 230, 210)).save(buf, "JPEG")
    return buf.getvalue()


def _add(client, **form) -> tuple[int, str | None]:
    r = client.post("/manage/traps", data={"name": "", "block": "", "lure": "CM", **form})
    m = re.search(r'(?:API_KEY |api_key = )"([^"]+)"', r.text)
    return r.status_code, m.group(1) if m else None


def _upload(client, key, trap_id, uid, when=None):
    when = when or datetime.now(timezone.utc)
    meta = {"capture_uid": uid, "trap_id": trap_id, "captured_at": when.isoformat()}
    return client.post("/api/v1/captures", headers={"Authorization": f"Bearer {key}"},
                       files={"image": (f"{uid}.jpg", _jpeg(), "image/jpeg")}, data={"meta": json.dumps(meta)})


def test_add_esp32_cameras_through_a_hub_and_remove_them():
    with TestClient(create_app()) as client:
        status, _ = _add(client, trap_id="T1", kind="esp32", hub_id="T9")
        assert status == 422  # no Pi trap to be its hub yet

        status, hub_key = _add(client, trap_id="T1", kind="pi", name="Hub at the shed")
        assert status == 200 and hub_key
        page = client.get("/manage").text
        assert 'value="T2"' in page  # suggests the next free id

        status, cam_key = _add(client, trap_id="T2", kind="esp32", hub_id="T1", name="Row 4 east")
        assert status == 200 and cam_key and cam_key != hub_key
        assert _add(client, trap_id="T2", kind="esp32", hub_id="T1")[0] == 422  # id taken

        nodes = client.get("/api/v1/hub/nodes", headers={"Authorization": f"Bearer {hub_key}"}).json()["nodes"]
        assert nodes == {"T2": services.hash_key(cam_key)}
        assert _upload(client, cam_key, "T2", "a1").status_code == 201

        client.post("/manage/traps/T2/remove")
        assert client.get("/api/v1/hub/nodes", headers={"Authorization": f"Bearer {hub_key}"}).json()["nodes"] == {}
        assert _upload(client, cam_key, "T2", "a2").status_code == 410
        assert "/traps/T2" not in client.get("/").text.split("Recent events")[0]  # gone from the trap table
        assert client.get("/traps/T2").status_code == 200  # its history is kept

        client.post("/manage/traps/T2/restore")
        assert _upload(client, cam_key, "T2", "a3").status_code == 201

        r = client.post("/manage/traps/T2/new-key")
        new_key = re.search(r'API_KEY "([^"]+)"', r.text).group(1)
        assert _upload(client, cam_key, "T2", "a4").status_code == 401
        assert _upload(client, new_key, "T2", "a4").status_code == 201


def test_hub_list_needs_the_hub_key():
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/hub/nodes").status_code == 401
        assert client.get("/api/v1/hub/nodes", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_orchard_view_and_each_traps_photos():
    with session_scope() as db:
        k1 = services.create_trap(db, "T1", "Hub", lure="CM")
        k2 = services.create_trap(db, "T2", "Row 4", lure="OFM", kind="esp32", hub_id="T1")
    with TestClient(create_app()) as client:
        start = datetime.now(timezone.utc) - timedelta(days=3)
        for i in range(50):
            assert _upload(client, k2, "T2", f"p{i:02d}", start + timedelta(hours=i)).status_code == 201
        _upload(client, k1, "T1", "h1")
        page = client.get("/").text
        assert "whole orchard" in page and "Traps reporting" in page and "ESP32 via T1" in page
        assert re.search(r'class="val">2<small> / 2', page)

        photos = client.get("/traps/T2/photos").text
        assert "50 photos" in photos and photos.count('class="gallery"') == 1
        assert len(re.findall(r'href="/captures/\d+"', photos)) == 48 and "page 1 of 2" in photos
        older = client.get("/traps/T2/photos?page=2").text
        assert len(re.findall(r'href="/captures/\d+"', older)) == 2
        assert "1 photo," in client.get("/traps/T1/photos").text


def test_cli_add_trap_esp32_needs_a_hub(capsys):
    from sentinel_server.cli import main

    assert main(["add-trap", "T5", "--lure", "CM", "--kind", "esp32"]) == 1
    assert main(["add-trap", "T1", "--lure", "CM"]) == 0
    assert main(["add-trap", "T5", "--lure", "OFM", "--kind", "esp32", "--hub", "T1"]) == 0
    assert "node_config.h" in capsys.readouterr().out
    with session_scope() as db:
        assert db.get(Trap, "T5").hub_id == "T1"
