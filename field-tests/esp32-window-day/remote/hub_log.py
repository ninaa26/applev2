#!/usr/bin/env python3
"""Runs on the hub every 10 min (cron, installed by start.sh): one row of hub health to window-test/hub.csv.

    hub_log.py <hub data_dir> <trap id>
"""
import csv
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


def run(*cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception:
        return ""


data, trap = Path(sys.argv[1]), sys.argv[2]
node = data / "nodes" / trap
ip = run("ip", "-4", "-br", "addr", "show", "wlan0").split()
try:
    ts_online = json.loads(run("tailscale", "status", "--json"))["Self"]["Online"]
except Exception:
    ts_online = ""
mem = dict(line.split(":", 1) for line in open("/proc/meminfo"))
kb = lambda k: int(mem[k].split()[0])
row = {
    "at": datetime.now(UTC).isoformat(timespec="seconds"),
    "wlan0_ip": ip[2].split("/")[0] if len(ip) > 2 else "",
    "gateway": run("systemctl", "is-active", "sentinel-gateway"),
    "queued": len(list((node / "queue").glob("*.jpg"))),
    "sent_total": len(list((node / "sent").glob("*.jpg"))),
    "cpu_temp_c": int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000,
    "throttled": run("vcgencmd", "get_throttled").removeprefix("throttled="),
    "uptime_h": round(float(open("/proc/uptime").read().split()[0]) / 3600, 2),
    "load1": round(os.getloadavg()[0], 2),
    "mem_used_mb": (kb("MemTotal") - kb("MemAvailable")) // 1024,
    "disk_free_gb": round(shutil.disk_usage("/").free / 1e9, 1),
    "tailscale_online": ts_online,
}
out = Path.home() / "window-test" / "hub.csv"
new = not out.exists()
with out.open("a", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(row))
    if new:
        w.writeheader()
    w.writerow(row)
