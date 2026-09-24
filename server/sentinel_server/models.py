"""Database tables. All timestamps are naive UTC."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# Classes the trap classifier can output. PC is not caught in delta traps.
SPECIES = ["CM", "OFM", "OBLR", "other_moth", "debris"]
SPECIES_LABELS = {
    "CM": "Codling moth",
    "OFM": "Oriental fruit moth",
    "OBLR": "Obliquebanded leafroller",
    "other_moth": "Other moth",
    "debris": "Debris / not an insect",
    "unclassified": "Insect (not yet classified)",
}
PESTS = ["CM", "OFM", "OBLR"]


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Trap(Base):
    __tablename__ = "traps"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    block: Mapped[str] = mapped_column(String(120), default="")
    lure: Mapped[str] = mapped_column(String(16), default="CM")
    api_key_hash: Mapped[str] = mapped_column(String(64))
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Settings pushed to the device in every upload reply (schedule, camera, led).
    device_config: Mapped[dict] = mapped_column(JSON, default=dict)
    # Areas to ignore, as [x1, y1, x2, y2] fractions of the image (the lure spot).
    mask: Mapped[list] = mapped_column(JSON, default=lambda: [[0.45, 0.46, 0.55, 0.54]])
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    cards: Mapped[list["Card"]] = relationship(back_populates="trap", order_by="Card.installed_at")


class Card(Base):
    """One sticky liner. Counting restarts on every new card."""

    __tablename__ = "cards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trap_id: Mapped[str] = mapped_column(ForeignKey("traps.id"), index=True)
    installed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str] = mapped_column(String(200), default="")
    trap: Mapped[Trap] = relationship(back_populates="cards")


class Capture(Base):
    __tablename__ = "captures"
    __table_args__ = (UniqueConstraint("trap_id", "uid"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trap_id: Mapped[str] = mapped_column(ForeignKey("traps.id"), index=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), index=True)
    uid: Mapped[str] = mapped_column(String(80))
    captured_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    image_path: Mapped[str] = mapped_column(String(300))
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wake_reason: Mapped[str] = mapped_column(String(16), default="")
    temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    rh: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_v: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)  # new | processed | failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    detections: Mapped[list["Detection"]] = relationship(back_populates="capture", cascade="all, delete-orphan")


class Track(Base):
    """One insect on one card, followed across photos."""

    __tablename__ = "tracks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime)
    first_capture_id: Mapped[int] = mapped_column(ForeignKey("captures.id"))
    n_seen: Mapped[int] = mapped_column(Integer, default=1)
    misses: Mapped[int] = mapped_column(Integer, default=0)
    # candidate: seen once; confirmed: seen in 2+ photos (counted); dropped: vanished while a candidate
    status: Mapped[str] = mapped_column(String(16), default="candidate", index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    x1: Mapped[float] = mapped_column(Float)
    y1: Mapped[float] = mapped_column(Float)
    x2: Mapped[float] = mapped_column(Float)
    y2: Mapped[float] = mapped_column(Float)
    prob_sum: Mapped[dict] = mapped_column(JSON, default=dict)
    n_classified: Mapped[int] = mapped_column(Integer, default=0)
    species: Mapped[str] = mapped_column(String(16), default="unclassified")
    species_conf: Mapped[float] = mapped_column(Float, default=0.0)
    # auto: confident model label; review: needs a person; unknown: model can't tell;
    # confirmed / relabelled by a person; rejected: not an insect
    review_status: Mapped[str] = mapped_column(String(16), default="review", index=True)
    reviewed_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # insects this track stands for: >1 when touching insects couldn't be separated (from the
    # latest photo, so if they're told apart later, the new track takes over the extra one)
    n_insects: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    @property
    def label(self) -> str:
        return self.reviewed_label or self.species


class Detection(Base):
    __tablename__ = "detections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    capture_id: Mapped[int] = mapped_column(ForeignKey("captures.id"), index=True)
    track_id: Mapped[int | None] = mapped_column(ForeignKey("tracks.id"), index=True, nullable=True)
    x1: Mapped[float] = mapped_column(Float)
    y1: Mapped[float] = mapped_column(Float)
    x2: Mapped[float] = mapped_column(Float)
    y2: Mapped[float] = mapped_column(Float)
    det_conf: Mapped[float] = mapped_column(Float)
    n_insects: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    probs: Mapped[dict] = mapped_column(JSON, default=dict)
    model_version: Mapped[str] = mapped_column(String(80), default="")
    capture: Mapped[Capture] = relationship(back_populates="detections")


class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True)
    label: Mapped[str] = mapped_column(String(16))
    reviewer: Mapped[str] = mapped_column(String(60), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WeatherDay(Base):
    """Daily max/min air temperature, from the trap's own sensor or an imported NEWA station file."""

    __tablename__ = "weather_days"
    __table_args__ = (UniqueConstraint("source", "day"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(60))  # e.g. "trap:T1" or "newa:Ithaca"
    day: Mapped[date] = mapped_column(Date, index=True)
    tmax_f: Mapped[float] = mapped_column(Float)
    tmin_f: Mapped[float] = mapped_column(Float)


class Event(Base):
    """Things a person might want to be told about (biofix, offline, card full). Alerts read from here."""

    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trap_id: Mapped[str | None] = mapped_column(ForeignKey("traps.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
