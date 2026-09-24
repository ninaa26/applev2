"""Queries shared by the API and the dashboard."""

from __future__ import annotations

import hashlib
import secrets
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import phenology
from .models import Capture, Card, Event, Track, Trap, WeatherDay, utcnow
from .settings import get_settings


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_api_key() -> str:
    return secrets.token_urlsafe(24)


def local_date(dt_utc: datetime) -> date:
    return dt_utc.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(get_settings().timezone)).date()


def open_card(db: Session, trap_id: str) -> Card | None:
    return db.scalar(
        select(Card).where(Card.trap_id == trap_id, Card.removed_at.is_(None)).order_by(Card.installed_at.desc())
    )


def start_new_card(db: Session, trap_id: str, at: datetime | None = None, note: str = "") -> Card:
    at = at or utcnow()
    current = open_card(db, trap_id)
    if current is not None:
        current.removed_at = at
    card = Card(trap_id=trap_id, installed_at=at, note=note)
    db.add(card)
    db.add(Event(trap_id=trap_id, kind="new_card", payload={"note": note}, at=at))
    db.flush()
    return card


def counted_tracks(db: Session, trap_id: str, since: datetime | None = None) -> list[Track]:
    """Confirmed insects that count as catches (not rejected, not debris)."""
    q = (
        select(Track)
        .join(Card, Track.card_id == Card.id)
        .where(Card.trap_id == trap_id, Track.status == "confirmed", Track.review_status != "rejected")
    )
    if since is not None:
        q = q.where(Track.first_seen_at >= since)
    return [t for t in db.scalars(q) if t.label != "debris"]


def daily_counts(db: Session, trap_id: str, days: int = 30) -> list[dict]:
    """Per local day: new catches by label, for the last `days` days (oldest first)."""
    today = local_date(utcnow())
    start = today - timedelta(days=days - 1)
    since = datetime.combine(start - timedelta(days=1), datetime.min.time())
    buckets: dict[date, Counter] = defaultdict(Counter)
    for t in counted_tracks(db, trap_id, since):
        d = local_date(t.first_seen_at)
        if d >= start:
            buckets[d][t.label] += 1
    return [{"date": start + timedelta(days=i), "counts": dict(buckets[start + timedelta(days=i)])} for i in range(days)]


def week_counts(db: Session, trap_id: str) -> Counter:
    since = utcnow() - timedelta(days=7)
    return Counter(t.label for t in counted_tracks(db, trap_id, since))


def pending_reviews(db: Session, trap_id: str | None = None) -> list[Track]:
    q = select(Track).join(Card, Track.card_id == Card.id).where(
        Track.status == "confirmed", Track.reviewed_label.is_(None), Track.review_status.in_(["review", "unknown"])
    )
    if trap_id:
        q = q.where(Card.trap_id == trap_id)
    return list(db.scalars(q.order_by(Track.first_seen_at)))


def last_capture(db: Session, trap_id: str) -> Capture | None:
    return db.scalar(select(Capture).where(Capture.trap_id == trap_id).order_by(Capture.captured_at.desc()))


def trap_health(db: Session, trap: Trap) -> dict:
    last = last_capture(db, trap.id)
    if last is None:
        return {"state": "never", "label": "No photos yet", "last": None}
    age_h = (utcnow() - last.received_at).total_seconds() / 3600
    state = "online" if age_h <= get_settings().offline_after_h else "offline"
    err = (last.meta or {}).get("device", {}).get("last_error")
    return {
        "state": "error" if (state == "online" and (err or last.status == "failed")) else state,
        "age_h": age_h,
        "last": last,
        "device_error": err,
    }


def weather_days(db: Session, trap_id: str) -> tuple[dict[date, tuple[float, float]], str]:
    """Prefer an imported NEWA station file; fall back to the trap's own temperature readings."""
    rows = list(db.scalars(select(WeatherDay).where(WeatherDay.source.like("newa:%"))))
    if rows:
        return {r.day: (r.tmax_f, r.tmin_f) for r in rows}, rows[0].source
    readings = [
        (local_date(c.captured_at), c.temp_c)
        for c in db.scalars(select(Capture).where(Capture.trap_id == trap_id, Capture.temp_c.is_not(None)))
    ]
    return phenology.daily_extremes_f(readings), f"trap:{trap_id}"


def phenology_status(db: Session, trap: Trap) -> dict | None:
    model = phenology.MODELS.get(trap.lure)
    if model is None:
        return None
    catch_dates = sorted(local_date(t.first_seen_at) for t in counted_tracks(db, trap.id) if t.label == trap.lure)
    biofix = phenology.sustained_biofix(catch_dates)
    days, source = weather_days(db, trap.id)
    today = local_date(utcnow())
    out = {"model": model, "biofix": biofix, "catches": len(catch_dates), "weather_source": source}
    if biofix:
        dd, missing = phenology.cumulative_dd(days, biofix, today, model.base_f)
        out.update(dd=dd, missing_days=missing, next=phenology.next_milestone(model, dd))
    if trap.lure == "OFM":
        jan1 = date(today.year, 1, 1)
        out["dd_jan1"], out["missing_jan1"] = phenology.cumulative_dd(days, jan1, today, model.base_f)
    return out

