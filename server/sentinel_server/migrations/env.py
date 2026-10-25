"""Alembic's entry point. init_db() hands it an open connection; the alembic command line (server/alembic.ini,
for writing a new revision) gets one from the server's settings, so SENTINEL_DATA_DIR or
SENTINEL_DATABASE_URL say which database it works on."""

from alembic import context

from sentinel_server import models  # noqa: F401  (register tables)
from sentinel_server.db import Base, migration_connection

config = context.config


def run(connection) -> None:
    # render_as_batch: SQLite can't alter or drop most things in place, so autogenerate writes those as
    # batch operations (copy the table, swap it in), which also work on Postgres. The connection is already in
    # a transaction that covers the DDL too (db.migration_connection), on SQLite as well.
    context.configure(connection=connection, target_metadata=Base.metadata, render_as_batch=True,
                      transactional_ddl=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("offline (--sql) migrations aren't set up: run them against a database")
if (conn := config.attributes.get("connection")) is not None:
    run(conn)
else:
    with migration_connection() as conn:
        run(conn)
