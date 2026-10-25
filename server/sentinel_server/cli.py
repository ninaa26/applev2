"""sentinel-server: run the server and manage traps.

    sentinel-server init
    sentinel-server add-trap T1 --kind hub --name "Fieldhouse hub"
    sentinel-server add-trap T2 --kind esp32 --hub T1 --lure CM --name "Row 4 east"
    sentinel-server set-kind T1 hub        # a Pi that was a camera trap is now a hub with no camera
    sentinel-server serve                  # API + dashboard + worker in one process (Mac dev setup)
    sentinel-server serve --no-worker      # API only; run `sentinel-server worker` separately
    sentinel-server worker
    sentinel-server backup ~/sentinel-backup --push nina@team-mac:sentinel-backup   # database + photos
    sentinel-server reprocess --card 3     # re-run a liner's photos with the current models
    sentinel-server import-weather newa.csv --source newa:Ithaca
    sentinel-server detect photo.jpg --out overlays/   # try the detector on photos, draw what it found
    sentinel-server set-mask T1 --none     # lure not in view: don't ignore any area
    sentinel-server set-scale T2 10.3      # the camera's measured px/mm: photos far from it are left out
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
from .services import TRAP_KINDS, create_trap, hash_key, new_api_key, set_kind
from .settings import get_settings


def cmd_init(args) -> int:
    init_db()
    s = get_settings()
    print(f"database: {s.database_url}\nmedia:    {s.media_dir}")
    return 0


def cmd_add_trap(args) -> int:
    if args.kind != "hub" and not args.lure:
        print("a camera needs --lure (CM, OFM or OBLR)", file=sys.stderr)
        return 1
    init_db()
    try:
        with session_scope() as db:
            key = create_trap(db, args.trap_id, args.name, args.block, args.lure or "CM", args.kind, args.hub)
    except ValueError as e:
        print(f"{e}{'; use rotate-key for a new key' if 'exists' in str(e) else ''}", file=sys.stderr)
        return 1
    where = {"esp32": f"ESP32 node_config.h API_KEY (uploads through {args.hub})",
             "hub": "hub's /etc/sentinel/config.toml"}.get(args.kind, "device config.toml")
    what = "hub (no camera)" if args.kind == "hub" else f"trap ({args.lure} lure)"
    print(f"Created {what} {args.trap_id}.\nAPI key (shown once, put it in the {where}):\n\n  {key}\n")
    setup = {"esp32": f"device/esp32-node/flash-camera.sh {args.trap_id} {key}",
             "hub": f"sudo ./install-hub.sh {args.trap_id} {key} <server url>   (on the hub, in device/)"}.get(args.kind)
    if setup:
        print(f"Or set the device up with it in one go:\n\n  {setup}\n")
    return 0


def cmd_set_kind(args) -> int:
    init_db()
    try:
        with session_scope() as db:
            trap = db.get(Trap, args.trap_id)
            if trap is None:
                raise ValueError(f"no trap {args.trap_id}")
            set_kind(db, trap, args.kind)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"{args.trap_id} is now: {TRAP_KINDS[args.kind]}")
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
            print(f"{t.id:6} {t.kind:5} {'-' if t.kind == 'hub' else t.lure:5} {t.name}"
                  f"{f' (via {t.hub_id})' if t.hub_id else ''}{' [removed]' if t.retired_at else ''}")
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    from .app import create_app

    init_db()
    app = create_app(start_worker=not args.no_worker)
    print(f"Dashboard: http://{'localhost' if args.host in ('0.0.0.0', '127.0.0.1') else args.host}:{args.port}")
    if not get_settings().dashboard_password and args.host not in ("127.0.0.1", "localhost", "::1"):
        print("No dashboard password: anyone who can reach this machine on its network (same Wi-Fi included) can open "
              "the dashboard and submit reviews. Set SENTINEL_DASHBOARD_PASSWORD in .env, or serve with --host 127.0.0.1.")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


def cmd_worker(args) -> int:
    from .pipeline.worker import run_forever

    init_db()
    run_forever()
    return 0


def cmd_backup(args) -> int:
    import subprocess

    from . import backup

    try:
        done = backup.run(args.dest, keep=args.keep, target=args.push)
    except (ValueError, subprocess.CalledProcessError, OSError) as e:
        print(f"backup failed: {e}", file=sys.stderr)
        return 1
    print(f"backed up {done['database'].name} and {done['photos']} new photos to {args.dest}"
          + (f", pushed to {args.push}" if args.push else ""))
    return 0


def cmd_reprocess(args) -> int:
    from .pipeline.worker import Pipeline

    init_db()
    pipeline = Pipeline()
    with session_scope() as db:
        n = pipeline.reprocess_card(db, args.card)
    print(f"reprocessed {n} photos on liner {args.card} with {pipeline.version}")
    return 0


def cmd_detect(args) -> int:
    """Run the detector on image files and write copies with boxes drawn, for tuning on the bench."""
    import cv2

    from .pipeline.detect import make_detector

    det = make_detector(args.detector or get_settings().detector)
    if args.lens is not None and hasattr(det, "lens"):
        det.lens = "auto" if args.lens == "auto" else float(args.lens)
    args.out.mkdir(parents=True, exist_ok=True)
    for path in args.images:
        boxes = det.detect(path)
        img = cv2.imread(str(path))
        info = getattr(det, "last", {})
        if info.get("card") is not None:
            cv2.polylines(img, [info["card"].astype("int32")], True, (0, 255, 0), 2)
        for b in boxes:
            cv2.rectangle(img, (int(b.x1), int(b.y1)), (int(b.x2), int(b.y2)), (255, 255, 0), 2)
            cv2.putText(img, f"{b.conf:.2f}", (int(b.x1), max(12, int(b.y1) - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 0), 1)
        line = f"{path.name}: {len(boxes)} insects"
        if info.get("grid") is not None:
            g = info["grid"]
            grid = f"grid {g.pitch_px / info['work_scale']:.0f}px at {', '.join(f'{a:.1f}°' for a in g.angles)}" if g.score else "no grid found"
            ppm = info["px_per_mm"] or 0.0
            line += f"  ({grid}; {ppm:.1f} px/mm; lens k {info.get('lens_k', 0):+.3f}"
            line += f"; {info['off_card']} off the card ignored)" if info.get("off_card") else ")"
            cv2.putText(img, f"{len(boxes)} found | {ppm:.1f} px/mm", (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 1)
        cv2.imwrite(str(args.out / path.name), img)
        print(line)
    print(f"overlays in {args.out}/")
    return 0


def cmd_set_mask(args) -> int:
    """Areas the detector ignores (the lure), as fractions of the photo: x1 y1 x2 y2."""
    with session_scope() as db:
        trap = db.get(Trap, args.trap_id)
        if trap is None:
            print(f"no trap {args.trap_id}", file=sys.stderr)
            return 1
        if args.none:
            trap.mask = []
        elif args.box:
            trap.mask = [list(b) for b in args.box]
        print(f"{trap.id} mask: {trap.mask or 'none'}")
    return 0


def cmd_set_scale(args) -> int:
    """The camera's measured px/mm at the card centre: photos whose grid reads far from it are left out."""
    with session_scope() as db:
        trap = db.get(Trap, args.trap_id)
        if trap is None:
            print(f"no trap {args.trap_id}", file=sys.stderr)
            return 1
        if args.none:
            trap.px_per_mm = None
        elif args.px_per_mm is not None:
            if args.px_per_mm <= 0:
                print("px/mm must be above 0", file=sys.stderr)
                return 1
            trap.px_per_mm = args.px_per_mm
        print(f"{trap.id} scale: {f'{trap.px_per_mm} px/mm' if trap.px_per_mm else 'not set (checked per liner)'}")
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


def cmd_evaluate(args) -> int:
    """Score counts, detection and biofix against a person's count (see evaluate.py for the file formats)."""
    from . import evaluate as ev

    init_db()
    targets = ev.Targets(count=args.count_target, iomin=args.iomin, biofix_days=args.biofix_days)
    counts = ev.read_counts(args.counts) if args.counts else None
    boxes = ev.read_boxes(args.boxes) if args.boxes else None
    with session_scope() as db:
        md = ev.to_markdown(ev.evaluate(db, counts, boxes, targets))
    print(md)
    if args.out:
        args.out.write_text(md)
        print(f"saved {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sentinel-server", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create the database").set_defaults(fn=cmd_init)

    p = sub.add_parser("add-trap", help="register a trap and print its API key")
    p.add_argument("trap_id")
    p.add_argument("--lure", choices=["CM", "OFM", "OBLR"], help="the trap's lure (cameras only)")
    p.add_argument("--name", default="")
    p.add_argument("--block", default="")
    p.add_argument("--kind", choices=list(TRAP_KINDS), default="pi",
                   help="esp32: a camera that uploads through --hub; hub: a Pi with no camera; pi: a Pi camera trap")
    p.add_argument("--hub", default=None, help="the hub an ESP32 camera sends its photos through")
    p.set_defaults(fn=cmd_add_trap)

    p = sub.add_parser("set-kind", help="switch a Raspberry Pi between camera trap ('pi') and hub with no camera ('hub')")
    p.add_argument("trap_id")
    p.add_argument("kind", choices=["pi", "hub"])
    p.set_defaults(fn=cmd_set_kind)

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

    p = sub.add_parser("backup", help="snapshot the database and copy new photos to a folder (and push it elsewhere)")
    p.add_argument("dest", type=Path, help="backup folder, outside the data folder")
    p.add_argument("--keep", type=int, default=14, help="database snapshots to keep (default 14)")
    p.add_argument("--push", metavar="TARGET", help="then rsync the folder here: a path or user@host:path")
    p.set_defaults(fn=cmd_backup)

    p = sub.add_parser("reprocess", help="re-run detection/tracking for one liner")
    p.add_argument("--card", type=int, required=True)
    p.set_defaults(fn=cmd_reprocess)

    p = sub.add_parser("detect", help="run the detector on photos and save annotated copies")
    p.add_argument("images", type=Path, nargs="+")
    p.add_argument("--out", type=Path, default=Path("overlays"))
    p.add_argument("--detector", choices=["baseline", "flatbug", "yolo"])
    p.add_argument("--lens", help="baseline: lens distortion k, or 'auto' (default: SENTINEL_LENS_K)")
    p.set_defaults(fn=cmd_detect)

    p = sub.add_parser("set-mask", help="set (or show) the area a trap's detector ignores")
    p.add_argument("trap_id")
    p.add_argument("--box", type=float, nargs=4, action="append", metavar=("X1", "Y1", "X2", "Y2"))
    p.add_argument("--none", action="store_true")
    p.set_defaults(fn=cmd_set_mask)

    p = sub.add_parser("set-scale", help="set (or show) a camera's measured px/mm, which photos are checked against")
    p.add_argument("trap_id")
    p.add_argument("px_per_mm", type=float, nargs="?")
    p.add_argument("--none", action="store_true", help="forget it: check each liner's photos against each other")
    p.set_defaults(fn=cmd_set_scale)

    p = sub.add_parser("import-weather", help="import daily max/min temperatures (°F)")
    p.add_argument("csv", type=Path)
    p.add_argument("--source", default="newa:station")
    p.set_defaults(fn=cmd_import_weather)

    p = sub.add_parser("evaluate", help="score counts, detection (IoMin) and biofix against manual truth")
    p.add_argument("--counts", type=Path, help="CSV card,date,label,count from counting the liners by hand")
    p.add_argument("--boxes", type=Path, help="CSV photo,x1,y1,x2,y2[,label] of insects drawn on some photos")
    p.add_argument("--out", type=Path, help="also save the report (Markdown)")
    p.add_argument("--count-target", type=float, default=0.80, help="pass mark for count accuracy (default 0.80)")
    p.add_argument("--iomin", type=float, default=0.5, help="detection match threshold (default 0.5)")
    p.add_argument("--biofix-days", type=int, default=1, help="biofix passes if within this many days (default 1)")
    p.set_defaults(fn=cmd_evaluate)

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
