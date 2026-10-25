"""`sentinel-server backup`: a consistent copy of the database and the photos, kept somewhere else."""

import shutil
import sqlite3

import pytest

from sentinel_server import services
from sentinel_server.db import session_scope
from sentinel_server.models import Trap
from sentinel_server.settings import get_settings


def _photo(rel: str, data: bytes) -> None:
    p = get_settings().media_dir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def test_backup_copies_the_database_and_new_photos(tmp_path):
    from sentinel_server.cli import main

    with session_scope() as db:
        db.add(Trap(id="T1", api_key_hash=services.hash_key("k")))
    _photo("T1/2026-06-01/a.jpg", b"one")
    dest = tmp_path / "backup"
    assert main(["backup", str(dest)]) == 0

    snaps = sorted(dest.glob("sentinel-*.db"))
    assert len(snaps) == 1
    with sqlite3.connect(snaps[0]) as con:  # a whole database, not a half-written file
        assert con.execute("select id from traps").fetchall() == [("T1",)]
    assert (dest / "media/T1/2026-06-01/a.jpg").read_bytes() == b"one"

    _photo("T1/2026-06-02/b.jpg", b"two")
    (dest / "media/T1/2026-06-01/a.jpg").write_bytes(b"one")  # unchanged photos are left alone
    assert main(["backup", str(dest), "--keep", "1"]) == 0
    assert (dest / "media/T1/2026-06-02/b.jpg").read_bytes() == b"two"
    assert len(list(dest.glob("sentinel-*.db"))) == 1  # older snapshots pruned


def test_backup_rejects_a_destination_inside_the_data_folder():
    from sentinel_server.cli import main

    assert main(["backup", str(get_settings().data_dir / "backup")]) == 1


@pytest.mark.skipif(shutil.which("rsync") is None, reason="needs rsync")
def test_backup_pushes_off_the_machine(tmp_path):
    from sentinel_server.cli import main

    _photo("T1/2026-06-01/a.jpg", b"one")
    far = tmp_path / "team-mac"
    assert main(["backup", str(tmp_path / "backup"), "--push", str(far)]) == 0
    assert (far / "media/T1/2026-06-01/a.jpg").read_bytes() == b"one"
    assert list(far.glob("sentinel-*.db"))
