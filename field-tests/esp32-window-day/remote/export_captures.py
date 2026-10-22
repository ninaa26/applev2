"""Runs on the server at the end (finish.sh), with the server's venv Python: the camera's photos since the
start as JSON on stdout, with everything the report needs from each row.

    export_captures.py <server dir> <trap id> <start, ISO UTC>
"""
import json
import sqlite3
import sys
from datetime import datetime, timezone

server_dir, trap, start = sys.argv[1], sys.argv[2], datetime.fromisoformat(sys.argv[3])
start = start.astimezone(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
db = sqlite3.connect(f"file:{server_dir}/data/sentinel.db?mode=ro", uri=True, timeout=30)
db.row_factory = sqlite3.Row
rows = db.execute(
    "select id, uid, card_id, captured_at, received_at, processed_at, status, error, wake_reason, image_path, meta "
    "from captures where trap_id = ? and received_at >= ? order by captured_at", (trap, start)).fetchall()
out = []
for r in rows:
    d = dict(r)
    d["meta"] = json.loads(d["meta"] or "{}")
    d["detections"] = db.execute("select count(*) from detections where capture_id = ?", (r["id"],)).fetchone()[0]
    out.append(d)
cards = [dict(r) for r in db.execute("select id, installed_at from cards where trap_id = ? and installed_at >= ?", (trap, start))]
json.dump({"captures": out, "new_cards": cards}, sys.stdout, default=str)
