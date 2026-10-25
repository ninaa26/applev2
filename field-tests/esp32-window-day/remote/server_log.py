"""Runs on the server every 10 min (cron, installed by start.sh) with the server's venv Python:
one row of server health and the camera's photos to window-test/server.csv.

    server_log.py <server dir> <trap id> <hub trap id>
"""
import csv
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


def run(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return ""


server_dir, trap, hub = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
now = datetime.now(UTC)
db = sqlite3.connect(f"file:{server_dir}/data/sentinel.db?mode=ro", uri=True, timeout=30)
one = lambda sql, *a: db.execute(sql, a).fetchone()[0]
naive = lambda d: d.replace(tzinfo=None).isoformat(sep=" ")
age = lambda t: round((now.replace(tzinfo=None) - datetime.fromisoformat(t)).total_seconds() / 60, 1) if t else ""
status = dict(db.execute("select status, count(*) from captures where trap_id = ? group by 1", (trap,)).fetchall())
mem = dict(line.split(":", 1) for line in open("/proc/meminfo"))
kb = lambda k: int(mem[k].split()[0])
log = run("journalctl", "-u", "sentinel-server", "--since", "-10 min", "--no-pager")
row = {
    "at": now.isoformat(timespec="seconds"),
    "server": run("systemctl", "is-active", "sentinel-server").strip(),
    "photos": sum(status.values()),
    "photos_last_hour": one("select count(*) from captures where trap_id = ? and received_at >= ?", trap, naive(now - timedelta(hours=1))),
    "last_photo_age_min": age(one("select max(received_at) from captures where trap_id = ?", trap)),
    "new": status.get("new", 0), "processed": status.get("processed", 0), "failed": status.get("failed", 0),
    "hub_last_seen_min": age(one("select last_seen_at from traps where id = ?", hub)),
    "photo_requested": bool(one("select photo_requested_at from traps where id = ?", trap)),
    "mem_used_mb": (kb("MemTotal") - kb("MemAvailable")) // 1024,
    "swap_used_mb": (kb("SwapTotal") - kb("SwapFree")) // 1024,
    "cpu_temp_c": int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000,
    "throttled": run("vcgencmd", "get_throttled").strip().removeprefix("throttled="),
    "load1": round(os.getloadavg()[0], 2),
    "db_locked_10min": log.count("database is locked"),
    "tracebacks_10min": log.count("Traceback"),
}
out = Path.home() / "window-test" / "server.csv"
new = not out.exists()
with out.open("a", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(row))
    if new:
        w.writeheader()
    w.writerow(row)
