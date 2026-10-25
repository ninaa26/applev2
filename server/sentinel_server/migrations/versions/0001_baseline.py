"""Baseline: the schema as it was when the server moved to Alembic (Oct 25 2026).

It creates only what is missing, so it also takes in a database from before Alembic: one already at this
schema (the Pi 5's) is left as it is and only stamped, and an older one gets the tables, columns and
indexes it lacks, with the rules the old column-adding code used (a column needs a server default or must
be nullable). The tables are written out here rather than taken from models.py, so later changes to the
models don't change what this revision does.

Revision ID: 0001
Revises:
Create Date: 2026-10-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

meta = sa.MetaData()

sa.Table(
    "firmware", meta,
    sa.Column("version", sa.String(length=32), nullable=False),
    sa.Column("size", sa.Integer(), nullable=False),
    sa.Column("md5", sa.String(length=32), nullable=False),
    sa.Column("uploaded_at", sa.DateTime(), nullable=False),
    sa.Column("note", sa.String(length=200), nullable=False),
    sa.PrimaryKeyConstraint("version")
)

sa.Table(
    "hub_claims", meta,
    sa.Column("code", sa.String(length=16), nullable=False),
    sa.Column("trap_id", sa.String(length=32), nullable=False),
    sa.Column("api_key", sa.String(length=64), nullable=False),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint("code")
)

sa.Table(
    "pending_cameras", meta,
    sa.Column("code", sa.String(length=12), nullable=False),
    sa.Column("hub_id", sa.String(length=32), nullable=False),
    sa.Column("fw", sa.String(length=32), nullable=False),
    sa.Column("rssi", sa.Integer(), nullable=True),
    sa.Column("first_seen_at", sa.DateTime(), nullable=False),
    sa.Column("last_seen_at", sa.DateTime(), nullable=False),
    sa.Column("trap_id", sa.String(length=32), nullable=True),
    sa.Column("api_key", sa.String(length=64), nullable=True),
    sa.PrimaryKeyConstraint("code")
)

sa.Table(
    "traps", meta,
    sa.Column("id", sa.String(length=32), nullable=False),
    sa.Column("name", sa.String(length=120), nullable=False),
    sa.Column("block", sa.String(length=120), nullable=False),
    sa.Column("lure", sa.String(length=16), nullable=False),
    sa.Column("api_key_hash", sa.String(length=64), nullable=False),
    sa.Column("lat", sa.Float(), nullable=True),
    sa.Column("lon", sa.Float(), nullable=True),
    sa.Column("device_config", sa.JSON(), nullable=False),
    sa.Column("mask", sa.JSON(), nullable=False),
    sa.Column("px_per_mm", sa.Float(), nullable=True),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.Column("kind", sa.String(length=16), server_default="pi", nullable=False),
    sa.Column("hub_id", sa.String(length=32), nullable=True),
    sa.Column("last_seen_at", sa.DateTime(), nullable=True),
    sa.Column("photo_requested_at", sa.DateTime(), nullable=True),
    sa.Column("retired_at", sa.DateTime(), nullable=True),
    sa.Column("biofix_date", sa.Date(), nullable=True),
    sa.Column("firmware_version", sa.String(length=32), nullable=True),
    sa.Column("firmware_target", sa.String(length=32), nullable=True),
    sa.PrimaryKeyConstraint("id")
)

sa.Table(
    "weather_days", meta,
    sa.Column("id", sa.Integer(), nullable=False),
    sa.Column("source", sa.String(length=60), nullable=False),
    sa.Column("day", sa.Date(), nullable=False),
    sa.Column("tmax_f", sa.Float(), nullable=False),
    sa.Column("tmin_f", sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("source", "day")
)

sa.Index("ix_weather_days_day", meta.tables["weather_days"].c.day)
sa.Table(
    "cards", meta,
    sa.Column("id", sa.Integer(), nullable=False),
    sa.Column("trap_id", sa.String(length=32), nullable=False),
    sa.Column("installed_at", sa.DateTime(), nullable=False),
    sa.Column("removed_at", sa.DateTime(), nullable=True),
    sa.Column("note", sa.String(length=200), nullable=False),
    sa.Column("lure", sa.String(length=16), nullable=True),
    sa.ForeignKeyConstraint(["trap_id"], ["traps.id"]),
    sa.PrimaryKeyConstraint("id")
)

sa.Index("ix_cards_trap_id", meta.tables["cards"].c.trap_id)
sa.Table(
    "events", meta,
    sa.Column("id", sa.Integer(), nullable=False),
    sa.Column("trap_id", sa.String(length=32), nullable=True),
    sa.Column("kind", sa.String(length=40), nullable=False),
    sa.Column("payload", sa.JSON(), nullable=False),
    sa.Column("at", sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(["trap_id"], ["traps.id"]),
    sa.PrimaryKeyConstraint("id")
)

sa.Index("ix_events_trap_id", meta.tables["events"].c.trap_id)
sa.Table(
    "captures", meta,
    sa.Column("id", sa.Integer(), nullable=False),
    sa.Column("trap_id", sa.String(length=32), nullable=False),
    sa.Column("card_id", sa.Integer(), nullable=False),
    sa.Column("uid", sa.String(length=80), nullable=False),
    sa.Column("captured_at", sa.DateTime(), nullable=False),
    sa.Column("received_at", sa.DateTime(), nullable=False),
    sa.Column("image_path", sa.String(length=300), nullable=False),
    sa.Column("width", sa.Integer(), nullable=True),
    sa.Column("height", sa.Integer(), nullable=True),
    sa.Column("wake_reason", sa.String(length=16), nullable=False),
    sa.Column("temp_c", sa.Float(), nullable=True),
    sa.Column("rh", sa.Float(), nullable=True),
    sa.Column("battery_v", sa.Float(), nullable=True),
    sa.Column("meta", sa.JSON(), nullable=False),
    sa.Column("status", sa.String(length=16), nullable=False),
    sa.Column("error", sa.Text(), nullable=True),
    sa.Column("processed_at", sa.DateTime(), nullable=True),
    sa.Column("model_version", sa.String(length=80), nullable=True),
    sa.ForeignKeyConstraint(["card_id"], ["cards.id"]),
    sa.ForeignKeyConstraint(["trap_id"], ["traps.id"]),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("trap_id", "uid")
)

sa.Index("ix_captures_captured_at", meta.tables["captures"].c.captured_at)
sa.Index("ix_captures_card_id", meta.tables["captures"].c.card_id)
sa.Index("ix_captures_status", meta.tables["captures"].c.status)
sa.Index("ix_captures_trap_id", meta.tables["captures"].c.trap_id)
sa.Table(
    "tracks", meta,
    sa.Column("id", sa.Integer(), nullable=False),
    sa.Column("card_id", sa.Integer(), nullable=False),
    sa.Column("first_seen_at", sa.DateTime(), nullable=False),
    sa.Column("last_seen_at", sa.DateTime(), nullable=False),
    sa.Column("first_capture_id", sa.Integer(), nullable=False),
    sa.Column("n_seen", sa.Integer(), nullable=False),
    sa.Column("misses", sa.Integer(), nullable=False),
    sa.Column("status", sa.String(length=16), nullable=False),
    sa.Column("confirmed_at", sa.DateTime(), nullable=True),
    sa.Column("x1", sa.Float(), nullable=False),
    sa.Column("y1", sa.Float(), nullable=False),
    sa.Column("x2", sa.Float(), nullable=False),
    sa.Column("y2", sa.Float(), nullable=False),
    sa.Column("prob_sum", sa.JSON(), nullable=False),
    sa.Column("n_classified", sa.Integer(), nullable=False),
    sa.Column("species", sa.String(length=16), nullable=False),
    sa.Column("species_conf", sa.Float(), nullable=False),
    sa.Column("review_status", sa.String(length=16), nullable=False),
    sa.Column("reviewed_label", sa.String(length=16), nullable=True),
    sa.Column("n_insects", sa.Integer(), server_default="1", nullable=False),
    sa.ForeignKeyConstraint(["card_id"], ["cards.id"]),
    sa.ForeignKeyConstraint(["first_capture_id"], ["captures.id"]),
    sa.PrimaryKeyConstraint("id")
)

sa.Index("ix_tracks_card_id", meta.tables["tracks"].c.card_id)
sa.Index("ix_tracks_review_status", meta.tables["tracks"].c.review_status)
sa.Index("ix_tracks_status", meta.tables["tracks"].c.status)
sa.Table(
    "detections", meta,
    sa.Column("id", sa.Integer(), nullable=False),
    sa.Column("capture_id", sa.Integer(), nullable=False),
    sa.Column("track_id", sa.Integer(), nullable=True),
    sa.Column("x1", sa.Float(), nullable=False),
    sa.Column("y1", sa.Float(), nullable=False),
    sa.Column("x2", sa.Float(), nullable=False),
    sa.Column("y2", sa.Float(), nullable=False),
    sa.Column("det_conf", sa.Float(), nullable=False),
    sa.Column("n_insects", sa.Integer(), server_default="1", nullable=False),
    sa.Column("probs", sa.JSON(), nullable=False),
    sa.Column("model_version", sa.String(length=80), nullable=False),
    sa.ForeignKeyConstraint(["capture_id"], ["captures.id"]),
    sa.ForeignKeyConstraint(["track_id"], ["tracks.id"]),
    sa.PrimaryKeyConstraint("id")
)

sa.Index("ix_detections_capture_id", meta.tables["detections"].c.capture_id)
sa.Index("ix_detections_track_id", meta.tables["detections"].c.track_id)
sa.Table(
    "reviews", meta,
    sa.Column("id", sa.Integer(), nullable=False),
    sa.Column("track_id", sa.Integer(), nullable=False),
    sa.Column("label", sa.String(length=16), nullable=False),
    sa.Column("reviewer", sa.String(length=60), nullable=False),
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(["track_id"], ["tracks.id"]),
    sa.PrimaryKeyConstraint("id")
)

sa.Index("ix_reviews_track_id", meta.tables["reviews"].c.track_id)


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for table in meta.sorted_tables:
        if not insp.has_table(table.name):
            table.create(bind)
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in have:
                continue
            if col.server_default is None and not col.nullable:
                raise RuntimeError(f"{table.name}.{col.name} is missing and has no default for the rows already "
                                   "there: this database is too old to take in")
            default = col.server_default.arg if col.server_default is not None else None
            op.add_column(table.name, sa.Column(col.name, col.type, nullable=col.nullable, server_default=default))
        indexes = {i["name"] for i in insp.get_indexes(table.name)}
        for index in table.indexes:
            if index.name not in indexes:
                index.create(bind)


def downgrade() -> None:
    for table in reversed(meta.sorted_tables):
        table.drop(op.get_bind())
