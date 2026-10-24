"""Backups: one dead SD card shouldn't lose the season.

A dated snapshot of the database, made with SQLite's backup API (consistent while the server keeps
writing, WAL included), and the photos copied next to it. Photos never change once saved, so only new
ones are copied. With `push`, the backup folder is then rsynced to another machine (the team Mac over
Tailscale), since a copy on the same SD card dies with it.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from .settings import get_settings

log = logging.getLogger(__name__)


def database_path() -> Path:
    url = make_url(get_settings().database_url)
    if not url.drivername.startswith("sqlite") or not url.database:
        raise ValueError(f"only a SQLite database file can be backed up this way, not {url.drivername}")
    return Path(url.database).resolve()


def snapshot(dest: Path, keep: int = 14) -> Path:
    """Write dest/sentinel-<time>.db and drop all but the newest `keep` snapshots."""
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / f"sentinel-{datetime.now():%Y%m%d-%H%M%S}.db"
    tmp = out.with_suffix(".part")
    src = sqlite3.connect(database_path())
    try:
        dst = sqlite3.connect(tmp)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    tmp.replace(out)  # a snapshot is either whole or absent
    for old in sorted(dest.glob("sentinel-*.db"))[:-keep]:
        old.unlink()
    return out


def copy_media(dest: Path) -> int:
    """Copy photos the backup doesn't have yet (or has at a different size). Returns how many."""
    src = get_settings().media_dir
    n = 0
    for f in src.rglob("*"):
        if not f.is_file():
            continue
        to = dest / "media" / f.relative_to(src)
        if to.exists() and to.stat().st_size == f.stat().st_size:
            continue
        to.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, to)
        n += 1
    return n


def push(dest: Path, target: str) -> None:
    """rsync the backup folder to `target` (a path, or user@host:path). Nothing is deleted there, so an
    accident on the server can't empty the far copy."""
    subprocess.run(["rsync", "-a", f"{dest}/", f"{target.rstrip('/')}/"], check=True)


def run(dest: Path, keep: int = 14, target: str | None = None) -> dict:
    dest = dest.resolve()
    if dest.is_relative_to(get_settings().data_dir):
        raise ValueError(f"{dest} is inside the data folder: back up somewhere else")
    db = snapshot(dest, keep)
    photos = copy_media(dest)
    if target:
        push(dest, target)
    log.info("backup: %s, %d new photos%s", db.name, photos, f", pushed to {target}" if target else "")
    return {"database": db, "photos": photos}
