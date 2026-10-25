"""Alembic migrations (sentinel_server/migrations): new databases, ones from before Alembic, and rollbacks."""

import logging
import sqlite3

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from sentinel_server import db as db_mod, models  # noqa: F401
from sentinel_server.backup import database_path
from sentinel_server.db import Base

HEAD = ScriptDirectory(str(db_mod.MIGRATIONS)).get_current_head()


def fresh_file():
    """Throw away the database the conftest made, leaving an empty file path."""
    db_mod.reset_engine()
    path = database_path()
    for p in (path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")):
        p.unlink(missing_ok=True)
    return path


def pre_alembic(path):
    """A database as the old init_db (create_all) left it: every table, no alembic_version."""
    eng = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(eng)
    eng.dispose()


def schema(path):
    with sqlite3.connect(path) as c:
        return sorted(c.execute("SELECT type, name, sql FROM sqlite_master WHERE tbl_name != 'alembic_version'"))


def version(path):
    with sqlite3.connect(path) as c:
        return [r[0] for r in c.execute("SELECT version_num FROM alembic_version")]


def test_new_database_matches_the_models():
    path = database_path()  # the conftest's init_db made it from nothing
    assert version(path) == [HEAD]
    with db_mod.engine().connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_up_to_date_database_from_before_alembic_is_only_stamped():
    path = fresh_file()
    pre_alembic(path)
    before = schema(path)
    db_mod.init_db()
    assert schema(path) == before
    assert version(path) == [HEAD]


def test_older_database_gets_what_it_is_missing():
    path = fresh_file()
    pre_alembic(path)
    with sqlite3.connect(path) as c:
        c.execute("INSERT INTO traps (id, name, block, lure, api_key_hash, device_config, mask, created_at, kind) "
                  "VALUES ('T1', '', '', 'CM', 'x', '{}', '[]', '2026-05-01 00:00:00', 'esp32')")
        c.execute("ALTER TABLE traps DROP COLUMN kind")  # had a server default: old rows get 'pi'
        c.execute("ALTER TABLE traps DROP COLUMN firmware_target")  # nullable
        c.execute("ALTER TABLE tracks DROP COLUMN n_insects")
        c.execute("DROP INDEX ix_captures_status")
        c.execute("DROP TABLE hub_claims")
    db_mod.init_db()
    assert version(path) == [HEAD]
    with db_mod.engine().connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn), Base.metadata) == []
        assert conn.execute(text("SELECT kind, firmware_target FROM traps")).one() == ("pi", None)


def test_database_too_old_to_take_in_is_left_alone():
    path = fresh_file()
    pre_alembic(path)
    with sqlite3.connect(path) as c:
        c.execute("ALTER TABLE traps DROP COLUMN api_key_hash")  # NOT NULL, no default: can't be added back
    before = schema(path)
    with pytest.raises(RuntimeError, match="traps.api_key_hash"):
        db_mod.init_db()
    assert schema(path) == before
    with sqlite3.connect(path) as c:
        assert not c.execute("SELECT 1 FROM sqlite_master WHERE name = 'alembic_version'").fetchall()


def test_rows_already_pointing_nowhere_dont_stop_it():
    """Only a broken link the migration made stops it, not one the database already had."""
    path = fresh_file()
    pre_alembic(path)
    with sqlite3.connect(path) as c:  # foreign keys are off on a plain sqlite3 connection
        c.execute("INSERT INTO cards (trap_id, installed_at, note) VALUES ('gone', '2026-05-01', '')")
    db_mod.init_db()
    assert version(path) == [HEAD]


def test_newer_revision_is_left_for_older_code(caplog):
    """deploy.sh puts the old code back when the new one doesn't come up, and may leave the database at the
    new code's revision."""
    path = database_path()
    with sqlite3.connect(path) as c:
        c.execute("UPDATE alembic_version SET version_num = 'ffff_from_newer_code'")
    before = schema(path)
    with caplog.at_level(logging.WARNING):
        db_mod.init_db()
    assert "ffff_from_newer_code" in caplog.text
    assert schema(path) == before


def test_failed_migration_leaves_nothing_behind():
    path = database_path()
    with pytest.raises(ZeroDivisionError):
        with db_mod.migration_connection() as conn:
            conn.execute(text("CREATE TABLE half_done (id INTEGER)"))
            conn.execute(text("ALTER TABLE traps ADD COLUMN half_done INTEGER"))
            1 / 0  # noqa: B018
    assert "half_done" not in str(schema(path))
