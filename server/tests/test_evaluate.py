"""Evaluation against manual truth: count accuracy, IoMin detection matching, biofix, confirmation."""

from datetime import date, datetime

import pytest

from sentinel_server import evaluate as ev
from sentinel_server.cli import main as cli
from sentinel_server.db import session_scope
from sentinel_server.models import Capture, Card, Detection, Track, Trap

# Two weeks of CM catches, Monday-based weeks: 2 moths in each week -> NEWA biofix on the first one.
CATCH_DAYS = [date(2026, 6, 1), date(2026, 6, 3), date(2026, 6, 9), date(2026, 6, 10)]


def noon(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 16)  # 16:00 UTC = noon in New York


def seed(extra_auto: int = 0, shift_days: int = 0):
    """Liner 1 on trap T1: one confirmed CM per catch day (optionally shifted), plus `extra_auto`
    confirmed false positives, one dropped single-photo detection, and one rejected track."""
    with session_scope() as db:
        db.add(Trap(id="T1", lure="CM", api_key_hash="x"))
        db.flush()
        db.add(Card(id=1, trap_id="T1", installed_at=noon(date(2026, 5, 30))))
        db.flush()
        cap = Capture(id=1, trap_id="T1", card_id=1, uid="a", captured_at=noon(date(2026, 6, 10)),
                      image_path="T1/2026/06/10/20260610T160000Z_T1.jpg", width=640, height=480)
        db.add(cap)
        db.flush()

        def track(d, status="confirmed", label="CM", review="auto", n=1, box=(0, 0, 10, 10)):
            t = Track(card_id=1, first_seen_at=noon(d), last_seen_at=noon(d), first_capture_id=1, status=status,
                      x1=box[0], y1=box[1], x2=box[2], y2=box[3], prob_sum={}, species=label, review_status=review,
                      n_insects=n)
            db.add(t)
            db.flush()
            db.add(Detection(capture_id=1, track_id=t.id, x1=box[0], y1=box[1], x2=box[2], y2=box[3],
                             det_conf=0.9, probs={}, n_insects=n))

        for k, d in enumerate(CATCH_DAYS):
            track(date.fromordinal(d.toordinal() + shift_days), box=(100 * k, 0, 100 * k + 40, 20))
        for k in range(extra_auto):
            track(date(2026, 6, 10), label="other_moth", box=(500, 100 * k, 520, 100 * k + 20))
        track(date(2026, 6, 10), status="dropped", label="other_moth", box=(600, 400, 610, 410))
        track(date(2026, 6, 10), label="CM", review="rejected", box=(620, 400, 630, 410))


def manual_counts():
    return {1: [(d, "CM", 1) for d in CATCH_DAYS]}


def test_iomin_suits_a_small_insect_inside_a_loose_box():
    moth, loose = (10, 10, 20, 14), (0, 0, 40, 30)
    assert ev.iomin(moth, loose) == pytest.approx(1.0)  # IoU would be 40 / 1200 = 0.03
    assert ev.iomin(moth, (100, 100, 110, 110)) == 0.0


def test_a_touching_pair_box_matches_both_insects():
    truth = [(0, 0, 10, 4), (0, 5, 10, 9), (50, 50, 60, 54)]
    dets = [(0, 0, 10, 9)]
    assert ev.match_boxes(truth, dets, [2], 0.5) == {0: 0, 1: 0}
    assert len(ev.match_boxes(truth, dets, [1], 0.5)) == 1


def test_count_accuracy_biofix_and_confirmation():
    seed(extra_auto=1)
    with session_scope() as db:
        rep = ev.evaluate(db, manual_counts())
    by = {r["label"]: r for r in rep.counts}
    assert by["CM"]["auto"] == 4 and by["CM"]["accuracy"] == 1.0 and by["CM"]["pass"]
    # all moths: 4 CM + 1 false other_moth = 5 vs 4 manual -> 0.75, below the 0.80 target
    assert by["all moths"]["auto"] == 5 and by["all moths"]["accuracy"] == pytest.approx(0.75)
    assert not by["all moths"]["pass"]
    assert by["all moths"]["auto_without_confirmation"] == 6  # + the dropped single-photo detection
    assert rep.confirmation == [{"card": 1, "trap": "T1", "confirmed": 5, "pending": 0, "dropped": 1,
                                 "without_confirmation": 6}]
    assert rep.biofix == [{"trap": "T1", "lure": "CM", "manual": date(2026, 6, 1), "auto": date(2026, 6, 1),
                           "days_off": 0, "pass": True}]


def test_biofix_a_week_late_fails():
    seed(shift_days=7)
    with session_scope() as db:
        b = ev.evaluate(db, manual_counts()).biofix[0]
    assert b["days_off"] == 7 and not b["pass"]


def test_detection_scores_and_cli_report(tmp_path, capsys):
    seed()
    counts = tmp_path / "counts.csv"
    counts.write_text("card,date,label,count\n" + "".join(f"1,{d},CM,1\n" for d in CATCH_DAYS))
    boxes = tmp_path / "boxes.csv"
    boxes.write_text("photo,x1,y1,x2,y2,label\n"
                     "20260610T160000Z_T1.jpg,5,2,30,15,CM\n"        # inside the first CM's box
                     "20260610T160000Z_T1.jpg,105,2,130,15,OFM\n"    # matched, but the model said CM
                     "20260610T160000Z_T1.jpg,300,300,320,315,CM\n")  # missed
    with session_scope() as db:
        d = ev.detection_scores(db, ev.read_boxes(boxes), 0.5)
    assert d["insects"] == 3 and d["matched"] == 2 and d["recall"] == pytest.approx(2 / 3)
    assert d["detections"] == 6 and d["precision"] == pytest.approx(2 / 6)  # 4 CM, 1 dropped, 1 rejected
    assert d["label_accuracy"] == 0.5

    out = tmp_path / "report.md"
    assert cli(["evaluate", "--counts", str(counts), "--boxes", str(boxes), "--out", str(out)]) == 0
    text = out.read_text()
    assert "1/1 liners pass" in text and "IoMin > 0.5" in text and "| T1 | CM | 2026-06-01 | 2026-06-01 | +0 | PASS |" in text
    assert "1 moth-sized detections were seen in one photo" in text
