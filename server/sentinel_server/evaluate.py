"""Score the pipeline against a person's count: the report's accuracy numbers.

    sentinel-server evaluate --counts truth/counts.csv [--boxes truth/boxes.csv] [--out report.md]
    sentinel-server evaluate                 # confirmation stats only, for every card

Three results, each with a pass/fail target:

1. Count accuracy per card, 1 - |automatic - manual| / manual, for each pest and for all moths.
   Target >= 0.80: Suto (2022) found no standard metric but says forecasting tolerates ~20% error.
   Also per trap-day (new moths that day, automatic vs manual), since a liner's total can be right
   while its days are wrong, and the days are what the biofix is made of.
2. Detection, from boxes drawn on some photos: a detection matches a drawn insect when
   IoMin = overlap / smaller box area > 0.5 (Ding & Taylor 2016), which suits small insects
   better than IoU. A detection counted as n touching insects may match up to n drawn ones.
   Recall and species accuracy are also given by the insect's size in the photo (accuracy swings
   ~20 points between small and large crops in the AMI dataset), and every detection wrongly counted
   as a moth is put down to its cause: bycatch, debris (drawn boxes labelled `debris`), or nothing there.
   With an `insect` column, the same insect followed across photos, tracking is scored too.
3. Biofix: NEWA's sustained-catch date from the manual counts vs from the automatic ones, per
   trap. Target: within --biofix-days (default 1). This is the decision growers act on.

Plus the photos themselves: how many were left out as unusable and why (about 7% of camera-trap photos
were unusable in one study), whether the smallest target is big enough in them (px/mm from the liner's
grid; an OFM is 6 mm and needs >= 50 px), glare, and how old each liner got.

Plus what two-photo confirmation does (track.py): insects seen once and never again (dropped),
and the count you'd get without confirmation, next to the manual count when there is one.

Input files (CSV with a header):
  counts.csv  card,date,label,count   card = the dashboard's liner id; date = local date the
              insects were first on the liner; label = CM, OFM, OBLR, other_moth, other_insect or
              debris. One row per card/date/label; days with no catch need no row.
  boxes.csv   photo,x1,y1,x2,y2[,label[,insect]]   photo = the capture's file name (e.g.
              20260924T175641Z_T1.jpg); box in pixels of that photo. label `debris` marks something
              drawn that is not an insect (leaf bit, scales, lure). insect = any name for that
              insect, the same in every photo of the liner it is boxed in.
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
SIZE_BINS = ((0, 30), (30, 75), (75, 150), (150, None))  # long side of the drawn box, px
SMALLEST_TARGET_MM, SMALLEST_TARGET_PX = 6.0, 50  # OFM; below ~50 px the classifier is guessing (docs/camera-bench.md)


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
            out[r["photo"].strip()].append((*box, (r.get("label") or "").strip(), (r.get("insect") or "").strip()))
    return dict(out)


# ------------------------------------------------------------------ the three results

@dataclass
class Report:
    targets: Targets
    counts: list[dict] = field(default_factory=list)
    days: list[dict] = field(default_factory=list)
    photos: dict | None = None
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
            manual_day: Counter = Counter()
            for d, label, n in counts[cid]:
                if label in MOTHS:
                    manual_day[d] += n
            auto_day: Counter = Counter()
            for t in tracks:
                if t.status == "confirmed" and t.label in MOTHS:
                    auto_day[services.local_date(t.first_seen_at)] += t.n_insects
            for d in sorted(set(manual_day) | set(auto_day)):
                m, a = manual_day[d], auto_day[d]
                # within the count target, or one moth: a day with 2 moths can't be closer than 50% otherwise
                rep.days.append({"card": cid, "trap": card.trap_id, "date": d, "manual": m, "auto": a,
                                 "liner_day": (d - services.local_date(card.installed_at)).days,
                                 "ok": abs(a - m) <= max(1, (1 - rep.targets.count) * m)})

    rep.photos = photo_stats(db, cards)
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


def photo_stats(db: Session, cards: list[int]) -> dict:
    caps = [c for c in db.scalars(select(Capture).where(Capture.card_id.in_(cards))) if c.status in ("processed", "failed")]
    left_out: Counter = Counter()
    for c in caps:
        if c.status == "failed":
            why = c.error or "failed"
            left_out["blurred" if "blurred" in why else "scale or grid" if why.startswith("photo not used") else "error"] += 1
    used = [c.meta or {} for c in caps if c.status == "processed"]
    ppm = sorted(m["px_per_mm"] for m in used if m.get("px_per_mm"))
    mid = ppm[len(ppm) // 2] if ppm else None
    return {"photos": len(caps), "left_out": dict(left_out), "px_per_mm": mid,
            "smallest_px": round(mid * SMALLEST_TARGET_MM) if mid else None,
            "max_glare": max((m.get("glare", 0.0) for m in used), default=0.0),
            "oldest_liner_days": max((m.get("liner_days", 0.0) for m in used), default=0.0)}


def size_bin(box) -> int:
    long_side = max(box[2] - box[0], box[3] - box[1])
    return next(k for k, (lo, hi) in enumerate(SIZE_BINS) if long_side >= lo and (hi is None or long_side < hi))


def detection_scores(db: Session, boxes: dict, thr: float) -> dict:
    tp = n_truth = n_det = det_hit = 0
    label_ok = label_n = 0
    missing = []
    by_size = [{"insects": 0, "found": 0, "labelled": 0, "label_ok": 0} for _ in SIZE_BINS]
    wrong_moths: Counter = Counter()  # cause -> detections counted as a moth that are not one
    counted_moths = 0
    tracks_of: dict[tuple, set] = defaultdict(set)   # (liner, insect name) -> tracks it was matched to
    insects_of: dict[int, set] = defaultdict(set)    # track -> insect names matched to it
    for photo, rows in sorted(boxes.items()):
        cap = db.scalar(select(Capture).where(Capture.image_path.like(f"%{photo}")))
        if cap is None:
            missing.append(photo)
            continue
        truth = [t for t in rows if t[4] != "debris"]
        debris = [t for t in rows if t[4] == "debris"]
        dets = list(db.scalars(select(Detection).where(Detection.capture_id == cap.id)))
        det_boxes = [(d.x1, d.y1, d.x2, d.y2) for d in dets]
        match = match_boxes([t[:4] for t in truth], det_boxes, [d.n_insects for d in dets], thr)
        on_debris = set(match_boxes([t[:4] for t in debris], det_boxes, [1] * len(dets), thr).values())
        n_truth += len(truth)
        n_det += len(dets)
        tp += len(match)
        det_hit += len(set(match.values()))
        for i, t in enumerate(truth):
            b = by_size[size_bin(t)]
            b["insects"] += 1
            b["found"] += i in match
        truth_of: dict[int, list] = defaultdict(list)
        for i, j in match.items():
            truth_of[j].append(truth[i])
            want, name = truth[i][4], truth[i][5]
            track = db.get(Track, dets[j].track_id) if dets[j].track_id else None
            if want and track is not None:
                right = track.label == want
                label_n += 1
                label_ok += right
                b = by_size[size_bin(truth[i])]
                b["labelled"] += 1
                b["label_ok"] += right
            if name and track is not None:
                tracks_of[(cap.card_id, name)].add(track.id)
                insects_of[track.id].add(name)
        for j, d in enumerate(dets):
            track = db.get(Track, d.track_id) if d.track_id else None
            if track is None or track.status == "dropped" or track.review_status == "rejected" or track.label not in MOTHS:
                continue  # not counted as a moth
            counted_moths += 1
            drawn = [t[4] for t in truth_of.get(j, [])]
            if not drawn:
                wrong_moths["debris" if j in on_debris else "nothing drawn there"] += 1
            elif all(lab and lab not in MOTHS for lab in drawn):
                wrong_moths[drawn[0]] += 1
    precision = det_hit / n_det if n_det else 0.0
    recall = tp / n_truth if n_truth else 0.0
    tracking = None
    if tracks_of:
        tracking = {"insects": len(tracks_of), "split": sum(len(v) > 1 for v in tracks_of.values()),
                    "merged_tracks": sum(len(v) > 1 for v in insects_of.values())}
    return {"photos": len(boxes) - len(missing), "missing_photos": missing, "insects": n_truth, "detections": n_det,
            "matched": tp, "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
            "label_accuracy": label_ok / label_n if label_n else None, "labelled_matches": label_n,
            "by_size": by_size, "counted_moths": counted_moths, "wrong_moths": dict(wrong_moths), "tracking": tracking}


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
    if rep.days:
        n, ok = len(rep.days), sum(r["ok"] for r in rep.days)
        mae = sum(abs(r["auto"] - r["manual"]) for r in rep.days) / n
        out += ["### Per trap-day", "",
                f"{n} trap-days with a catch (manual or automatic), all moths: mean error **{mae:.1f}** moths a day; "
                f"**{ok}/{n}** days within {1 - t.count:.0%} or one moth of the manual count.", ""]
        off = [r for r in rep.days if not r["ok"]]
        if off:
            out += ["| liner | trap | day | day of liner | manual | auto |", "|---|---|---|---|---|---|"]
            out += [f"| {r['card']} | {r['trap']} | {r['date']} | {r['liner_day']} | {r['manual']} | {r['auto']} |" for r in off]
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
        out += ["", "| drawn insect's long side | insects | found | recall | species right |", "|---|---|---|---|---|"]
        for (lo, hi), b in zip(SIZE_BINS, d["by_size"]):
            if b["insects"]:
                name = f"{lo}–{hi} px" if hi else f"over {lo} px"
                species = f"{b['label_ok']}/{b['labelled']}" if b["labelled"] else ""
                out.append(f"| {name} | {b['insects']} | {b['found']} | {b['found'] / b['insects']:.2f} | {species} |")
        wrong = sum(d["wrong_moths"].values())
        out += ["", f"Of {d['counted_moths']} detections counted as a moth on these photos, **{wrong}** were not one"
                + (": " + ", ".join(f"{n} {cause}" for cause, n in sorted(d["wrong_moths"].items(), key=lambda kv: -kv[1])) + "."
                   if wrong else ".")]
        if d["tracking"]:
            k = d["tracking"]
            out.append(f"Tracking, {k['insects']} insects followed across photos: {k['split']} were given more than one "
                       f"track (counted twice); {k['merged_tracks']} tracks took in more than one insect (counted once).")
        out.append("")
    if rep.biofix:
        out += [f"## 3. Biofix (target: within {t.biofix_days} day{'s' if t.biofix_days != 1 else ''})", "",
                "| trap | lure | from manual count | from automatic count | days off | pass |", "|---|---|---|---|---|---|"]
        for b in rep.biofix:
            off = "" if b["days_off"] is None else f"{b['days_off']:+d}"
            out.append(f"| {b['trap']} | {b['lure']} | {b['manual'] or 'none yet'} | {b['auto'] or 'none yet'} | "
                       f"{off} | {'PASS' if b['pass'] else 'FAIL'} |")
        out.append("")
    if rep.photos and rep.photos["photos"]:
        p = rep.photos
        n_out = sum(p["left_out"].values())
        out += ["## Photos", "",
                f"{p['photos']} photos, **{n_out}** left out ({n_out / p['photos']:.0%})"
                + (": " + ", ".join(f"{n} {why}" for why, n in sorted(p["left_out"].items())) if n_out else "") + "."]
        if p["px_per_mm"]:
            ok = p["smallest_px"] >= SMALLEST_TARGET_PX
            out.append(f"Scale {p['px_per_mm']:.1f} px/mm (median, from the liner grid): an OFM ({SMALLEST_TARGET_MM:g} mm) is "
                       f"about {p['smallest_px']} px long, {'enough' if ok else '**too few**'} (need ≥ {SMALLEST_TARGET_PX}).")
        out += [f"Most glare in one photo: {p['max_glare']:.1%} of the card blown out. "
                f"Oldest liner photographed: {p['oldest_liner_days']:.0f} days.", ""]
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
