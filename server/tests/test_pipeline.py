"""End to end: device-style uploads of synthetic liner photos -> worker -> counts on the dashboard."""

import io
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from sentinel_server import services
from sentinel_server.app import create_app
from sentinel_server.db import session_scope
from sentinel_server.models import Capture, Track, Trap
from sentinel_server.pipeline import track as trk
from sentinel_server.pipeline.worker import Pipeline, process_pending

W, H = 1600, 900
MOTHS = [(300, 300), (900, 500), (1300, 200)]


def liner(moths) -> bytes:
    img = Image.new("RGB", (W, H), (236, 232, 205))
    d = ImageDraw.Draw(img)
    for x in range(0, W, 50):
        d.line([(x, 0), (x, H)], fill=(214, 210, 185), width=2)
    for y in range(0, H, 50):
        d.line([(0, y), (W, y)], fill=(214, 210, 185), width=2)
    d.rounded_rectangle([W / 2 - 30, H / 2 - 10, W / 2 + 30, H / 2 + 10], radius=6, fill=(170, 40, 40))  # lure (masked)
    for x, y in moths:
        d.ellipse([x - 25, y - 12, x + 25, y + 12], fill=(80, 70, 60))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def add_trap(key="secret-key"):
    with session_scope() as db:
        db.add(Trap(id="T1", name="bench", lure="CM", api_key_hash=services.hash_key(key)))
    return key


def upload(client, key, when, moths, uid, **extra):
    meta = {"capture_uid": uid, "trap_id": "T1", "captured_at": when.isoformat(), "env": {"temp_c": 18.5},
            "power": {"battery_v": 13.1}, **extra}
    return client.post(
        "/api/v1/captures",
        headers={"Authorization": f"Bearer {key}"},
        files={"image": (f"{uid}.jpg", liner(moths), "image/jpeg")},
        data={"meta": json.dumps(meta)},
    )


def test_iou_and_match():
    a, b = trk.Rect(0, 0, 10, 10), trk.Rect(5, 0, 15, 10)
    assert abs(trk.iou(a, b) - 1 / 3) < 1e-9
    assert trk.match([a], [trk.Rect(1, 1, 11, 11), trk.Rect(100, 100, 110, 110)]) == {0: 0}


def test_consensus_thresholds():
    assert trk.consensus({"CM": 1.8, "OFM": 0.2}, 2) == ("CM", 0.9, "auto")
    assert trk.consensus({"CM": 1.2, "OFM": 0.8}, 2)[2] == "review"
    assert trk.consensus({"CM": 0.8, "OFM": 0.7, "other_moth": 0.5}, 2)[2] == "unknown"
    assert trk.consensus({}, 0) == ("unclassified", 0.0, "review")


def test_upload_auth_and_duplicates():
    key = add_trap()
    with TestClient(create_app()) as client:
        now = datetime.now(timezone.utc)
        assert upload(client, "wrong", now, MOTHS, "a").status_code == 401
        r = upload(client, key, now, MOTHS, "a")
        assert r.status_code == 201 and r.json()["card_id"]
        assert upload(client, key, now, MOTHS, "a").status_code == 409
        bad = client.post("/api/v1/captures", headers={"Authorization": f"Bearer {key}"},
                          files={"image": ("x.jpg", b"not a jpeg", "image/jpeg")},
                          data={"meta": json.dumps({"captured_at": now.isoformat()})})
        assert bad.status_code == 422


def test_counts_each_insect_once_and_new_card_resets():
    key = add_trap()
    t0 = datetime.now(timezone.utc) - timedelta(hours=6)
    with TestClient(create_app()) as client:
        upload(client, key, t0, MOTHS[:2], "c1")
        upload(client, key, t0 + timedelta(hours=2), MOTHS[:2], "c2")          # same two moths again
        upload(client, key, t0 + timedelta(hours=4), MOTHS, "c3")              # a third one lands
        upload(client, key, t0 + timedelta(hours=5), MOTHS, "c4")
        assert process_pending(Pipeline(), limit=10) == 4

        with session_scope() as db:
            caps = db.query(Capture).all()
            assert all(c.status == "processed" for c in caps), [c.error for c in caps]
            confirmed = db.query(Track).filter(Track.status == "confirmed").count()
            assert confirmed == 3, "three moths, each counted once despite 4 photos"
            assert sum(services.week_counts(db, "T1").values()) == 3

        # dashboard pages render
        for path in ["/", "/traps/T1", "/review", f"/captures/{caps[-1].id}", "/api/v1/traps", "/api/v1/traps/T1/counts"]:
            assert client.get(path).status_code == 200, path

        # a fresh liner: counting starts over
        upload(client, key, t0 + timedelta(hours=5, minutes=30), [MOTHS[0]], "c5", new_card=True)
        upload(client, key, t0 + timedelta(hours=5, minutes=45), [MOTHS[0]], "c6")
        process_pending(Pipeline(), limit=10)
        with session_scope() as db:
            card = services.open_card(db, "T1")
            assert db.query(Track).filter(Track.card_id == card.id, Track.status == "confirmed").count() == 1


def test_review_overrides_model_and_reject_removes_count():
    key = add_trap()
    t0 = datetime.now(timezone.utc) - timedelta(hours=3)
    with TestClient(create_app()) as client:
        upload(client, key, t0, MOTHS[:2], "r1")
        upload(client, key, t0 + timedelta(hours=1), MOTHS[:2], "r2")
        process_pending(Pipeline())
        with session_scope() as db:
            ids = [t.id for t in services.pending_reviews(db, "T1")]
        assert len(ids) == 2
        assert client.post(f"/tracks/{ids[0]}/review", data={"label": "CM"}, follow_redirects=False).status_code == 303
        client.post(f"/tracks/{ids[1]}/review", data={"label": "reject"})
        with session_scope() as db:
            assert services.week_counts(db, "T1") == {"CM": 1}
            assert services.pending_reviews(db, "T1") == []
