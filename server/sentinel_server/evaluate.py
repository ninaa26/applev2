"""Score the pipeline against a person's count: the report's accuracy numbers.

    sentinel-server evaluate --counts truth/counts.csv [--boxes truth/boxes.csv] [--out report.md]
    sentinel-server evaluate                 # confirmation stats only, for every card

Three results, each with a pass/fail target:

1. Count accuracy per card, 1 - |automatic - manual| / manual, for each pest and for all moths.
   Target >= 0.80: Suto (2022) found no standard metric but says forecasting tolerates ~20% error.
2. Detection, from boxes drawn on some photos: a detection matches a drawn insect when
   IoMin = overlap / smaller box area > 0.5 (Ding & Taylor 2016), which suits small insects
   better than IoU. A detection counted as n touching insects may match up to n drawn ones.
3. Biofix: NEWA's sustained-catch date from the manual counts vs from the automatic ones, per
   trap. Target: within --biofix-days (default 1). This is the decision growers act on.

Plus what two-photo confirmation does (track.py): insects seen once and never again (dropped),
and the count you'd get without confirmation, next to the manual count when there is one.

Input files (CSV with a header):
  counts.csv  card,date,label,count   card = the dashboard's liner id; date = local date the
              insects were first on the liner; label = CM, OFM, OBLR, other_moth, other_insect or
              debris. One row per card/date/label; days with no catch need no row.
  boxes.csv   photo,x1,y1,x2,y2[,label]   photo = the capture's file name (e.g.
              20260924T175641Z_T1.jpg); box in pixels of that photo.
"""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import phenology, services
from .models import Capture, Card, Detection, Track, Trap

PESTS = ("CM", "OFM", "OBLR")
MOTHS = {"CM", "OFM", "OBLR", "other_moth", "unclassified"}  # "all moths": what the detector should count


@dataclass
class Targets:
    count: float = 0.80
    iomin: float = 0.5
    biofix_days: int = 1


def count_accuracy(auto: float, manual: float) -> float | None:
    return None if manual == 0 else 1 - abs(auto - manual) / manual


def iomin(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return ix * iy / smaller if smaller > 0 else 0.0


def match_boxes(truth: list[tuple], dets: list[tuple], capacity: list[int], thr: float) -> dict[int, int]:
    """Greedy by IoMin: {truth index: detection index}. Detection j can take capacity[j] truths."""
    pairs = sorted(((iomin(t, d), i, j) for i, t in enumerate(truth) for j, d in enumerate(dets)), reverse=True)
    left, out = list(capacity), {}
    for score, i, j in pairs:
        if score <= thr:
            break
        if i not in out and left[j] > 0:
            out[i] = j
            left[j] -= 1
    return out


# ------------------------------------------------------------------ reading truth files

def read_counts(path: Path) -> dict[int, list[tuple[date, str, int]]]:
    out: dict[int, list] = defaultdict(list)
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            out[int(r["card"])].append((date.fromisoformat(r["date"].strip()), r["label"].strip(), int(r["count"])))
    return dict(out)


def read_boxes(path: Path) -> dict[str, list[tuple]]:
    out: dict[str, list] = defaultdict(list)
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            box = tuple(float(r[k]) for k in ("x1", "y1", "x2", "y2"))
            out[r["photo"].strip()].append((*box, (r.get("label") or "").strip()))
    return dict(out)


# ------------------------------------------------------------------ the three results

@dataclass
class Report:
    targets: Targets
    counts: list[dict] = field(default_factory=list)
    confirmation: list[dict] = field(default_factory=list)
    detection: dict | None = None
    biofix: list[dict] = field(default_factory=list)


def card_tracks(db: Session, card_id: int) -> list[Track]:
    return [t for t in db.scalars(select(Track).where(Track.card_id == card_id)) if t.review_status != "rejected"]


def auto_counts(tracks: list[Track], statuses: set[str]) -> Counter:
    c: Counter = Counter()
    for t in tracks:
        if t.status in statuses:
            c[t.label] += t.n_insects
    return c


def evaluate(db: Session, counts: dict | None = None, boxes: dict | None = None,
             targets: Targets | None = None) -> Report:
    rep = Report(targets or Targets())
    cards = sorted(counts) if counts else list(db.scalars(select(Card.id).order_by(Card.id)))

    for cid in cards:
        card = db.get(Card, cid)
        if card is None:
            rep.counts.append({"card": cid, "error": "no such liner in the database"})
            continue
        tracks = card_tracks(db, cid)
        confirmed = auto_counts(tracks, {"confirmed"})
        everything = auto_counts(tracks, {"confirmed", "candidate", "dropped"})
        moths = lambda c: sum(v for k, v in c.items() if k in MOTHS)  # noqa: E731
        rep.confirmation.append({
            "card": cid, "trap": card.trap_id,
            "confirmed": moths(confirmed),
            "pending": moths(auto_counts(tracks, {"candidate"})),
            "dropped": moths(auto_counts(tracks, {"dropped"})),
            "without_confirmation": moths(everything),
        })
        if counts:
            manual: Counter = Counter()
            for _, label, n in counts[cid]:
                manual[label] += n
            rows = [(p, confirmed[p], everything[p], manual[p]) for p in PESTS if manual[p] or confirmed[p]]
            rows.append(("all moths", moths(confirmed), moths(everything), moths(manual)))
            for label, a, a_all, m in rows:
                acc = count_accuracy(a, m)
                rep.counts.append({
                    "card": cid, "trap": card.trap_id, "label": label, "manual": m, "auto": a,
                    "accuracy": acc, "pass": acc is not None and acc >= rep.targets.count,
                    "auto_without_confirmation": a_all, "accuracy_without_confirmation": count_accuracy(a_all, m),
                })

    if boxes:
        rep.detection = detection_scores(db, boxes, rep.targets.iomin)

    if counts:
        by_trap: dict[str, list[int]] = defaultdict(list)
        for cid in cards:
            card = db.get(Card, cid)
            if card is not None:
                by_trap[card.trap_id].append(cid)
        for trap_id, cids in sorted(by_trap.items()):
            trap = db.get(Trap, trap_id)
            manual_dates = sorted(d for cid in cids for d, label, n in counts[cid] if label == trap.lure for _ in range(n))
            m = phenology.sustained_biofix(manual_dates)
            a = phenology.sustained_biofix(services.lure_catch_dates(db, trap, set(cids)))
            if m is None and a is None:
                ok, diff = True, None
            elif m is None or a is None:
                ok, diff = False, None
            else:
                diff = (a - m).days
                ok = abs(diff) <= rep.targets.biofix_days
            rep.biofix.append({"trap": trap_id, "lure": trap.lure, "manual": m, "auto": a, "days_off": diff, "pass": ok})
    return rep


def detection_scores(db: Session, boxes: dict, thr: float) -> dict:
    tp = n_truth = n_det = det_hit = 0
    label_ok = label_n = 0
    missing = []
    for photo, truth in sorted(boxes.items()):
        cap = db.scalar(select(Capture).where(Capture.image_path.like(f"%{photo}")))
        if cap is None:
            missing.append(photo)
            continue
        dets = list(db.scalars(select(Detection).where(Detection.capture_id == cap.id)))
        match = match_boxes([t[:4] for t in truth], [(d.x1, d.y1, d.x2, d.y2) for d in dets],
                            [d.n_insects for d in dets], thr)
        n_truth += len(truth)
        n_det += len(dets)
        tp += len(match)
        det_hit += len(set(match.values()))
        for i, j in match.items():
            want = truth[i][4]
            if want and dets[j].track_id:
                label_n += 1
                label_ok += db.get(Track, dets[j].track_id).label == want
    precision = det_hit / n_det if n_det else 0.0
    recall = tp / n_truth if n_truth else 0.0
    return {"photos": len(boxes) - len(missing), "missing_photos": missing, "insects": n_truth, "detections": n_det,
            "matched": tp, "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
            "label_accuracy": label_ok / label_n if label_n else None, "labelled_matches": label_n}


# ------------------------------------------------------------------ output

def _pct(x) -> str:
    return "n/a" if x is None else f"{x:.2f}"


def to_markdown(rep: Report) -> str:
    t = rep.targets
    out = ["# Pipeline evaluation", ""]
    if rep.counts:
        rows = [r for r in rep.counts if "error" not in r]
        passed = sum(r["pass"] for r in rows if r["label"] == "all moths")
        n_cards = sum(1 for r in rows if r["label"] == "all moths")
        out += [f"## 1. Count accuracy per liner (target >= {t.count:.2f})", "",
                f"**{passed}/{n_cards} liners pass on all moths.** Accuracy = 1 - |auto - manual| / manual.", "",
                "| liner | trap | label | manual | auto | accuracy | pass | auto without confirmation | accuracy without |",
                "|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            out.append(f"| {r['card']} | {r['trap']} | {r['label']} | {r['manual']} | {r['auto']} | {_pct(r['accuracy'])} | "
                       f"{'PASS' if r['pass'] else 'FAIL'} | {r['auto_without_confirmation']} | "
                       f"{_pct(r['accuracy_without_confirmation'])} |")
        out += [f"| {r['card']} | | {r['error']} | | | | | | |" for r in rep.counts if "error" in r]
        out.append("")
    if rep.detection:
        d = rep.detection
        out += [f"## 2. Detection (IoMin > {t.iomin})", "",
                f"{d['photos']} photos, {d['insects']} insects drawn, {d['detections']} detections: "
                f"precision **{d['precision']:.2f}**, recall **{d['recall']:.2f}**, F1 **{d['f1']:.2f}**."]
        if d["label_accuracy"] is not None:
            out.append(f"Species right on {d['label_accuracy']:.0%} of {d['labelled_matches']} matched, labelled insects.")
        if d["missing_photos"]:
            out.append(f"Not in the database: {', '.join(d['missing_photos'])}")
        out.append("")
    if rep.biofix:
        out += [f"## 3. Biofix (target: within {t.biofix_days} day{'s' if t.biofix_days != 1 else ''})", "",
                "| trap | lure | from manual count | from automatic count | days off | pass |", "|---|---|---|---|---|---|"]
        for b in rep.biofix:
            off = "" if b["days_off"] is None else f"{b['days_off']:+d}"
            out.append(f"| {b['trap']} | {b['lure']} | {b['manual'] or 'none yet'} | {b['auto'] or 'none yet'} | "
                       f"{off} | {'PASS' if b['pass'] else 'FAIL'} |")
        out.append("")
    if rep.confirmation:
        tot = Counter()
        for r in rep.confirmation:
            tot.update({k: r[k] for k in ("confirmed", "pending", "dropped", "without_confirmation")})
        factor = tot["without_confirmation"] / tot["confirmed"] if tot["confirmed"] else None
        out += ["## Two-photo confirmation", "",
                f"Across {len(rep.confirmation)} liners, {tot['dropped']} moth-sized detections were seen in one photo "
                f"and never again, so they were never counted. Without confirmation the count would be "
                f"{tot['without_confirmation']} instead of {tot['confirmed']}"
                + (f" ({factor:.1f}x)." if factor else ".")
                + f" {tot['pending']} are still waiting for a second photo.", "",
                "| liner | trap | confirmed | waiting | dropped | count without confirmation |", "|---|---|---|---|---|---|"]
        for r in rep.confirmation:
            out.append(f"| {r['card']} | {r['trap']} | {r['confirmed']} | {r['pending']} | {r['dropped']} | "
                       f"{r['without_confirmation']} |")
        out.append("")
    return "\n".join(out)
