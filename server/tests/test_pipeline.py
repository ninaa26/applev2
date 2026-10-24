"""End to end: device-style uploads of synthetic liner photos -> worker -> counts on the dashboard."""

import io
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from sentinel_server import services
from sentinel_server.app import create_app
from sentinel_server.db import session_scope
from sentinel_server.models import Capture, Event, Track, Trap
from sentinel_server.pipeline import track as trk
from sentinel_server.pipeline.worker import Pipeline, process_pending

W, H = 1600, 900
MOTHS = [(300, 300), (900, 500), (1300, 200)]
GRID = 160  # a 25.4 mm liner grid at ~6.3 px/mm: moths below are ~8 mm long


def liner(moths) -> bytes:
    img = Image.new("RGB", (W, H), (236, 232, 205))
    d = ImageDraw.Draw(img)
    for x in range(0, W, GRID):
        d.line([(x, 0), (x, H)], fill=(190, 60, 50), width=3)
    for y in range(0, H, GRID):
        d.line([(0, y), (W, y)], fill=(190, 60, 50), width=3)
    d.rounded_rectangle([W / 2 - 30, H / 2 - 10, W / 2 + 30, H / 2 + 10], radius=6, fill=(170, 40, 40))  # lure (masked)
    for x, y, *r in moths:  # (x, y) or (x, y, half-length px, half-width px)
        rx, ry = r or (25, 12)
        d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=(80, 70, 60))
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


def test_dashboard_password_guards_pages_but_not_trap_uploads(monkeypatch):
    from sentinel_server import settings as settings_mod

    key = add_trap()
    with TestClient(create_app()) as client:
        assert client.get("/").status_code == 200  # no password set: open, as before

    monkeypatch.setenv("SENTINEL_DASHBOARD_PASSWORD", "orchard")
    settings_mod.reset_settings()
    with TestClient(create_app()) as client:
        for path in ("/", "/review", "/api/v1/traps", "/static/app.css"):
            r = client.get(path)
            assert r.status_code == 401 and r.headers["www-authenticate"].startswith("Basic"), path
        assert client.post("/traps/T1/new-card", follow_redirects=False).status_code == 401
        assert client.get("/", auth=("anyone", "wrong")).status_code == 401
        assert client.get("/", headers={"Authorization": "Basic not-base64!"}).status_code == 401
        assert client.get("/", auth=("anyone", "orchard")).status_code == 200
        assert client.get("/healthz").status_code == 200
        assert upload(client, key, datetime.now(timezone.utc), MOTHS, "a").status_code == 201


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

        # re-running the liner with a new model gives the same counts (and doesn't trip foreign keys)
        with session_scope() as db:
            assert Pipeline().reprocess_card(db, caps[0].card_id) == 4
        with session_scope() as db:
            assert db.query(Track).filter(Track.status == "confirmed").count() == 3

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


def _liners_after(third_photo_moths, **meta):
    """Two photos of a liner with three moths, then a third photo that claims a new liner."""
    from sentinel_server.models import Card, Event

    key = add_trap()
    t0 = datetime.now(timezone.utc) - timedelta(hours=6)
    with TestClient(create_app()) as client:
        upload(client, key, t0, MOTHS, "c1")
        upload(client, key, t0 + timedelta(hours=3), MOTHS, "c2")
        upload(client, key, t0 + timedelta(hours=4), third_photo_moths, "c3", new_card=True, wake_reason="manual", **meta)
        upload(client, key, t0 + timedelta(hours=5), third_photo_moths, "c4")
        assert process_pending(Pipeline(), limit=10) == 4
    with session_scope() as db:
        return {"cards": db.query(Card).count(), "open": services.open_card(db, "T1") is not None,
                "counted": sum(services.week_counts(db, "T1").values()),
                "on_open_card": db.query(Capture).filter(Capture.card_id == services.open_card(db, "T1").id).count(),
                "ignored": db.query(Event).filter(Event.kind == "new_card_ignored").count()}


def test_battery_swap_is_not_a_new_liner():
    # the trap woke off schedule and called it a new liner, but the same three moths are still there
    got = _liners_after(MOTHS)
    assert got == {"cards": 1, "open": True, "counted": 3, "on_open_card": 4, "ignored": 1}, got


def test_battery_swap_with_a_new_catch_is_still_the_old_liner():
    got = _liners_after(MOTHS + [(600, 700)])
    assert (got["cards"], got["counted"], got["ignored"]) == (1, 4, 1), got


def test_button_press_with_a_clean_liner_starts_a_new_one():
    got = _liners_after([(600, 700)])  # one moth, somewhere new
    assert got == {"cards": 2, "open": True, "counted": 4, "on_open_card": 2, "ignored": 0}, got


def test_new_liner_asked_for_outright_is_not_second_guessed():
    got = _liners_after(MOTHS, new_card_source="flag")  # sentinel-cycle --new-card
    assert (got["cards"], got["ignored"]) == (2, 0), got


def test_same_liner_needs_old_insects_to_go_by():
    from sentinel_server.pipeline.worker import same_liner_as_before

    a, b, far = trk.Rect(0, 0, 10, 10), trk.Rect(50, 50, 60, 60), trk.Rect(200, 200, 210, 210)
    assert same_liner_as_before([], [a]) is None
    assert same_liner_as_before([a, b], [a, far]) is True       # half still there
    assert same_liner_as_before([a, b, far], [a]) is False      # most are gone


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


def test_bycatch_is_kept_but_not_counted():
    key = add_trap()
    t0 = datetime.now(timezone.utc) - timedelta(hours=3)
    with TestClient(create_app()) as client:
        upload(client, key, t0, MOTHS[:2], "b1")
        upload(client, key, t0 + timedelta(hours=1), MOTHS[:2], "b2")
        process_pending(Pipeline())
        with session_scope() as db:
            ids = [t.id for t in services.pending_reviews(db, "T1")]
        client.post(f"/tracks/{ids[0]}/review", data={"label": "OFM"})
        client.post(f"/tracks/{ids[1]}/review", data={"label": "other_insect"})
        with session_scope() as db:
            assert services.week_counts(db, "T1") == {"OFM": 1}
            assert db.get(Track, ids[1]).label == "other_insect"


def test_linear_head_maps_to_species_and_zero_fills_missing_classes():
    import numpy as np

    from sentinel_server.pipeline.classify import linear_head_probs

    W = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    out = linear_head_probs(np.array([[5.0, 0.0]], dtype=np.float32), W, np.zeros(2, np.float32), ["CM", "OFM"])
    assert set(out[0]) == {"CM", "OFM", "OBLR", "other_moth", "other_insect", "debris"}
    assert out[0]["CM"] > 0.99 and out[0]["debris"] == 0.0
    assert abs(sum(out[0].values()) - 1.0) < 1e-6
    # a head's temperature softens the same logits: same answer, less sure of it
    cool = linear_head_probs(np.array([[5.0, 0.0]], dtype=np.float32), W, np.zeros(2, np.float32), ["CM", "OFM"], T=5.0)
    assert 0.7 < cool[0]["CM"] < 0.75 and cool[0]["CM"] > cool[0]["OFM"]


def test_touching_pair_counts_two_and_reviewer_can_fix_the_count():
    key = add_trap()
    t0 = datetime.now(timezone.utc) - timedelta(hours=3)
    pair = [(600, 300, 32, 14), (600, 329, 32, 14)]  # two ~10 mm moths lying side by side, touching
    with TestClient(create_app()) as client:
        upload(client, key, t0, pair, "p1")
        upload(client, key, t0 + timedelta(hours=1), pair, "p2")
        process_pending(Pipeline())
        with session_scope() as db:
            tracks = db.query(Track).filter(Track.status == "confirmed").all()
            assert sum(t.n_insects for t in tracks) == 2
            assert sum(services.week_counts(db, "T1").values()) == 2
            clump = [t for t in tracks if t.n_insects > 1]
        if clump:  # not split into two boxes: it's in the review queue with its count
            assert "insects touching" in client.get("/review").text
            client.post(f"/tracks/{clump[0].id}/review", data={"label": "CM", "count": "3"})
            upload(client, key, t0 + timedelta(hours=2), pair, "p3")
            process_pending(Pipeline())
            with session_scope() as db:
                assert services.week_counts(db, "T1")["CM"] == 3, "the reviewer's count stands"


def test_old_database_gets_new_columns(tmp_path):
    import sqlite3

    from sentinel_server import db as db_mod

    db_mod.reset_engine()
    path = tmp_path / "data" / "sentinel.db"
    path.unlink()
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE tracks (id INTEGER PRIMARY KEY, card_id INTEGER)")
    con.execute("INSERT INTO tracks (id, card_id) VALUES (1, 1)")
    con.commit()
    con.close()
    db_mod.init_db()
    con = sqlite3.connect(path)
    assert con.execute("SELECT n_insects FROM tracks").fetchall() == [(1,)]


def test_rejection_sticks_on_later_photos_and_reprocess():
    key = add_trap()
    t0 = datetime.now(timezone.utc) - timedelta(hours=4)
    with TestClient(create_app()) as client:
        upload(client, key, t0, MOTHS[:2], "j1")
        upload(client, key, t0 + timedelta(hours=1), MOTHS[:2], "j2")
        process_pending(Pipeline())
        with session_scope() as db:
            ids = [t.id for t in services.pending_reviews(db, "T1")]
        client.post(f"/tracks/{ids[0]}/review", data={"label": "reject"})
        upload(client, key, t0 + timedelta(hours=2), MOTHS[:2], "j3")  # the rejected one is seen again
        process_pending(Pipeline())
        with session_scope() as db:
            assert db.get(Track, ids[0]).review_status == "rejected"
            assert ids[0] not in [t.id for t in services.pending_reviews(db, "T1")]
            card_id = db.get(Track, ids[0]).card_id
        with session_scope() as db:  # reviews point at rejected tracks: reprocess must keep them
            assert Pipeline().reprocess_card(db, card_id) == 3
        with session_scope() as db:
            assert db.get(Track, ids[0]).review_status == "rejected"


def test_reprocess_replays_a_reviewed_insect_from_where_it_landed():
    """A reviewed track is kept through a reprocess. Its counters start over (they were added on top of the
    first run's), and photos from before it landed don't count as misses: they used to drop a reviewed
    candidate, and a fresh track then counted the same insect again."""
    key = add_trap()
    t0 = datetime.now(timezone.utc) - timedelta(hours=4)
    with TestClient(create_app(start_worker=False)) as client:
        upload(client, key, t0, MOTHS[:2], "r1")
        upload(client, key, t0 + timedelta(hours=1), MOTHS[:2], "r2")
        upload(client, key, t0 + timedelta(hours=2), MOTHS, "r3")  # the third moth lands
        process_pending(Pipeline())
    landed = (t0 + timedelta(hours=2)).replace(tzinfo=None)
    with session_scope() as db:
        new = db.query(Track).filter(Track.first_seen_at == landed).one()
        assert new.status == "candidate" and new.n_seen == 1
        new.reviewed_label, new.review_status = "OFM", "relabelled"
        tid, card_id, n_classified = new.id, new.card_id, new.n_classified
    with session_scope() as db:
        assert Pipeline().reprocess_card(db, card_id) == 3
    with session_scope() as db:
        t = db.get(Track, tid)
        assert t.status == "candidate" and t.n_seen == 1 and t.misses == 0, (t.status, t.n_seen, t.misses)
        assert t.n_classified == n_classified
        assert db.query(Track).filter(Track.status != "dropped").count() == 3, "the third moth counted once"


def test_capture_uid_cannot_leave_the_media_folder():
    key = add_trap()
    with TestClient(create_app()) as client:
        now = datetime.now(timezone.utc)
        for uid in ("../../../../escaped", "a/b", ".hidden", ""):
            r = upload(client, key, now, MOTHS, uid)
            if uid:
                assert r.status_code == 422, uid
    from sentinel_server.settings import get_settings
    assert not list(get_settings().data_dir.parent.rglob("escaped.jpg"))


def test_species_vote_uses_only_fresh_photos():
    from datetime import datetime, timedelta

    first = datetime(2026, 6, 1, 12)
    assert trk.fresh(first, first + timedelta(hours=48), n_classified=2)
    assert not trk.fresh(first, first + timedelta(hours=96), n_classified=2)  # scales gone: no say on species
    assert trk.fresh(first, first + timedelta(days=9), n_classified=0)        # but a first look always counts


def test_photo_with_a_different_scale_is_left_out():
    from sentinel_server.pipeline.worker import scale_problem

    assert scale_problem([7.0], 30.0) is None            # nothing to compare with yet
    assert scale_problem([7.0, 7.1, 7.2], 7.4) is None
    assert "scale reads 30.0" in scale_problem([7.0, 7.1, 7.2], 30.0)
    assert "no liner grid" in scale_problem([7.0, 7.1], None)


def test_camera_scale_overrides_the_liners_first_photos():
    """T2, Oct 2026: a liner's first photos misread the grid at about a third of the camera's 10.3 px/mm,
    then every right reading after them was rejected for disagreeing. With the camera's measured scale the
    first photos are checked too, and they can't outvote it."""
    from sentinel_server.pipeline.worker import scale_problem

    assert "scale reads 3.5" in scale_problem([], 3.5, camera=10.3)          # first photo of a liner
    assert "camera reads 10.3" in scale_problem([], 32.6, camera=10.3)
    assert scale_problem([3.5, 3.6, 3.4], 10.4, camera=10.3) is None          # the liner's misreads don't count
    assert scale_problem([], 11.5, camera=10.3) is None                       # fisheye and focus: within 20%
    assert "no liner grid" in scale_problem([], None, camera=10.3)


def test_photo_off_the_cameras_scale_is_left_out():
    key = add_trap()
    with session_scope() as db:
        db.get(Trap, "T1").px_per_mm = 15.3  # the synthetic liner reads ~6.4
    with TestClient(create_app(start_worker=False)) as client:
        upload(client, key, datetime(2026, 6, 1, 12, tzinfo=timezone.utc), MOTHS, "a")
        process_pending(Pipeline())
        with session_scope() as db:
            cap = db.get(Capture, 1)
            assert cap.status == "failed" and "camera reads 15.3" in cap.error
            db.get(Trap, "T1").px_per_mm = 6.4
            cap.status = "new"
        process_pending(Pipeline())
    with session_scope() as db:
        assert db.get(Capture, 1).status == "processed"


def test_blurred_photo_is_left_out_and_context_is_logged():
    from datetime import datetime

    from sentinel_server.pipeline.worker import blur_problem, moon_illumination

    assert blur_problem([95.0], 10.0) is None                 # nothing to compare with yet
    assert blur_problem([95.0, 97.0, 94.0], 70.0) is None     # repeat shots vary this much
    assert "blurred" in blur_problem([95.0, 97.0, 94.0], 18.0)
    assert moon_illumination(datetime(2026, 10, 26, 4)) > 0.95  # full moon 26 Oct 2026
    assert moon_illumination(datetime(2026, 10, 10, 16)) < 0.05  # new moon 10 Oct 2026

    key = add_trap()
    with TestClient(create_app(start_worker=False)) as client:
        upload(client, key, datetime(2026, 6, 1, 12, tzinfo=timezone.utc), [(200, 200)], "a")
        process_pending(Pipeline())
    with session_scope() as db:
        meta = db.get(Capture, 1).meta
    assert {"sharpness", "glare", "card_rgb", "liner_days", "moon", "px_per_mm"} <= set(meta)


def test_late_photo_goes_on_the_liner_it_was_taken_on():
    # photos wait in the trap's queue while the liner is changed on the dashboard
    key = add_trap()
    t0 = datetime.now(timezone.utc) - timedelta(hours=6)
    with TestClient(create_app()) as client:
        upload(client, key, t0, MOTHS, "c1")
        old = upload(client, key, t0 + timedelta(hours=1), MOTHS, "c2").json()["card_id"]
        client.post("/traps/T1/new-card", data={"note": "changed"})
        late = upload(client, key, t0 + timedelta(hours=2), MOTHS, "c3").json()["card_id"]
        stale_flag = upload(client, key, t0 + timedelta(hours=3), MOTHS, "c4", new_card=True).json()["card_id"]
        after = upload(client, key, datetime.now(timezone.utc) + timedelta(minutes=5), [], "c5").json()["card_id"]
    assert late == old and stale_flag == old, "taken before the new liner went in"
    assert after != old
    with session_scope() as db:
        assert services.open_card(db, "T1").id == after


def test_late_photo_is_tracked_in_order():
    key = add_trap()
    t0 = datetime.now(timezone.utc) - timedelta(hours=6)
    with TestClient(create_app()) as client:
        upload(client, key, t0, MOTHS[:2], "c1")
        upload(client, key, t0 + timedelta(hours=4), MOTHS, "c3")
        process_pending(Pipeline(), limit=10)
        upload(client, key, t0 + timedelta(hours=2), MOTHS[:2], "c2")  # sat in a queue
        process_pending(Pipeline(), limit=10)
    with session_scope() as db:
        assert all(c.status == "processed" for c in db.query(Capture).all())
        tracks = db.query(Track).all()
        assert sorted(t.status for t in tracks) == ["candidate", "confirmed", "confirmed"]
        # the first two moths were confirmed by the photo taken second, not by the one that arrived second
        expected = (t0 + timedelta(hours=2)).replace(tzinfo=None)
        assert all(t.confirmed_at == expected for t in tracks if t.status == "confirmed")


def test_worker_survives_a_failed_save(monkeypatch):
    key = add_trap()
    t0 = datetime.now(timezone.utc) - timedelta(hours=6)
    with TestClient(create_app()) as client:
        upload(client, key, t0, MOTHS, "c1")
        upload(client, key, t0 + timedelta(hours=1), MOTHS, "c2")
    pipeline = Pipeline()
    real = pipeline.process

    def breaks_the_save(db, cap, **kw):
        if cap.uid == "c1":
            cap.card_id = 999_999  # no such liner: the commit fails on the foreign key, after processing
            return
        real(db, cap, **kw)

    monkeypatch.setattr(pipeline, "process", breaks_the_save)
    assert process_pending(pipeline, limit=10) == 2
    with session_scope() as db:
        caps = {c.uid: c for c in db.query(Capture).all()}
        assert caps["c1"].status == "failed" and "IntegrityError" in caps["c1"].error
        assert caps["c2"].status == "processed"


def test_worker_thread_keeps_going_after_a_failed_pass(monkeypatch):
    import threading

    from sentinel_server.pipeline import worker

    stop, calls = threading.Event(), []

    def flaky(pipeline):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("database is locked")
        stop.set()
        return 0

    monkeypatch.setattr(worker, "process_pending", flaky)
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)
    worker.run_forever(stop)
    assert len(calls) == 2


def test_upload_commits_while_classifier_runs(monkeypatch):
    """A slow classifier (BioCLIP on the Pi's CPU takes minutes for a cluttered photo) must not hold the
    database's write lock: uploads would wait out the 30 s busy timeout and fail with "database is locked"."""
    import threading

    from sentinel_server import settings as settings_mod

    monkeypatch.setenv("SENTINEL_LINER_MAX_DAYS", "-1")  # every photo raises "card_old" before classifying
    settings_mod.reset_settings()

    class SlowClassifier:
        version = "slow"

        def __init__(self):
            self.started, self.release = threading.Event(), threading.Event()

        def classify(self, crops):
            self.started.set()
            assert self.release.wait(30)
            return [{} for _ in crops]

    key = add_trap()
    now = datetime.now(timezone.utc)
    with TestClient(create_app()) as client:
        assert upload(client, key, now - timedelta(hours=1), MOTHS, "slow").status_code == 201
        pipeline = Pipeline()
        pipeline.classifier = SlowClassifier()
        worker = threading.Thread(target=process_pending, args=(pipeline,), daemon=True)
        worker.start()
        try:
            assert pipeline.classifier.started.wait(30)
            result = {}
            up = threading.Thread(target=lambda: result.update(r=upload(client, key, now, MOTHS, "during")))
            up.start()
            up.join(5)  # with the lock held, this waits for the busy timeout instead
            assert not up.is_alive() and result["r"].status_code == 201
        finally:
            pipeline.classifier.release.set()
            worker.join(30)
            up.join(60)
    with session_scope() as db:
        assert {c.uid: c.status for c in db.query(Capture)} == {"slow": "processed", "during": "new"}
        assert "card_old" in [e.kind for e in db.query(Event)]  # raised before classifying, as before


def test_upload_commits_while_a_liner_is_reprocessed():
    """Re-running a liner (the CLI, or the worker when a photo arrives late) classifies every photo before
    deleting or writing anything, so it doesn't hold the write lock for the whole liner either."""
    import threading

    class SlowClassifier:
        version = "slow"

        def __init__(self):
            self.started, self.release = threading.Event(), threading.Event()

        def classify(self, crops):
            self.started.set()
            assert self.release.wait(30)
            return [{} for _ in crops]

    key = add_trap()
    now = datetime.now(timezone.utc)
    with TestClient(create_app()) as client:
        for i in range(2):
            assert upload(client, key, now - timedelta(hours=3 - i), MOTHS, f"r{i}").status_code == 201
        assert process_pending(Pipeline()) == 2
        with session_scope() as db:
            card_id = db.query(Capture).first().card_id
        pipeline = Pipeline()
        pipeline.classifier = SlowClassifier()
        result = {}

        def rerun():
            with session_scope() as db:
                result["n"] = pipeline.reprocess_card(db, card_id)

        worker = threading.Thread(target=rerun, daemon=True)
        worker.start()
        try:
            assert pipeline.classifier.started.wait(30)
            up = threading.Thread(target=lambda: result.update(r=upload(client, key, now, MOTHS, "during")))
            up.start()
            up.join(5)
            assert not up.is_alive() and result["r"].status_code == 201
        finally:
            pipeline.classifier.release.set()
            worker.join(30)
            up.join(60)
    assert result["n"] == 2
    with session_scope() as db:
        assert {c.uid: c.status for c in db.query(Capture)} == {"r0": "processed", "r1": "processed", "during": "new"}
