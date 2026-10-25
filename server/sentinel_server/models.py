"""Database tables. All timestamps are naive UTC."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# Classes the trap classifier can output. PC is not caught in delta traps.
SPECIES = ["CM", "OFM", "OBLR", "other_moth", "other_insect", "debris"]
SPECIES_LABELS = {
    "CM": "Codling moth",
    "OFM": "Oriental fruit moth",
    "OBLR": "Obliquebanded leafroller",
    "other_moth": "Other moth",
    "other_insect": "Other insect (not a moth)",
    "debris": "Debris / not an insect",
    "unclassified": "Insect (not yet classified)",
}
PESTS = ["CM", "OFM", "OBLR"]
NOT_CATCHES = {"other_insect", "debris"}  # kept on the liner record, left out of moth counts


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
    # The camera's measured scale at the card centre (px/mm on the straightened photo), e.g. 10.3 for the
    # 130° OV5640 110 mm over the card at 2048 × 1536. Photos whose grid reads far from it are left out.
    # None: each liner's photos are checked against each other instead.
    px_per_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # "esp32" is an ESP32 camera that uploads through hub_id's gateway; "hub" is a Pi with no camera that
    # only relays ESP32 photos; "pi" is a Pi camera trap that uploads by itself (and can also be a hub)
    kind: Mapped[str] = mapped_column(String(16), default="pi", server_default="pi")
    hub_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Last time the device used its key (a hub asks for its camera list every minute or so).
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # "Take a photo now" from the dashboard (ESP32 cameras): the hub passes it on at the camera's next
    # check-in, and it is cleared when a photo taken after it arrives.
    photo_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Taken out of the orchard from the dashboard: hidden, and its key stops working. Photos are kept.
    retired_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Biofix confirmed or set by a person on the trap page, in place of the one from the catches. It counts
    # for its own season only.
    biofix_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # ESP32 cameras: the firmware version its photos last reported, and the one picked on the dashboard for it
    # to install. Its hub offers the target at each contact until the camera reports running it.
    firmware_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    firmware_target: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cards: Mapped[list["Card"]] = relationship(back_populates="trap", order_by="Card.installed_at")


class Card(Base):
    """One sticky liner. Counting restarts on every new card."""

    __tablename__ = "cards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trap_id: Mapped[str] = mapped_column(ForeignKey("traps.id"), index=True)
    installed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    note: Mapped[str] = mapped_column(String(200), default="")
    # The lure in the trap while this liner was in: its catches are read against it, so changing a trap's
    # lure doesn't reinterpret earlier liners. None only on a liner made outside start_new_card.
    lure: Mapped[str | None] = mapped_column(String(16), nullable=True)
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

    @property
    def reviewed(self) -> bool:
        """A person labelled or rejected it: the model no longer changes its label or count."""
        return self.reviewed_label is not None or self.review_status == "rejected"


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


class Firmware(Base):
    """An ESP32 camera firmware build (a release build: no trap id or key in it), uploaded on the dashboard.
    The file is data_dir/firmware/<version>.bin. The version is read from the file itself."""

    __tablename__ = "firmware"
    version: Mapped[str] = mapped_column(String(32), primary_key=True)
    size: Mapped[int] = mapped_column(Integer)
    md5: Mapped[str] = mapped_column(String(32))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    note: Mapped[str] = mapped_column(String(200), default="")


class PendingCamera(Base):
    """An ESP32 with no trap id or key yet that asked a hub to be added (pairing). It shows on Set up traps;
    when it is added there, its new key waits here until the hub has handed it to the camera."""

    __tablename__ = "pending_cameras"
    code: Mapped[str] = mapped_column(String(12), primary_key=True)  # last 6 hex digits of its MAC, on its sticker
    hub_id: Mapped[str] = mapped_column(String(32))
    fw: Mapped[str] = mapped_column(String(32), default="")
    rssi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    trap_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    api_key: Mapped[str | None] = mapped_column(String(64), nullable=True)


class HubClaim(Base):
    """A hub added on the dashboard with the pairing code from its sticker. The hub asks with that code
    and gets its trap id and key; the row goes once the hub has used the key."""

    __tablename__ = "hub_claims"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    trap_id: Mapped[str] = mapped_column(String(32))
    api_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
