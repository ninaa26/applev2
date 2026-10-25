from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool

from .settings import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal: sessionmaker | None = None


MIGRATIONS = Path(__file__).parent / "migrations"
log = logging.getLogger(__name__)


def _sqlite_pragmas(dbapi_conn, foreign_keys: bool = True) -> None:
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")  # API and worker write concurrently
    cur.execute(f"PRAGMA foreign_keys={'ON' if foreign_keys else 'OFF'}")
    cur.close()


def engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = get_settings().database_url
        kwargs = {"connect_args": {"check_same_thread": False, "timeout": 30}} if url.startswith("sqlite") else {}
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            event.listen(_engine, "connect", lambda dbapi_conn, _: _sqlite_pragmas(dbapi_conn))
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine, _SessionLocal = None, None


@contextmanager
def migration_connection():
    """A connection in a transaction that migrations can run in, committed at the end.

    On SQLite it is a connection of its own: Python's sqlite3 doesn't put CREATE or ALTER in a transaction, so
    a migration that failed halfway would stay half done. This one starts every transaction itself with BEGIN
    IMMEDIATE, which also makes a second process starting at the same moment wait for the first one's
    migration rather than run it again. Foreign keys are off while it runs, as SQLite asks for when a table is
    rebuilt (batch operations), and checked before the commit (only for broken links the migration made: rows
    the database already had pointing nowhere don't stop it)."""
    url = get_settings().database_url
    if not url.startswith("sqlite"):
        with engine().begin() as conn:
            yield conn
        return
    eng = create_engine(url, poolclass=NullPool, connect_args={"timeout": 30, "isolation_level": None})
    event.listen(eng, "connect", lambda dbapi_conn, _: _sqlite_pragmas(dbapi_conn, foreign_keys=False))
    event.listen(eng, "begin", lambda conn: conn.exec_driver_sql("BEGIN IMMEDIATE"))
    try:
        with eng.begin() as conn:
            had = set(conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall())
            yield conn
            if bad := set(conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall()) - had:
                raise RuntimeError(f"the migration left rows pointing at rows that aren't there: {sorted(bad)[:5]}")
    finally:
        eng.dispose()


def init_db() -> None:
    """Bring the database to the newest schema: Alembic runs the revisions in migrations/versions/ that it
    hasn't had yet. A new database gets every table; one from before Alembic gets whatever the baseline
    revision finds missing, and is stamped."""
    logging.getLogger("alembic").setLevel(logging.WARNING)  # it says a lot even when there's nothing to do
    from alembic import command
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory

    from . import models  # noqa: F401  (register tables)

    with migration_connection() as conn:
        cfg = Config()
        cfg.set_main_option("script_location", str(MIGRATIONS))
        cfg.attributes["connection"] = conn
        known = {s.revision for s in ScriptDirectory.from_config(cfg).walk_revisions()}
        current = MigrationContext.configure(conn).get_current_heads()
        if unknown := [r for r in current if r not in known]:
            # Newer code migrated this database and older code is running on it again (an older checkout, or a
            # rollback that kept the database). Migrations only add things, so the older code can still use it.
            log.warning("database is at revision %s, which this code doesn't know: left as it is", unknown)
        else:
            command.upgrade(cfg, "head")
            if (now := MigrationContext.configure(conn).get_current_heads()) != current:
                log.info("database migrated from %s to %s", list(current) or "nothing", list(now))
    _fill_card_lures()


def _fill_card_lures() -> None:
    """Liners from before the lure was kept per liner had their trap's lure."""
    from sqlalchemy import text

    with engine().begin() as conn:
        conn.execute(text("UPDATE cards SET lure = (SELECT lure FROM traps WHERE traps.id = cards.trap_id) "
                          "WHERE lure IS NULL"))


@contextmanager
def session_scope():
    engine()
    s: Session = _SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_session():
    """FastAPI dependency."""
    with session_scope() as s:
        yield s
