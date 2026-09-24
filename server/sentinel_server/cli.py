"""sentinel-server: run the server and manage traps.

    sentinel-server init
    sentinel-server add-trap T1 --lure CM --name "Bench mockup"
    sentinel-server serve                  # API + dashboard + worker in one process (Mac dev setup)
    sentinel-server serve --no-worker      # API only; run `sentinel-server worker` separately
    sentinel-server worker
    sentinel-server reprocess --card 3     # re-run a liner's photos with the current models
    sentinel-server import-weather newa.csv --source newa:Ithaca
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import select

from .db import init_db, session_scope
from .models import Trap, WeatherDay
from .services import hash_key, new_api_key
from .settings import get_settings


def cmd_init(args) -> int:
    init_db()
    s = get_settings()
    print(f"database: {s.database_url}\nmedia:    {s.media_dir}")
    return 0


def cmd_add_trap(args) -> int:
    init_db()
    key = new_api_key()
    with session_scope() as db:
        if db.get(Trap, args.trap_id):
            print(f"trap {args.trap_id} already exists; use rotate-key for a new key", file=sys.stderr)
            return 1
        db.add(Trap(id=args.trap_id, name=args.name, block=args.block, lure=args.lure, api_key_hash=hash_key(key)))
    print(f"Created trap {args.trap_id} ({args.lure} lure).\nAPI key (shown once, put it in the device config.toml):\n\n  {key}\n")
    return 0


def cmd_rotate_key(args) -> int:
    key = new_api_key()
    with session_scope() as db:
        trap = db.get(Trap, args.trap_id)
        if trap is None:
            print(f"no trap {args.trap_id}", file=sys.stderr)
            return 1
        trap.api_key_hash = hash_key(key)
    print(f"New API key for {args.trap_id}:\n\n  {key}\n")
    return 0


def cmd_list(args) -> int:
    init_db()
    with session_scope() as db:
        for t in db.scalars(select(Trap).order_by(Trap.id)):
            print(f"{t.id:6} {t.lure:5} {t.name}")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from .app import create_app

    init_db()
    app = create_app(start_worker=not args.no_worker)
    print(f"Dashboard: http://{'localhost' if args.host in ('0.0.0.0', '127.0.0.1') else args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def cmd_worker(args) -> int:
    from .pipeline.worker import run_forever

    init_db()
    run_forever()
    return 0


def cmd_reprocess(args) -> int:
    from .pipeline.worker import Pipeline

    init_db()
    pipeline = Pipeline()
    with session_scope() as db:
        n = pipeline.reprocess_card(db, args.card)
    print(f"reprocessed {n} photos on liner {args.card} with {pipeline.version}")
    return 0


def cmd_import_weather(args) -> int:
    """CSV with columns date, tmax_f, tmin_f (e.g. exported daily data from the nearest NEWA station)."""
    init_db()
    n = 0
    with open(args.csv, newline="") as f, session_scope() as db:
        for row in csv.DictReader(f):
            day = date.fromisoformat(row["date"].strip()[:10])
            tmax, tmin = float(row["tmax_f"]), float(row["tmin_f"])
            existing = db.scalar(select(WeatherDay).where(WeatherDay.source == args.source, WeatherDay.day == day))
            if existing:
                existing.tmax_f, existing.tmin_f = tmax, tmin
            else:
                db.add(WeatherDay(source=args.source, day=day, tmax_f=tmax, tmin_f=tmin))
            n += 1
    print(f"imported {n} days into {args.source}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sentinel-server", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create the database").set_defaults(fn=cmd_init)

    p = sub.add_parser("add-trap", help="register a trap and print its API key")
    p.add_argument("trap_id")
    p.add_argument("--lure", choices=["CM", "OFM", "OBLR"], required=True)
    p.add_argument("--name", default="")
    p.add_argument("--block", default="")
    p.set_defaults(fn=cmd_add_trap)

    p = sub.add_parser("rotate-key", help="issue a new API key for a trap")
    p.add_argument("trap_id")
    p.set_defaults(fn=cmd_rotate_key)

    sub.add_parser("list", help="list traps").set_defaults(fn=cmd_list)

    p = sub.add_parser("serve", help="run API + dashboard (+ worker)")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-worker", action="store_true")
    p.set_defaults(fn=cmd_serve)

    sub.add_parser("worker", help="process new photos forever").set_defaults(fn=cmd_worker)

    p = sub.add_parser("reprocess", help="re-run detection/tracking for one liner")
    p.add_argument("--card", type=int, required=True)
    p.set_defaults(fn=cmd_reprocess)

    p = sub.add_parser("import-weather", help="import daily max/min temperatures (°F)")
    p.add_argument("csv", type=Path)
    p.add_argument("--source", default="newa:station")
    p.set_defaults(fn=cmd_import_weather)

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
