"""Process new captures: detect → track → classify → update counts and events."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import session_scope
from ..models import Capture, Detection, Event, Track, Trap, utcnow
from ..settings import get_settings
from . import track as trk
from .classify import crop, make_classifier
from .detect import in_mask, make_detector

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, detector_name: str | None = None, classifier_name: str | None = None):
        s = get_settings()
        self.detector = make_detector(detector_name or s.detector)
        self.classifier = make_classifier(classifier_name or s.classifier)

    @property
    def version(self) -> str:
        return f"{self.detector.version}+{self.classifier.version}"

    def process(self, db: Session, cap: Capture) -> None:
        trap = db.get(Trap, cap.trap_id)
        path = get_settings().media_dir / cap.image_path
        boxes = self.detector.detect(path)
        with Image.open(path) as img:
            w, h = img.size
            boxes = [b for b in boxes if not in_mask(b, trap.mask, w, h)]
            probs = self.classifier.classify([crop(img, b) for b in boxes])
        cap.width, cap.height = w, h

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
                if t.reviewed_label is None:  # a reviewer's count stands
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
            if p:
                summed = dict(t.prob_sum or {})
                for k, v in p.items():
                    summed[k] = summed.get(k, 0.0) + v
                t.prob_sum = summed
                t.n_classified += 1
            if t.reviewed_label is None:
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
        for t in db.scalars(select(Track).where(Track.card_id == card_id, Track.reviewed_label.is_(None))):
            db.delete(t)
        db.flush()
        for c in caps:
            self.process(db, c)
            db.flush()
        return len(caps)


CARD_FULL_DETECTIONS = 60  # beyond this, accuracy drops and the liner should be swapped


def _card_full_check(db: Session, cap: Capture, n: int) -> None:
    if n < CARD_FULL_DETECTIONS:
        return
    already = db.scalar(
        select(Event).where(Event.trap_id == cap.trap_id, Event.kind == "card_full", Event.payload["card_id"].as_integer() == cap.card_id)
    )
    if already is None:
        db.add(Event(trap_id=cap.trap_id, kind="card_full", payload={"card_id": cap.card_id, "detections": n}))


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
