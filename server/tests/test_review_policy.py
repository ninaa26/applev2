"""Who gets shown to a person, and how the biofix says what it rests on."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from sentinel_server import services
from sentinel_server.app import create_app
from sentinel_server.db import session_scope
from sentinel_server.models import Capture, Card, Track, Trap, utcnow


def trap_with_tracks(specs, now=None):
    """specs: (species, confidence, review_status, days ago). Returns the track ids."""
    now = now or utcnow()
    with session_scope() as db:
        db.add(Trap(id="T1", name="bench", lure="CM", api_key_hash=services.hash_key("k")))
        card = Card(trap_id="T1")
        db.add(card)
        db.flush()
        cap = Capture(trap_id="T1", card_id=card.id, uid="c1", captured_at=now, image_path="x.jpg")
        db.add(cap)
        db.flush()
        ids = []
        for species, conf, status, days in specs:
            when = now - timedelta(days=days)
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


def test_a_lure_change_applies_from_the_new_liner_on():
    """The lure is kept per liner. Swapping a CM lure for an OFM one used to reinterpret every past catch:
    OFM bycatch on the old CM liner then counted towards the OFM biofix."""
    from datetime import date

    now = datetime(2026, 7, 20, 16)
    first = trap_with_tracks([("OFM", 0.95, "auto", d) for d in (40, 39, 33, 32)], now=now)  # on the CM liner
    with session_scope() as db:
        old = db.get(Track, first[0]).card_id
        new = services.start_new_card(db, "T1", at=now - timedelta(days=20), lure="OFM")
        assert db.get(Trap, "T1").lure == "OFM" and new.lure == "OFM"
        assert db.get(Card, old).lure == "CM"  # the liner it replaced keeps the lure it had
        cap = db.query(Capture).first()
        for d in (12, 11, 5, 4):
            when = now - timedelta(days=d)
            db.add(Track(card_id=new.id, first_seen_at=when, last_seen_at=when, first_capture_id=cap.id,
                         status="confirmed", x1=0, y1=0, x2=10, y2=10, species="OFM", species_conf=0.95,
                         review_status="auto"))
    with session_scope() as db:
        dates = services.lure_catch_dates(db, db.get(Trap, "T1"))
    assert dates == sorted((now - timedelta(days=d)).date() for d in (12, 11, 5, 4)), dates
    with TestClient(create_app()) as client:  # the dashboard's "New liner installed" can change the lure too
        client.post("/traps/T1/new-card", data={"note": "OBLR now", "lure": "OBLR"})
        assert client.post("/traps/T1/new-card", data={"lure": "PX"}).status_code == 422
    with session_scope() as db:
        assert db.get(Trap, "T1").lure == "OBLR" and services.open_card(db, "T1").lure == "OBLR"

def test_biofix_says_when_it_rests_on_unconfirmed_catches(monkeypatch):
    # two CM a week for two weeks: the first week's are the model's unsure guesses. "Now" is pinned to a
    # Wednesday in June so each pair lands in one Monday–Sunday week and in this season, whatever today is.
    now = datetime(2026, 6, 17, 16)
    monkeypatch.setattr(services, "utcnow", lambda: now)
    ids = trap_with_tracks([("CM", 0.6, "review", 12), ("CM", 0.4, "unknown", 11),
                            ("CM", 0.95, "auto", 5), ("CM", 0.95, "auto", 4)], now=now)
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


def test_biofix_comes_from_this_seasons_catches_only():
    # last year's catches qualified two weeks in a row; nothing yet this year
    trap_with_tracks([("CM", 0.95, "auto", d) for d in (380, 379, 373, 372)])
    with session_scope() as db:
        s = services.phenology_status(db, db.get(Trap, "T1"))
        assert s["biofix"] is None and s["catches"] == 0 and "dd" not in s


def test_a_person_confirms_or_changes_the_biofix(monkeypatch):
    """One false catch can start the season's clock, so a person can confirm the biofix or set another date
    on the trap page. It holds for this season only, and clearing it goes back to the catches."""
    from datetime import date

    now = datetime(2026, 6, 17, 16)
    monkeypatch.setattr(services, "utcnow", lambda: now)
    trap_with_tracks([("CM", 0.6, "review", 12), ("CM", 0.4, "unknown", 11),
                      ("CM", 0.95, "auto", 5), ("CM", 0.95, "auto", 4)], now=now)
    with session_scope() as db:
        auto = services.phenology_status(db, db.get(Trap, "T1"))["biofix"]
    with TestClient(create_app()) as client:
        assert client.post("/traps/T1/biofix", data={"date": auto.isoformat()}).status_code == 200  # confirm
        page = client.get("/traps/T1").text
        assert "Provisional" not in page and "Confirmed by a person" in page
        with session_scope() as db:
            s = services.phenology_status(db, db.get(Trap, "T1"))
            assert s["biofix"] == auto and s["biofix_set"] and s["biofix_auto"] == auto

        client.post("/traps/T1/biofix", data={"date": "2026-06-10"})  # the first catch was a false one
        with session_scope() as db:
            s = services.phenology_status(db, db.get(Trap, "T1"))
            assert s["biofix"] == date(2026, 6, 10) and s["biofix_auto"] == auto
        assert "Set by a person" in client.get("/traps/T1").text

        assert client.post("/traps/T1/biofix", data={"date": "June 10"}).status_code == 422
        assert client.post("/traps/T1/biofix", data={"date": "2026-07-01"}).status_code == 422  # in the future

        client.post("/traps/T1/biofix", data={"date": ""})  # clear
        with session_scope() as db:
            s = services.phenology_status(db, db.get(Trap, "T1"))
            assert s["biofix"] == auto and not s["biofix_set"]

    with session_scope() as db:  # last season's date doesn't start this season's clock
        db.get(Trap, "T1").biofix_date = date(2025, 5, 20)
    with session_scope() as db:
        s = services.phenology_status(db, db.get(Trap, "T1"))
        assert s["biofix"] == auto and not s["biofix_set"]
