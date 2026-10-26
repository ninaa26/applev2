"""The labelling site's store: one SQLite file (site.db) beside labels.csv. Standard library only.

Tables
  photos   one row per photo on the site (from photo_checks.csv): set, source path, px/mm, card, gold (a hidden
           test photo), priority (how unsure the models were: the queue shows the most unsure first)
  boxes    every box, in a `copy`: "main" is the photo's labels; "gold" the expert's labels of a hidden test
           photo; "u:<name>" one person's private copy (a hidden test photo, or a photo two people label apart)
  tasks    who works on which copy of which photo: kind label | double | gold_check | gold_truth | tiebreak | species,
           status open | done | accepted | returned (a reviewer sent it back, with a note)
  issues   review comments pinned to a spot or a box, until the labeller marks them resolved
  tags     photo-level tags a person set (unusable, wrong scale, not a gridded liner)
  log      every change, append-only: who, when, which box, before -> after (JSON)
  merges   the agreement between the two people of each double-labelled photo
Writes go through Store, which holds one lock: the site is small (a few people), so simple beats clever.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS photos (name TEXT PRIMARY KEY, set_name TEXT, file TEXT, source TEXT, px_per_mm REAL,
  decision TEXT, why TEXT, card TEXT, held_out INTEGER DEFAULT 0, gold INTEGER DEFAULT 0, priority REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS boxes (id INTEGER PRIMARY KEY, photo TEXT, copy TEXT DEFAULT 'main',
  x1 REAL, y1 REAL, x2 REAL, y2 REAL, label TEXT DEFAULT '', source TEXT, conf TEXT, detector_label TEXT,
  model_label TEXT, model_conf TEXT, old_label TEXT, by TEXT DEFAULT '', checked_at REAL, attrs TEXT DEFAULT '',
  locked INTEGER DEFAULT 0, ppm TEXT, length_mm TEXT, body_mm TEXT, length_from TEXT, crop TEXT, cutout TEXT,
  csv_n TEXT);
CREATE INDEX IF NOT EXISTS boxes_photo ON boxes(photo, copy);
CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, photo TEXT, user TEXT, kind TEXT, copy TEXT,
  status TEXT DEFAULT 'open', priority REAL DEFAULT 0, created REAL, done_at REAL, reviewer TEXT,
  reviewed_at REAL, note TEXT DEFAULT '');
CREATE INDEX IF NOT EXISTS tasks_user ON tasks(user, status);
CREATE TABLE IF NOT EXISTS issues (id INTEGER PRIMARY KEY, photo TEXT, copy TEXT, box_id INTEGER, x REAL, y REAL,
  kind TEXT, text TEXT, by TEXT, at REAL, resolved_by TEXT, resolved_at REAL);
CREATE TABLE IF NOT EXISTS tags (photo TEXT, user TEXT, tag TEXT, at REAL, PRIMARY KEY (photo, user, tag));
CREATE TABLE IF NOT EXISTS log (id INTEGER PRIMARY KEY, at REAL, user TEXT, photo TEXT, copy TEXT, box_id INTEGER,
  action TEXT, before TEXT, after TEXT);
CREATE TABLE IF NOT EXISTS merges (photo TEXT PRIMARY KEY, a TEXT, b TEXT, agreement REAL, disputes INTEGER, at REAL);
"""

BOX_FIELDS = ["x1", "y1", "x2", "y2", "label", "source", "conf", "detector_label", "model_label", "model_conf",
              "old_label", "by", "attrs", "locked", "ppm", "length_mm", "body_mm", "length_from", "crop", "cutout"]
# What a person changes; the rest is bookkeeping that follows from it.
EDITABLE = ["x1", "y1", "x2", "y2", "label", "attrs", "locked"]
TAGS = {"unusable", "wrong_scale", "not_gridded"}
TASK_FIELDS = {"status", "done_at", "reviewer", "reviewed_at", "note", "priority"}
COLUMNS = set(BOX_FIELDS) | {"checked_at", "csv_n"} | TASK_FIELDS


def cols(keys) -> list[str]:
    """Column names for an f-string query: only ever from the fixed lists above, never from a request."""
    keys = list(keys)
    if not set(keys) <= COLUMNS:
        raise ValueError(f"unknown columns {set(keys) - COLUMNS}")
    return keys
ATTRS = {"overlapping", "cut_off", "decayed", "unsure", "disputed"}


def connect(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    return con


def priority(boxes: list[dict]) -> float:
    """How unsure the models were on a photo: the share of its boxes the classifier gave under 0.8, plus the boxes
    YOLO missed (an earlier label had them). Higher goes first."""
    if not boxes:
        return 0.0
    unsure = sum(1 for b in boxes if b.get("source") == "missed-by-detector"
                 or (b.get("model_conf") and float(b["model_conf"]) < 0.8))
    return round(unsure / len(boxes), 3)


def import_site(con: sqlite3.Connection, site: Path) -> tuple[int, int]:
    """Add the photos and boxes of photo_checks.csv + labels.csv that aren't in the database yet."""
    with open(site / "photo_checks.csv", newline="") as f:
        checks = {r["photo"]: r for r in csv.DictReader(f)}
    with open(site / "labels.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    have = {r[0] for r in con.execute("SELECT name FROM photos")}
    by_photo: dict[str, list[dict]] = {}
    for r in rows:
        by_photo.setdefault(r["photo"], []).append(r)
    added_p = added_b = 0
    con.execute("BEGIN")
    # Every photo the checks kept and the pre-labeller linked, also those with no boxes at all: a person still has
    # to look whether the liner really is empty.
    linked = {p.name for p in (site / "inbox").iterdir()} if (site / "inbox").exists() else set()
    for photo in checks:
        if checks[photo]["decision"] != "exclude" and photo in linked:
            by_photo.setdefault(photo, [])
    for photo, boxes in by_photo.items():
        if photo in have or photo not in checks:
            continue
        c = checks[photo]
        con.execute("INSERT INTO photos (name, set_name, file, source, px_per_mm, decision, why, card, held_out, priority)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (photo, c["set"], c["file"], c["source"], float(c["px_per_mm"]) if c["px_per_mm"] else None,
                     c["decision"], c["why"], c["card"], 1 if c["held_out"] else 0, priority(boxes)))
        for b in boxes:
            con.execute(f"INSERT INTO boxes (photo, copy, csv_n, {', '.join(cols(BOX_FIELDS))}) VALUES (?,?,?,{','.join('?' * len(BOX_FIELDS))})",  # noqa: S608
                        [photo, "main", b.get("n", "")] + [b.get(k, "") or ("0" if k == "locked" else "") for k in BOX_FIELDS])
            added_b += 1
        added_p += 1
    con.execute("COMMIT")
    return added_p, added_b


class Conflict(Exception):
    pass


class Store:
    def __init__(self, site: Path):
        self.site = site
        self.con = connect(site / "site.db")
        self.lock = threading.RLock()

    # -- reading
    def q(self, sql: str, *args) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.con.execute(sql, args)]

    def task(self, task_id: int) -> dict | None:
        got = self.q("SELECT * FROM tasks WHERE id=?", task_id)
        return got[0] if got else None

    def boxes(self, photo: str, copy: str) -> list[dict]:
        return self.q("SELECT * FROM boxes WHERE photo=? AND copy=? ORDER BY id", photo, copy)

    def version(self, photo: str, copy: str) -> str:
        import hashlib

        rows = [[b["id"]] + [b[k] for k in EDITABLE] + [b["by"]] for b in self.boxes(photo, copy)]
        return hashlib.sha256(json.dumps(rows).encode()).hexdigest()[:16]

    # -- writing
    def log(self, user: str, photo: str, copy: str, box_id, action: str, before, after) -> None:
        self.con.execute("INSERT INTO log (at, user, photo, copy, box_id, action, before, after) VALUES (?,?,?,?,?,?,?,?)",
                         (time.time(), user, photo, copy, box_id, action,
                          json.dumps(before) if before is not None else None, json.dumps(after) if after is not None else None))

    def clone(self, photo: str, src: str, dst: str) -> None:
        """Copy a photo's boxes into another copy (a private one, or the gold one), unchecked as they were."""
        with self.lock:
            if self.q("SELECT 1 FROM boxes WHERE photo=? AND copy=? LIMIT 1", photo, dst):
                return
            c = ", ".join(cols(BOX_FIELDS))
            self.con.execute(f"INSERT INTO boxes (photo, copy, csv_n, {c}) SELECT photo, ?, csv_n, {c} FROM boxes"  # noqa: S608
                             " WHERE photo=? AND copy=?", (dst, photo, src))

    def save(self, photo: str, copy: str, boxes: list[dict], user: str, base: str | None, remeasure=None) -> list[dict]:
        """Make a copy's boxes what the page sent. Boxes the page left out are deleted (a detector's become
        "skip" instead, so they stay as a false hit). A box whose label, box or attributes changed, or that the page
        marks `confirm`, gets by = user. Every change is logged. remeasure(row) -> dict re-crops a moved box."""
        with self.lock:
            if base is not None and base != self.version(photo, copy):
                raise Conflict(photo)
            old = {b["id"]: b for b in self.boxes(photo, copy)}
            now = time.time()
            self.con.execute("BEGIN")
            try:
                seen = set()
                for b in boxes:
                    bid = b.get("id")
                    if bid is not None and int(bid) in old:
                        bid = int(bid)
                        seen.add(bid)
                        o = old[bid]
                        if o["locked"] and not b.get("unlock") and any(
                                float(o[k]) != b[k] for k in ("x1", "y1", "x2", "y2")):
                            b = {**b, **{k: float(o[k]) for k in ("x1", "y1", "x2", "y2")}}  # locked: box can't move
                        moved = any(abs(float(o[k]) - b[k]) > 0.5 for k in ("x1", "y1", "x2", "y2"))
                        changed = moved or b["label"] != o["label"] or b["attrs"] != o["attrs"] or int(b["locked"]) != o["locked"]
                        if not changed and not b.get("confirm"):
                            continue
                        upd = {k: b[k] for k in EDITABLE}
                        upd["locked"] = int(upd["locked"])
                        upd["by"], upd["checked_at"] = user, now
                        if moved:
                            upd["source"] = {"yolo": "yolo-edited", "baseline": "baseline-edited",
                                             "flatbug": "flatbug-edited"}.get(o["source"], o["source"])
                            upd["cutout"] = ""
                            if remeasure:
                                upd.update(remeasure({**o, **upd}))
                        self.con.execute(f"UPDATE boxes SET {', '.join(k + '=?' for k in cols(upd))} WHERE id=?", [*upd.values(), bid])  # noqa: S608
                        self.log(user, photo, copy, bid, "confirm" if not changed else "edit",
                                 {k: o[k] for k in EDITABLE}, {k: upd[k] for k in EDITABLE})
                    else:  # drawn on the site
                        row = {k: b[k] for k in EDITABLE}
                        row.update(locked=int(row["locked"]), source="manual", by=user, checked_at=now, conf="")
                        ppms = [float(o["ppm"]) for o in old.values() if o.get("ppm")]
                        row["ppm"] = f"{sorted(ppms)[len(ppms) // 2]:.2f}" if ppms else ""
                        if remeasure:
                            row.update(remeasure(row, photo=photo))
                        cur = self.con.execute(f"INSERT INTO boxes (photo, copy, {', '.join(cols(row))}) VALUES (?,?,{','.join('?' * len(row))})",  # noqa: S608
                                               [photo, copy, *row.values()])
                        seen.add(cur.lastrowid)
                        self.log(user, photo, copy, cur.lastrowid, "draw", None, {k: row[k] for k in EDITABLE})
                for bid, o in old.items():
                    if bid in seen:
                        continue
                    if o["source"] == "manual":
                        self.con.execute("DELETE FROM boxes WHERE id=?", (bid,))
                    else:
                        self.con.execute("UPDATE boxes SET label='skip', by=?, checked_at=? WHERE id=?", (user, now, bid))
                    self.log(user, photo, copy, bid, "delete", {k: o[k] for k in EDITABLE}, None)
                self.con.execute("COMMIT")
            except Exception:
                self.con.execute("ROLLBACK")
                raise
            return self.boxes(photo, copy)

    def set_task(self, task_id: int, **fields) -> None:
        with self.lock:
            self.con.execute(f"UPDATE tasks SET {', '.join(k + '=?' for k in cols(fields))} WHERE id=?", [*fields.values(), task_id])  # noqa: S608

    def add_task(self, photo: str, user: str, kind: str, copy: str, prio: float = 0.0) -> int:
        with self.lock:
            cur = self.con.execute("INSERT INTO tasks (photo, user, kind, copy, priority, created) VALUES (?,?,?,?,?,?)",
                                   (photo, user, kind, copy, prio, time.time()))
            return cur.lastrowid  # type: ignore[return-value]

    def add_issue(self, photo: str, copy: str, box_id, x: float, y: float, kind: str, text: str, by: str) -> int:
        with self.lock:
            cur = self.con.execute("INSERT INTO issues (photo, copy, box_id, x, y, kind, text, by, at) VALUES (?,?,?,?,?,?,?,?,?)",
                                   (photo, copy, box_id, x, y, kind, text, by, time.time()))
            return cur.lastrowid  # type: ignore[return-value]

    def resolve_issue(self, issue_id: int, user: str) -> None:
        with self.lock:
            self.con.execute("UPDATE issues SET resolved_by=?, resolved_at=? WHERE id=?", (user, time.time(), issue_id))

    def set_tag(self, photo: str, user: str, tag: str, on: bool) -> None:
        with self.lock:
            if on:
                self.con.execute("INSERT OR REPLACE INTO tags VALUES (?,?,?,?)", (photo, user, tag, time.time()))
            else:
                self.con.execute("DELETE FROM tags WHERE photo=? AND user=? AND tag=?", (photo, user, tag))
            self.log(user, photo, "", None, "tag" if on else "untag", None, {"tag": tag})

    def replace_copy(self, photo: str, copy: str, boxes: list[dict], user: str) -> list[int]:
        """Overwrite a copy with merged boxes (the two-person merge), logged as one action. The new boxes' ids."""
        with self.lock:
            self.con.execute("BEGIN")
            self.con.execute("DELETE FROM boxes WHERE photo=? AND copy=?", (photo, copy))
            ids = []
            for b in boxes:
                row = {k: b.get(k, "") for k in BOX_FIELDS if k in b}
                cur = self.con.execute(f"INSERT INTO boxes (photo, copy, {', '.join(cols(row))}) VALUES (?,?,{','.join('?' * len(row))})",  # noqa: S608
                                       [photo, copy, *row.values()])
                ids.append(cur.lastrowid)
            self.log(user, photo, copy, None, "merge", None, {"boxes": len(boxes)})
            self.con.execute("COMMIT")
            return ids
