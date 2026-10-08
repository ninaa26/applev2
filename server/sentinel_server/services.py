"""Queries shared by the API and the dashboard."""

from __future__ import annotations

import hashlib
import re
import secrets
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from . import phenology
from .models import NOT_CATCHES, Capture, Card, Event, Track, Trap, WeatherDay, utcnow
from .pipeline.track import AUTO_THRESHOLD
from .settings import get_settings


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def new_api_key() -> str:
    return secrets.token_urlsafe(24)


TRAP_KINDS = {"pi": "Raspberry Pi", "esp32": "ESP32 camera"}


def active_traps(db: Session) -> list[Trap]:
    return list(db.scalars(select(Trap).where(Trap.retired_at.is_(None)).order_by(Trap.id)))


def next_trap_id(db: Session) -> str:
    """T1, T2, ...: one past the highest number in use, retired traps included (their ids stay taken)."""
    nums = [int(t[1:]) for t in db.scalars(select(Trap.id)) if t[:1] == "T" and t[1:].isdigit()]
    return f"T{max(nums, default=0) + 1}"


def create_trap(db: Session, trap_id: str, name: str = "", block: str = "", lure: str = "CM",
                kind: str = "pi", hub_id: str | None = None) -> str:
    """Register a trap and return its API key (only its hash is stored, so this is the one chance to see it)."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}", trap_id):
        raise ValueError("trap id: letters, digits, _ and - only (max 32)")
    if db.get(Trap, trap_id) is not None:
        raise ValueError(f"trap {trap_id} already exists")
    if lure not in phenology.MODELS:
        raise ValueError(f"unknown lure {lure!r}")
    if kind not in TRAP_KINDS:
        raise ValueError(f"unknown kind {kind!r}")
    if kind == "esp32":
        hub = db.get(Trap, hub_id or "")
        if hub is None or hub.kind != "pi" or hub.retired_at is not None:
            raise ValueError("an ESP32 camera needs a Raspberry Pi trap in the orchard as its hub")
    key = new_api_key()
    db.add(Trap(id=trap_id, name=name, block=block, lure=lure, kind=kind,
                hub_id=hub_id if kind == "esp32" else None, api_key_hash=hash_key(key)))
    db.flush()  # the trap row before the event that points at it
    db.add(Event(trap_id=trap_id, kind="trap_added", payload={"note": f"{TRAP_KINDS[kind]}{f' via {hub_id}' if kind == 'esp32' else ''}"}))
    db.flush()
    return key


def retire_trap(db: Session, trap: Trap) -> None:
    trap.retired_at = utcnow()
    db.add(Event(trap_id=trap.id, kind="trap_removed", payload={"note": trap.name}))


def restore_trap(db: Session, trap: Trap) -> None:
    trap.retired_at = None
    db.add(Event(trap_id=trap.id, kind="trap_restored", payload={"note": trap.name}))


def hub_nodes(db: Session, hub_id: str) -> dict[str, str]:
    """ESP32 traps that upload through this hub: {trap_id: api_key_hash}."""
    return {t.id: t.api_key_hash for t in db.scalars(select(Trap).where(
        Trap.hub_id == hub_id, Trap.kind == "esp32", Trap.retired_at.is_(None)))}


def orchard_summary(db: Session, traps: list[Trap]) -> dict:
    """Totals over every trap in the orchard, for the top of the overview."""
    week: Counter = Counter()
    for t in traps:
        week.update(week_counts(db, t.id))
    daily: list[dict] = []
    for t in traps:
        for i, d in enumerate(daily_counts(db, t.id)):
            if i == len(daily):
                daily.append({"date": d["date"], "counts": Counter()})
            daily[i]["counts"].update(d["counts"])
    health = [trap_health(db, t)["state"] for t in traps]
    day_ago = utcnow() - timedelta(days=1)
    photos_24h = db.scalar(select(func.count(Capture.id)).where(
        Capture.trap_id.in_([t.id for t in traps]), Capture.received_at >= day_ago)) if traps else 0
    return {
        "week": week, "daily": daily, "peak": max([sum(r["counts"].values()) for r in daily] + [1]),
        "reporting": sum(s in ("online", "error") for s in health), "n_traps": len(traps),
        "problems": sum(s in ("offline", "error") for s in health), "photos_24h": photos_24h,
        "pending": len(pending_reviews(db)),
    }


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


def previous_card(db: Session, card: Card) -> Card | None:
    return db.scalar(
        select(Card).where(Card.trap_id == card.trap_id, Card.id != card.id, Card.installed_at <= card.installed_at)
        .order_by(Card.installed_at.desc(), Card.id.desc())
    )


def undo_new_card(db: Session, card: Card, why: str) -> Card | None:
    """Fold a card that turned out not to be a new liner back into the one before it. Returns that card."""
    before = previous_card(db, card)
    if before is None:
        return None
    for row in list(db.scalars(select(Capture).where(Capture.card_id == card.id))) + \
            list(db.scalars(select(Track).where(Track.card_id == card.id))):
        row.card_id = before.id
    before.removed_at = None
    db.add(Event(trap_id=card.trap_id, kind="new_card_ignored", payload={"note": why}, at=card.installed_at))
    db.flush()
    db.delete(card)
    db.flush()
    return before


def counted_tracks(db: Session, trap_id: str, since: datetime | None = None) -> list[Track]:
    """Confirmed moths that count as catches (not rejected, not bycatch or debris)."""
    q = (
        select(Track)
        .join(Card, Track.card_id == Card.id)
        .where(Card.trap_id == trap_id, Track.status == "confirmed", Track.review_status != "rejected")
    )
    if since is not None:
        q = q.where(Track.first_seen_at >= since)
    return [t for t in db.scalars(q) if t.label not in NOT_CATCHES]


def daily_counts(db: Session, trap_id: str, days: int = 30) -> list[dict]:
    """Per local day: new catches by label, for the last `days` days (oldest first)."""
    today = local_date(utcnow())
    start = today - timedelta(days=days - 1)
    since = datetime.combine(start - timedelta(days=1), datetime.min.time())
    buckets: dict[date, Counter] = defaultdict(Counter)
    for t in counted_tracks(db, trap_id, since):
        d = local_date(t.first_seen_at)
        if d >= start:
            buckets[d][t.label] += t.n_insects
    return [{"date": start + timedelta(days=i), "counts": dict(buckets[start + timedelta(days=i)])} for i in range(days)]


def week_counts(db: Session, trap_id: str) -> Counter:
    since = utcnow() - timedelta(days=7)
    out: Counter = Counter()
    for t in counted_tracks(db, trap_id, since):
        out[t.label] += t.n_insects
    return out


AUDIT_EVERY = 10  # one in this many automatic labels is also shown to a person


def pending_reviews(db: Session, trap_id: str | None = None) -> list[Track]:
    """Insects for a person to look at: everything the model wasn't sure of, plus a spot check of what it was
    sure of. Without the spot check a confident mistake is never seen, so it is never corrected, never becomes
    training data, and nobody knows how often the automatic count is wrong."""
    q = select(Track).join(Card, Track.card_id == Card.id).where(
        Track.status == "confirmed", Track.reviewed_label.is_(None),
        or_(Track.review_status.in_(["review", "unknown"]),
            and_(Track.review_status == "auto", Track.id % AUDIT_EVERY == 0)),
    )
    if trap_id:
        q = q.where(Card.trap_id == trap_id)
    return list(db.scalars(q.order_by(Track.first_seen_at)))


def spot_checks(db: Session, trap_id: str) -> dict:
    """How the spot-checked automatic labels held up: {"checked": n, "agreed": k}. The share that agreed is
    the best estimate there is of how right the unchecked automatic counts are."""
    done = [t for t in db.scalars(select(Track).join(Card, Track.card_id == Card.id).where(
        Card.trap_id == trap_id, Track.id % AUDIT_EVERY == 0, Track.species_conf >= AUTO_THRESHOLD,
        or_(Track.reviewed_label.is_not(None), Track.review_status == "rejected")))]
    return {"checked": len(done), "agreed": sum(t.reviewed_label == t.species for t in done)}


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


def lure_catch_dates(db: Session, trap: Trap, card_ids: set[int] | None = None, sure_only: bool = False) -> list[date]:
    """Local date of each catch of the trap's lure species, one entry per insect. `sure_only` leaves out
    catches whose species is still the model's unsure guess (waiting in the review queue)."""
    return sorted(local_date(t.first_seen_at) for t in counted_tracks(db, trap.id)
                  if t.label == trap.lure and (card_ids is None or t.card_id in card_ids)
                  and (not sure_only or t.reviewed or t.review_status == "auto")
                  for _ in range(t.n_insects))


def phenology_status(db: Session, trap: Trap) -> dict | None:
    model = phenology.MODELS.get(trap.lure)
    if model is None:
        return None
    catch_dates = lure_catch_dates(db, trap)
    biofix = phenology.sustained_biofix(catch_dates)
    days, source = weather_days(db, trap.id)
    today = local_date(utcnow())
    out = {"model": model, "biofix": biofix, "catches": len(catch_dates), "weather_source": source}
    # The biofix starts the season's clock, so say when it rests on catches nobody has confirmed.
    sure = lure_catch_dates(db, trap, sure_only=True)
    out["unsure_catches"] = len(catch_dates) - len(sure)
    out["biofix_sure"] = phenology.sustained_biofix(sure)
    if biofix:
        dd, missing = phenology.cumulative_dd(days, biofix, today, model.base_f)
        out.update(dd=dd, missing_days=missing, next=phenology.next_milestone(model, dd))
    if trap.lure == "OFM":
        jan1 = date(today.year, 1, 1)
        out["dd_jan1"], out["missing_jan1"] = phenology.cumulative_dd(days, jan1, today, model.base_f)
    return out

