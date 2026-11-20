"""Cameras pair with the secret on their sticker, and camera firmware is signed.

pending_cameras gets the camera's proof of its secret, and the sealed key and its hash in place of the plain
key (which is cleared, and no longer written). Waiting cameras from before can't finish pairing this way, so
their rows go: those cameras show again once they run firmware that pairs with a secret. firmware gets the
signature release.sh made. Like the baseline, it adds only what is missing.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

COLUMNS = {
    "pending_cameras": [
        sa.Column("proof", sa.String(length=32), nullable=False, server_default=""),
        sa.Column("key_hash", sa.String(length=64), nullable=True),
        sa.Column("sealed", sa.Text(), nullable=True),
    ],
    "firmware": [sa.Column("sig", sa.String(length=160), nullable=False, server_default="")],
}


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for table, cols in COLUMNS.items():
        have = {c["name"] for c in insp.get_columns(table)}
        for col in cols:
            if col.name not in have:
                op.add_column(table, col)
    op.execute("DELETE FROM pending_cameras WHERE proof = ''")
    op.execute("UPDATE pending_cameras SET api_key = NULL")


def downgrade() -> None:
    for table, cols in COLUMNS.items():
        for col in cols:
            op.drop_column(table, col.name)
