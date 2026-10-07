"""Who gets shown to a person, and how the biofix says what it rests on."""

from datetime import timedelta

from fastapi.testclient import TestClient

from sentinel_server import services
from sentinel_server.app import create_app
from sentinel_server.db import session_scope
from sentinel_server.models import Capture, Card, Track, Trap, utcnow


def trap_with_tracks(specs):
    """specs: (species, confidence, review_status, days ago). Returns the track ids."""
    with session_scope() as db:
        db.add(Trap(id="T1", name="bench", lure="CM", api_key_hash=services.hash_key("k")))
        card = Card(trap_id="T1")
        db.add(card)
        db.flush()
        cap = Capture(trap_id="T1", card_id=card.id, uid="c1", captured_at=utcnow(), image_path="x.jpg")
        db.add(cap)
        db.flush()
        ids = []
        for species, conf, status, days in specs:
            when = utcnow() - timedelta(days=days)
            t = Track(card_id=card.id, first_seen_at=when, last_seen_at=when, first_capture_id=cap.id, status="confirmed",
                      x1=0, y1=0, x2=10, y2=10, species=species, species_conf=conf, review_status=status)
            db.add(t)
            db.flush()
            ids.append(t.id)
        return ids


def test_one_in_ten_sure_labels_is_spot_checked_and_scored():
    ids = trap_with_tracks([("CM", 0.95, "auto", 1)] * 20 + [("CM", 0.6, "review", 1)])
    with session_scope() as db:
        pending = [t.id for t in services.pending_reviews(db, "T1")]
    spot = [i for i in ids[:20] if i % services.AUDIT_EVERY == 0]
    assert len(spot) == 2 and set(pending) == set(spot) | {ids[20]}
    with TestClient(create_app()) as client:
        client.post(f"/tracks/{spot[0]}/review", data={"label": "CM"})
        client.post(f"/tracks/{spot[1]}/review", data={"label": "OFM"})   # the model was sure, and wrong
        with session_scope() as db:
            assert services.spot_checks(db, "T1") == {"checked": 2, "agreed": 1}
            assert [t.id for t in services.pending_reviews(db, "T1")] == [ids[20]]
        assert "1 of 2 agreed" in client.get("/traps/T1").text


def test_biofix_says_when_it_rests_on_unconfirmed_catches():
    # two CM a week for two weeks: the first week's are the model's unsure guesses
    ids = trap_with_tracks([("CM", 0.6, "review", 12), ("CM", 0.4, "unknown", 11),
                            ("CM", 0.95, "auto", 5), ("CM", 0.95, "auto", 4)])
    with session_scope() as db:
        s = services.phenology_status(db, db.get(Trap, "T1"))
        assert s["biofix"] is not None and s["biofix_sure"] is None and s["unsure_catches"] == 2
    with TestClient(create_app()) as client:
        assert "Provisional" in client.get("/traps/T1").text
        for i in ids[:2]:
            client.post(f"/tracks/{i}/review", data={"label": "CM"})
        assert "Provisional" not in client.get("/traps/T1").text
    with session_scope() as db:
        s = services.phenology_status(db, db.get(Trap, "T1"))
        assert s["biofix_sure"] == s["biofix"] and s["unsure_catches"] == 0
