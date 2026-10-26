"""The team labelling site. Run from inside ml/:

    python -m label_site users nina sunny patti jacqui claire anna emily albert --admin nina
    python -m label_site init                  # site.db from photo_checks.csv + labels.csv (prelabel_liners.py)
    python -m label_site guide                 # example crops for the in-app guide
    python -m label_site assign --labellers sunny patti jacqui claire anna emily albert --experts nina --species patti
    python -m label_site serve --secure        # http://127.0.0.1:8765, behind Tailscale Funnel on the Pi
    python -m label_site export                # labels.csv, photo_tags.csv, coco.json, yolo.zip back out
    python -m label_site carry                 # copy a finished photo's boxes to other shots of the same card
    python -m label_site revert --user sunny --since 2026-10-26     # undo one person's changes

Everything lives in data/review/labelling_site/ (paths.LABEL_SITE): site.db, inbox/, crops/, auth/.
How the work is shared out (hidden test photos, two-person photos, review) is in workflow.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import secrets
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import paths

from . import workflow
from .auth import hash_password, new_password
from .db import BOX_FIELDS, EDITABLE, Store, connect, import_site


def cmd_users(a) -> None:
    d = a.site / "auth"
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    users_path, secret_path, pw_path = d / "users.json", d / "secret", d / "passwords.txt"
    users = json.loads(users_path.read_text()) if users_path.exists() else {}
    if not secret_path.exists():
        secret_path.write_text(secrets.token_hex(32))
        os.chmod(secret_path, 0o600)
    made = []
    for name in (n.strip().lower() for n in a.names):
        if not name.isidentifier():
            raise SystemExit(f"{name!r}: use letters, digits and _ only")
        if name not in users or a.reset:
            pw = new_password()
            users[name] = {**users.get(name, {}), **hash_password(pw)}
            made.append((name, pw))
        users[name]["admin"] = name in {x.lower() for x in a.admin} or bool(users[name].get("admin") and not a.admin)
    tmp = users_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(users, indent=1))
    os.chmod(tmp, 0o600)
    tmp.replace(users_path)
    if made:
        fd = os.open(pw_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a") as f:
            f.writelines(f"{n}\t{p}\n" for n, p in made)
    admins = [n for n, u in users.items() if u.get("admin")]
    print(f"{len(users)} logins ({', '.join(admins) or 'no'} admin) in {users_path}; new passwords for "
          f"{', '.join(n for n, _ in made) or 'nobody'}" + (f" in {pw_path} (send them, then delete the file)" if made else ""))


def cmd_init(a) -> None:
    con = connect(a.site / "site.db")
    p, b = import_site(con, a.site)
    print(f"added {p} photos, {b} boxes to {a.site / 'site.db'}")


def cmd_assign(a) -> None:
    store = Store(a.site)
    got = workflow.assign(store, [u.lower() for u in a.labellers], [u.lower() for u in a.experts], a.gold,
                          a.gold_each, a.double)
    print(json.dumps(got))


def cmd_serve(a) -> None:
    from .server import serve

    serve(a.site, a.site / "auth", a.host, a.port, a.secure, [u.lower() for u in a.species])


def cmd_export(a) -> None:
    """labels.csv (the main copy, as label_field_cards.py folders have it, plus site and set columns),
    photo_tags.csv (check_liner_photos.py reads it), coco.json and yolo.zip, into exports/<time>/."""
    from crop_field_cards import FIELDS

    from .server import coco_export, yolo_export

    store = Store(a.site)
    out = a.site / "exports" / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    photos = {p["name"]: p for p in store.q("SELECT * FROM photos")}
    with open(out / "labels.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["site_photo", "set", *FIELDS, "attrs", "checked_at"], restval="", extrasaction="ignore")
        w.writeheader()
        for name, p in sorted(photos.items()):
            for n, b in enumerate(store.boxes(name, "main"), 1):
                w.writerow({**b, "site_photo": name, "set": p["set_name"], "photo": p["file"], "n": str(n)})
    with open(out / "photo_tags.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["photo", "user", "tag", "at"])
        for t in store.q("SELECT * FROM tags ORDER BY photo"):
            w.writerow([t["photo"], t["user"], t["tag"], datetime.fromtimestamp(t["at"]).isoformat(timespec="seconds")])
    shutil.copy(out / "photo_tags.csv", a.site / "photo_tags.csv")
    (out / "coco.json").write_text(json.dumps(coco_export(store)))
    (out / "yolo.zip").write_bytes(yolo_export(store, a.site))
    print(f"exported {len(photos)} photos to {out}")


def cmd_revert(a) -> None:
    """Put back, newest first, every box change one person made since a date (from the log)."""
    store = Store(a.site)
    since = datetime.fromisoformat(a.since).timestamp()
    rows = store.q("SELECT * FROM log WHERE user=? AND at>=? AND box_id IS NOT NULL ORDER BY at DESC", a.user, since)
    n = 0
    for r in rows:
        before = json.loads(r["before"]) if r["before"] else None
        if r["action"] == "draw":
            store.con.execute("DELETE FROM boxes WHERE id=?", (r["box_id"],))
        elif before is not None:
            exists = store.q("SELECT 1 FROM boxes WHERE id=?", r["box_id"])
            if exists:
                store.con.execute(f"UPDATE boxes SET {', '.join(k + '=?' for k in EDITABLE)}, by='' WHERE id=?",  # noqa: S608
                                  [before[k] for k in EDITABLE] + [r["box_id"]])
        elif r["action"] == "confirm":
            store.con.execute("UPDATE boxes SET by='' WHERE id=?", (r["box_id"],))
        store.log("revert", r["photo"], r["copy"], r["box_id"], f"revert:{r['action']}", None, {"of": r["id"]})
        n += 1
    print(f"reverted {n} changes {a.user} made since {a.since}")


def cmd_carry(a) -> None:
    """For each finished (accepted) photo, copy its boxes onto the other shots of the same card that nobody has
    checked a box on yet, through the homography between the two shots (ORB features). Carried boxes keep
    their label as old_label and stay unchecked."""
    import cv2
    import numpy as np
    from PIL import Image, ImageOps

    store = Store(a.site)

    def load(name):
        with Image.open(a.site / "inbox" / name) as im:
            img = ImageOps.exif_transpose(im).convert("L")
        f = min(1.0, 1200 / max(img.size))
        small = np.asarray(img.resize((int(img.width * f), int(img.height * f))))
        kp, des = cv2.ORB_create(4000).detectAndCompute(small, None)
        return kp, des, f

    done = store.q("SELECT DISTINCT t.photo, p.card, p.set_name FROM tasks t JOIN photos p ON p.name=t.photo"
                   " WHERE t.status='accepted' AND t.kind IN ('label','tiebreak') AND p.card != ''")
    carried = 0
    for d in done:
        others = store.q("SELECT name FROM photos WHERE card=? AND set_name=? AND name!=?", d["card"], d["set_name"], d["photo"])
        for o in others:
            if store.q("SELECT 1 FROM boxes WHERE photo=? AND copy='main' AND by!='' LIMIT 1", o["name"]):
                continue
            ka, da, fa = load(d["photo"])
            kb, db_, fb = load(o["name"])
            pairs = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(da, db_, k=2)
            good = [m for m, *n in pairs if n and m.distance < 0.75 * n[0].distance]
            if len(good) < 60:
                continue
            H, inl = cv2.findHomography(np.float32([ka[m.queryIdx].pt for m in good]) / fa,
                                        np.float32([kb[m.trainIdx].pt for m in good]) / fb, cv2.RANSAC, 5.0)
            if H is None or inl.sum() < 60:
                continue
            new = []
            for b in store.boxes(d["photo"], "main"):
                if b["label"] == "skip":
                    continue
                pts = cv2.perspectiveTransform(np.float32([[[float(b["x1"]), float(b["y1"])], [float(b["x2"]), float(b["y1"])],
                                                            [float(b["x2"]), float(b["y2"])], [float(b["x1"]), float(b["y2"])]]]), H)[0]
                new.append({**{k: b[k] for k in BOX_FIELDS}, "x1": float(pts[:, 0].min()), "y1": float(pts[:, 1].min()),
                            "x2": float(pts[:, 0].max()), "y2": float(pts[:, 1].max()), "source": "carried",
                            "old_label": f"{b['label']} (carried from {d['photo']})", "by": "", "crop": "", "cutout": ""})
            store.replace_copy(o["name"], "main", new, "carry")
            carried += 1
            print(f"  {d['photo']} -> {o['name']}: {len(new)} boxes")
    print(f"carried labels to {carried} photos")


def cmd_guide(a) -> None:
    """Example crops for the in-app guide: a few of each class from the labelled real-liner crops."""
    import random

    rng = random.Random(1)
    out = a.site / "guide"
    out.mkdir(parents=True, exist_ok=True)
    src = a.data / paths.WEB_LINERS / "species"
    picked = {}
    for label in ("CM", "OFM", "OBLR", "other_moth", "other_insect", "debris"):
        files = sorted((src / label).glob("*.jpg")) if (src / label).exists() else []
        if not files and label in ("other_insect", "debris"):  # from the site's own checked boxes, if any
            files = [Path(b["crop"]) for b in Store(a.site).q("SELECT crop FROM boxes WHERE label=? AND by!='' AND crop!=''", label)]
        for i, f in enumerate(rng.sample(files, min(4, len(files)))):
            shutil.copy(f, out / f"{label}_{i}.jpg")
            picked.setdefault(label, []).append(f"{label}_{i}.jpg")
    (out / "examples.json").write_text(json.dumps(picked))
    print(f"guide examples: { {k: len(v) for k, v in picked.items()} } in {out}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m label_site", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=paths.DATA)
    sub = ap.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("users", help="make logins (users.json, secret, passwords.txt)")
    u.add_argument("names", nargs="+")
    u.add_argument("--admin", nargs="*", default=[], help="these names review, see the dashboard and export")
    u.add_argument("--reset", action="store_true", help="new passwords for these names even if they exist")
    sub.add_parser("init", help="import photo_checks.csv + labels.csv into site.db (only what's new)")
    sub.add_parser("guide", help="copy example crops for the in-app guide")
    s = sub.add_parser("assign", help="share the unassigned photos out")
    s.add_argument("--labellers", nargs="+", required=True)
    s.add_argument("--experts", nargs="+", required=True, help="label the hidden test photos (the first one does)")
    s.add_argument("--gold", type=int, default=12, help="hidden test photos in all")
    s.add_argument("--gold-each", type=int, default=3, help="hidden test photos in each labeller's queue")
    s.add_argument("--double", type=float, default=0.10, help="share of photos two people label apart")
    v = sub.add_parser("serve", help="run the site")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8765)
    v.add_argument("--secure", action="store_true", help="behind https (Funnel): Secure cookies and HSTS")
    v.add_argument("--species", nargs="*", default=["patti"], help="who does pass 2 (species)")
    sub.add_parser("export", help="labels.csv, photo_tags.csv, coco.json, yolo.zip into exports/")
    sub.add_parser("carry", help="carry finished photos' boxes to other shots of the same card")
    r = sub.add_parser("revert", help="undo one person's changes since a date")
    r.add_argument("--user", required=True)
    r.add_argument("--since", required=True, help="YYYY-MM-DD or YYYY-MM-DDTHH:MM")
    a = ap.parse_args(argv)
    a.site = a.data / paths.LABEL_SITE
    if a.cmd == "serve" and a.host not in ("127.0.0.1", "localhost", "::1"):
        print("warning: listening beyond this machine; on the Pi keep 127.0.0.1 and let Funnel be the way in")
    {"users": cmd_users, "init": cmd_init, "assign": cmd_assign, "serve": cmd_serve, "export": cmd_export,
     "carry": cmd_carry, "revert": cmd_revert, "guide": cmd_guide}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
