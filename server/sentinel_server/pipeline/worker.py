"""Process new captures: detect → track → classify → update counts and events."""

from __future__ import annotations

import logging
import math
import time
from pathlib import Path

import cv2
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import services
from ..db import session_scope
from ..models import Capture, Card, Detection, Event, Track, Trap, utcnow
from ..settings import get_settings
from . import track as trk
from .classify import crop, make_classifier
from .detect import card_outline, in_mask, make_detector, photo_quality

log = logging.getLogger(__name__)

SCALE_TOLERANCE = 0.20  # a photo whose px/mm is further than this from the liner's other photos is not trusted
BLURRED_BELOW = 0.4     # ... or whose sharpness is under this share of theirs (repeat shots vary by ~30%)
GLARE_WARN = 0.02       # share of the card blown out to white that raises a "glare" event


def moon_illumination(when) -> float:
    """Fraction of the moon's disc lit (0 new, 1 full), to a few percent: context logged with each photo,
    since moonlight changes how many moths fly."""
    days = (when - type(when)(2000, 1, 6, 18, 14)).total_seconds() / 86400
    return round((1 - math.cos(2 * math.pi * (days % 29.530588853) / 29.530588853)) / 2, 2)


def blur_problem(earlier: list[float], now: float) -> str | None:
    """Why this photo is too blurred to use, or None: judged against the same liner's other photos, since
    sharpness depends on the camera, the light and what is on the card."""
    if len(earlier) < 2:
        return None
    usual = sorted(earlier)[len(earlier) // 2]
    if now < BLURRED_BELOW * usual:
        return f"blurred: sharpness {now:.0f}, this liner's other photos {usual:.0f}"
    return None


def scale_problem(earlier: list[float], now: float | None) -> str | None:
    """Why this photo's scale can't be right, or None. The camera and liner don't move, so every photo of
    a liner has the same px/mm; one that reads differently (or shows no grid at all, when the others did)
    is blurred, mis-exposed, knocked, or had its grid misread, and its boxes would be sized wrongly. Such a
    photo is left out rather than allowed to drop real insects and add false ones. A new liner starts afresh,
    so a camera that really was changed is believed from the next liner on."""
    if len(earlier) < 2:  # one photo is not enough to say which of two is the odd one
        return None
    usual = sorted(earlier)[len(earlier) // 2]
    if now is None:
        return f"no liner grid found (this liner's other photos: {usual:.1f} px/mm)"
    if abs(now / usual - 1) > SCALE_TOLERANCE:
        return f"scale reads {now:.1f} px/mm, this liner's other photos {usual:.1f}"
    return None


class Pipeline:
    def __init__(self, detector_name: str | None = None, classifier_name: str | None = None):
        s = get_settings()
        self.detector = make_detector(detector_name or s.detector)
        self.classifier = make_classifier(classifier_name or s.classifier)

    @property
    def version(self) -> str:
        return f"{self.detector.version}+{self.classifier.version}"

    def process(self, db: Session, cap: Capture, check_liner: bool = True) -> None:
        trap = db.get(Trap, cap.trap_id)
        path = get_settings().media_dir / cap.image_path
        boxes = self.detector.detect(path, key=(cap.trap_id, cap.card_id))
        info = getattr(self.detector, "last", {})
        before = [c.meta or {} for c in db.scalars(select(Capture).where(
            Capture.card_id == cap.card_id, Capture.status == "processed", Capture.id != cap.id))]
        bgr = cv2.imread(str(path))
        quality = photo_quality(bgr, info["card"] if "card" in info else card_outline(bgr))
        problem = blur_problem([m["sharpness"] for m in before if m.get("sharpness")], quality["sharpness"])
        ppm = None
        if info.get("grid") is not None:  # detectors that measure the liner's grid
            ppm = float(info["px_per_mm"]) if info["grid"].score > 0 and info.get("px_per_mm") else None
            problem = scale_problem([m["px_per_mm"] for m in before if m.get("px_per_mm")], ppm) or problem
        if problem:
            log.warning("capture %s left out: %s", cap.id, problem)
            cap.status, cap.processed_at, cap.model_version = "failed", utcnow(), self.version
            cap.error = f"photo not used: {problem}"
            return
        card = db.get(Card, cap.card_id)
        liner_days = round((cap.captured_at - card.installed_at).total_seconds() / 86400, 1)
        cap.meta = {**(cap.meta or {}), **quality, **({"px_per_mm": round(ppm, 2)} if ppm else {}),
                    "liner_days": liner_days, "moon": moon_illumination(cap.captured_at)}
        if quality["glare"] > GLARE_WARN:
            _event_once(db, cap, "glare", {"share_of_card": quality["glare"]})
        if liner_days > get_settings().liner_max_days:
            _event_once(db, cap, "card_old", {"days": liner_days})
        with Image.open(path) as img:
            w, h = img.size
            boxes = [b for b in boxes if not in_mask(b, trap.mask, w, h)]
            probs = self.classifier.classify([crop(img, b) for b in boxes])
        cap.width, cap.height = w, h
        if check_liner:
            _keep_liner_if_unchanged(db, cap, [trk.Rect(b.x1, b.y1, b.x2, b.y2) for b in boxes])

        # Tracks on this card that are still alive.
        live = list(
            db.scalars(
                select(Track).where(Track.card_id == cap.card_id, Track.status.in_(["candidate", "confirmed"]))
            )
        )
        rects = [trk.Rect(t.x1, t.y1, t.x2, t.y2) for t in live]
        det_rects = [trk.Rect(b.x1, b.y1, b.x2, b.y2) for b in boxes]
        matches = trk.match(rects, det_rects)

        seen_tracks = set()
        for di, (box, p) in enumerate(zip(boxes, probs)):
            if di in matches:
                t = live[matches[di]]
                t.n_seen += 1
                t.misses = 0
                t.last_seen_at = cap.captured_at
                t.x1, t.y1, t.x2, t.y2 = box.x1, box.y1, box.x2, box.y2
                if not t.reviewed:  # a reviewer's count stands
                    t.n_insects = box.n
            else:
                t = Track(
                    card_id=cap.card_id, first_seen_at=cap.captured_at, last_seen_at=cap.captured_at,
                    first_capture_id=cap.id, x1=box.x1, y1=box.y1, x2=box.x2, y2=box.y2, prob_sum={},
                    n_insects=box.n,
                )
                db.add(t)
                db.flush()
            seen_tracks.add(t.id)
            if p and trk.fresh(t.first_seen_at, cap.captured_at, t.n_classified):
                summed = dict(t.prob_sum or {})
                for k, v in p.items():
                    summed[k] = summed.get(k, 0.0) + v
                t.prob_sum = summed
                t.n_classified += 1
            if not t.reviewed:
                t.species, t.species_conf, t.review_status = trk.consensus(t.prob_sum, t.n_classified)
                if t.n_insects > 1:  # touching insects: a person checks the count
                    t.review_status = "review"
            if t.status == "candidate" and t.n_seen >= trk.CONFIRM_AFTER:
                t.status = "confirmed"
                t.confirmed_at = cap.captured_at
            db.add(Detection(
                capture_id=cap.id, track_id=t.id, x1=box.x1, y1=box.y1, x2=box.x2, y2=box.y2,
                det_conf=box.conf, n_insects=box.n, probs=p, model_version=self.version,
            ))

        for t in live:
            if t.id not in seen_tracks:
                t.misses += 1
                if t.status == "candidate" and t.misses >= trk.DROP_CANDIDATE_AFTER:
                    t.status = "dropped"

        cap.status, cap.processed_at, cap.model_version, cap.error = "processed", utcnow(), self.version, None
        _card_full_check(db, cap, len(boxes))

    def reprocess_card(self, db: Session, card_id: int) -> int:
        """Re-run every photo of a card from scratch (e.g. after a model upgrade)."""
        caps = list(db.scalars(select(Capture).where(Capture.card_id == card_id).order_by(Capture.captured_at)))
        for c in caps:  # detections first: they reference the tracks
            for d in list(c.detections):
                db.delete(d)
            c.status = "new"
        db.flush()
        for t in db.scalars(select(Track).where(Track.card_id == card_id)):
            if not t.reviewed:  # people's labels and rejections are kept (and reviews point at them)
                db.delete(t)
        db.flush()
        for c in caps:
            self.process(db, c, check_liner=False)  # which liner each photo is on was settled the first time
            db.flush()
        return len(caps)


SAME_LINER_MIN_MATCHED = 0.5  # share of the old liner's insects that must still be in place


def same_liner_as_before(old: list[trk.Rect], now: list[trk.Rect]) -> bool | None:
    """Is this photo still the previous liner? None when that liner had no insects to go by.

    A fresh liner is nearly empty and nothing on it sits where the old insects were. If at least half
    of the insects counted on the old liner, and seen in its last photo, are still in the same places,
    the liner was not changed. Erring this way is the cheap mistake: a missed new liner keeps every count
    (the dashboard button starts it for real), a false one counts every insect on the old liner again.
    """
    if not old:
        return None
    return len(trk.match(old, now)) >= SAME_LINER_MIN_MATCHED * len(old)


def _keep_liner_if_unchanged(db: Session, cap: Capture, boxes: list[trk.Rect]) -> None:
    """The trap reads any press of its power button as "new liner", and cannot tell a press from its battery
    being swapped. If this photo opened a liner that way, check the claim against the liner before it."""
    card = db.get(Card, cap.card_id)
    meta = cap.meta or {}
    if not meta.get("new_card") or meta.get("new_card_source", "button") != "button":
        return  # an ordinary photo, or someone asked for the new liner outright
    if card.installed_at != cap.captured_at or db.scalar(select(Track.id).where(Track.card_id == card.id)) is not None:
        return  # not the photo that opened this liner, or the liner is already in use
    before = services.previous_card(db, card)
    if before is None:
        return
    old = [trk.Rect(t.x1, t.y1, t.x2, t.y2) for t in db.scalars(select(Track).where(
        Track.card_id == before.id, Track.status == "confirmed", Track.review_status != "rejected", Track.misses == 0))]
    if same_liner_as_before(old, boxes):
        n = len(trk.match(old, boxes))
        log.info("capture %s: %d of %d insects from liner %s still in place, not a new liner", cap.id, n, len(old), before.id)
        services.undo_new_card(db, card, f"{n} of {len(old)} insects from the last photo are still in place "
                                         "(battery swap or accidental button press?)")


CARD_FULL_DETECTIONS = 60  # beyond this, accuracy drops and the liner should be swapped


def _event_once(db: Session, cap: Capture, kind: str, payload: dict) -> None:
    """One event of a kind per liner: the first photo that shows it."""
    already = db.scalar(
        select(Event).where(Event.trap_id == cap.trap_id, Event.kind == kind, Event.payload["card_id"].as_integer() == cap.card_id)
    )
    if already is None:
        db.add(Event(trap_id=cap.trap_id, kind=kind, payload={"card_id": cap.card_id, **payload}))


def _card_full_check(db: Session, cap: Capture, n: int) -> None:
    if n >= CARD_FULL_DETECTIONS:
        _event_once(db, cap, "card_full", {"detections": n})


def process_pending(pipeline: Pipeline, limit: int = 10) -> int:
    done = 0
    with session_scope() as db:
        ids = list(db.scalars(select(Capture.id).where(Capture.status == "new").order_by(Capture.captured_at).limit(limit)))
    for cid in ids:
        with session_scope() as db:
            cap = db.get(Capture, cid)
            try:
                pipeline.process(db, cap)
            except Exception as e:  # keep the worker alive; the capture shows the error on the dashboard
                log.exception("capture %s failed", cid)
                db.rollback()
                cap = db.get(Capture, cid)
                cap.status, cap.error = "failed", f"{e.__class__.__name__}: {e}"
        done += 1
    return done


def run_forever(stop_flag=None) -> None:
    pipeline = Pipeline()
    log.info("worker started (%s)", pipeline.version)
    poll = get_settings().worker_poll_s
    while not (stop_flag and stop_flag.is_set()):
        if process_pending(pipeline) == 0:
            time.sleep(poll)
