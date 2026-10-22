#!/usr/bin/env python3
"""Build the window day test's report from a run folder that finish.sh filled: report.html (charts, the
measures from the README, a photo per time of day) and summary.md (the numbers for docs/esp32-traps.md).

    python3 report.py runs/current [--photo-ma 180 --checkin-ma 120 --sleep-ma 5]

The power figures are an estimate: awake time per wake (reported by the camera) times assumed currents.
The sleep current of a dev board (USB chip, power LED) is not known and probably dominates: measure it
with a USB power meter and pass --sleep-ma.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

LOCAL = ZoneInfo("America/New_York")
SLOT_OFFSET_S = 60  # [hub] node_offset_s: cameras aim for 60 s after each slot


def utc(s: str) -> datetime:
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def env(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def rows(path: Path) -> list[dict]:
    return list(csv.DictReader(path.open())) if path.exists() else []


def num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------------ charts (inline SVG)

COLORS = ["#2a7de1", "#e8743b", "#19a979", "#d64b8a", "#8a63d2", "#888"]


def chart(title: str, series: list[tuple[str, list[tuple[datetime, float]]]], start: datetime, end: datetime,
          unit: str = "", events: list[tuple[datetime, str]] = (), kind: str = "dots", ref: float | None = None) -> str:
    W, H, L, R, T, B = 900, 220, 56, 12, 12, 28
    pts = [y for _, s in series for _, y in s]
    if not pts:
        return f"<h3>{html.escape(title)}</h3><p class=muted>No data.</p>"
    lo, hi = min(pts + ([ref] if ref is not None else [])), max(pts + ([ref] if ref is not None else []))
    if hi == lo:
        lo, hi = lo - 1, hi + 1
    pad = (hi - lo) * 0.08
    lo, hi = lo - pad, hi + pad
    span = (end - start).total_seconds() or 1
    x = lambda t: L + (W - L - R) * (t - start).total_seconds() / span
    y = lambda v: T + (H - T - B) * (1 - (v - lo) / (hi - lo))
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{html.escape(title)}">']
    for i in range(5):  # y grid
        v = lo + (hi - lo) * i / 4
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
                   f'<text x="{L - 6}" y="{y(v) + 4:.1f}" text-anchor="end" class="tick">{v:.4g}</text>')
    t = start.astimezone(LOCAL).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    step = max(1, round(span / 3600 / 12))
    while t <= end:
        if t.hour % step == 0:
            out.append(f'<text x="{x(t):.1f}" y="{H - 8}" text-anchor="middle" class="tick">{t:%H:%M}</text>')
        t += timedelta(hours=1)
    if ref is not None:
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(ref):.1f}" y2="{y(ref):.1f}" class="ref"/>')
    for when, label in events:
        if start <= when <= end:
            out.append(f'<line x1="{x(when):.1f}" x2="{x(when):.1f}" y1="{T}" y2="{H - B}" class="event">'
                       f'<title>{html.escape(label)} {when.astimezone(LOCAL):%H:%M}</title></line>')
    for i, (name, s) in enumerate(series):
        c = COLORS[i % len(COLORS)]
        s = sorted(s)
        if kind == "line" and len(s) > 1:
            out.append(f'<polyline fill="none" stroke="{c}" stroke-width="1.8" points="'
                       + " ".join(f"{x(a):.1f},{y(b):.1f}" for a, b in s) + '"/>')
        else:
            out += [f'<circle cx="{x(a):.1f}" cy="{y(b):.1f}" r="3" fill="{c}"><title>{name} {a.astimezone(LOCAL):%H:%M}: {b:.4g} {unit}</title></circle>'
                    for a, b in s]
    out.append("</svg>")
    legend = " ".join(f'<span class=key><i style="background:{COLORS[i % len(COLORS)]}"></i>{html.escape(n)}</span>'
                      for i, (n, _) in enumerate(series))
    return f"<h3>{html.escape(title)}{f' <span class=muted>({unit})</span>' if unit else ''}</h3><div class=legend>{legend}</div>{''.join(out)}"


# ------------------------------------------------------------------ the measures

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("--photo-ma", type=float, default=180, help="assumed average current while awake for a photo (mA at 5 V)")
    ap.add_argument("--checkin-ma", type=float, default=120, help="assumed average current during a Wi-Fi-only wake (check-in, or a search for a lost hub)")
    ap.add_argument("--sleep-ma", type=float, default=5, help="assumed current asleep (dev board: measure it)")
    args = ap.parse_args()
    run = args.run.resolve()
    cfg = env(Path(__file__).with_name("test.env"))
    meta = env(run / "run.env")
    start = utc(meta["START"])
    end = utc(meta["END"]) if "END" in meta else datetime.now(timezone.utc)
    every = int(cfg.get("PHOTO_EVERY_MIN", 30))

    data = json.loads((run / "captures.json").read_text()) if (run / "captures.json").exists() else {"captures": [], "new_cards": []}
    caps = data["captures"]
    for c in caps:
        c["t"] = utc(c["captured_at"])
        c["server_at"] = utc(c["received_at"])
        hub = (c["meta"].get("hub") or {}).get("received_at")
        c["hub_at"] = utc(hub) if hub else None
        c["dev"] = c["meta"].get("device") or {}
    statuses = [json.loads(line) for line in (run / "status.jsonl").read_text().splitlines() if line.strip()] \
        if (run / "status.jsonl").exists() else []
    statuses = [s for s in statuses if start <= utc(s["at"]) <= end]
    for s in statuses:
        s["t"] = utc(s["at"])
    hub_rows, server_rows = rows(run / "hub.csv"), rows(run / "server.csv")
    events = [(utc(r[0]), r[1] + (f": {r[2]}" if len(r) > 2 and r[2] else "")) for r in csv.reader((run / "events.csv").open())] \
        if (run / "events.csv").exists() else []

    # 1. Reliability: a scheduled photo for every slot, from the camera's first contact after the start
    # (until then it doesn't know the test schedule).
    contacts = sorted([s["t"] for s in statuses] + [c["hub_at"] for c in caps if c["hub_at"] and c["hub_at"] >= start])
    first = (contacts[0] if contacts else start).replace(second=0, microsecond=0)
    first += timedelta(minutes=(-first.minute) % every)
    slots, t = [], first
    while t + timedelta(seconds=SLOT_OFFSET_S) <= end:
        slots.append(t)
        t += timedelta(minutes=every)
    scheduled = [c for c in caps if c["wake_reason"] == "scheduled"]
    matched, missing = {}, []
    for s in slots:
        target = s + timedelta(seconds=SLOT_OFFSET_S)
        near = [c for c in scheduled if abs((c["t"] - target).total_seconds()) <= 300 and id(c) not in {id(m) for m in matched.values()}]
        if near:
            matched[s] = min(near, key=lambda c: abs((c["t"] - target).total_seconds()))
        else:
            missing.append(s)
    offsets = [(c["t"], (c["t"] - (s + timedelta(seconds=SLOT_OFFSET_S))).total_seconds()) for s, c in matched.items()]

    # 2. Hops, 3. signal and heat, 4. boots, 5. duplicates, 6. statuses.
    hub_delay = [(c["t"], (c["hub_at"] - c["t"]).total_seconds() / 60) for c in caps if c["hub_at"]]
    server_delay = [(c["t"], (c["server_at"] - (c["hub_at"] or c["t"])).total_seconds() / 60) for c in caps]
    rssi = [(s["t"], s["rssi"]) for s in statuses if isinstance(s.get("rssi"), (int, float))] \
        or [(c["t"], c["dev"]["rssi"]) for c in caps if isinstance(c["dev"].get("rssi"), (int, float))]
    temp = [(s["t"], s["cpu_temp_c"]) for s in statuses if isinstance(s.get("cpu_temp_c"), (int, float))] \
        or [(c["t"], c["dev"]["cpu_temp_c"]) for c in caps if isinstance(c["dev"].get("cpu_temp_c"), (int, float))]
    drift = [(s["t"], s["drift_ppm"]) for s in statuses if isinstance(s.get("drift_ppm"), (int, float))]
    boot_jumps, resets = [], []
    for a, b in zip(statuses, statuses[1:]):
        if not (isinstance(a.get("boots"), int) and isinstance(b.get("boots"), int)):
            continue
        if b["boots"] < a["boots"]:
            resets.append(b["t"])
        elif b["boots"] - a["boots"] > 1:
            boot_jumps.append((b["t"], b["boots"] - a["boots"] - 1))
    errors = Counter(s.get("last_error") for s in statuses if s.get("last_error"))
    dup = [k for k, n in Counter(c["meta"].get("node_capture_id") for c in caps).items() if k and n > 1]
    status_counts = Counter(c["status"] for c in caps)
    fail_reasons = Counter((c["error"] or "").split(":")[0] + ": " + ((c["error"] or "").split(":")[1].split("(")[0].strip()
                           if ":" in (c["error"] or "") else "") for c in caps if c["status"] == "failed")
    stuck = [c for c in caps if c["status"] == "new"]

    # 7. Take a photo now: from each request to the photo it brought.
    requested = [c for c in caps if c["wake_reason"] == "requested"]
    asks = []
    for when, label in events:
        if label.startswith("photo-now"):
            got = next((c for c in requested if c["t"] >= when), None)
            asks.append((when, got, (got["server_at"] - when).total_seconds() / 60 if got else None))

    # 8. Power estimate from awake time per wake.
    wakes = []  # (time, kind, awake s, reached hub)
    for i, s in enumerate(statuses):
        if s.get("prev_wake") and isinstance(s.get("prev_awake_ms"), (int, float)) and i > 0:
            wakes.append((statuses[i - 1]["t"], s["prev_wake"], s["prev_awake_ms"] / 1000, bool(s.get("prev_reached_hub"))))
    if statuses and isinstance(statuses[-1].get("awake_ms"), (int, float)):  # the last wake: as far as it got
        wakes.append((statuses[-1]["t"], statuses[-1].get("wake", "?"), statuses[-1]["awake_ms"] / 1000, True))
    hours = (end - start).total_seconds() / 3600
    awake_s = sum(w[2] for w in wakes)
    ma = lambda kind: args.checkin_ma if kind in ("checkin", "search") else args.photo_ma  # search: Wi-Fi only, no photo
    awake_mah = sum(w[2] / 3600 * ma(w[1]) for w in wakes)
    sleep_mah = max(0.0, hours - awake_s / 3600) * args.sleep_ma
    by_kind = Counter(w[1] for w in wakes)
    awake_by_kind = {k: sum(w[2] for w in wakes if w[1] == k) for k in by_kind}

    # 9. Pi health from the loggers.
    hub_ips = sorted({r["wlan0_ip"] for r in hub_rows if r.get("wlan0_ip")})
    throttled = sorted({r.get("throttled") for r in hub_rows + server_rows if r.get("throttled") not in (None, "", "0x0")})
    hub_queue = [(utc(r["at"]), num(r["queued"], 0)) for r in hub_rows]
    mem = [(utc(r["at"]), num(r["mem_used_mb"], 0)) for r in server_rows]
    swap = [(utc(r["at"]), num(r["swap_used_mb"], 0)) for r in server_rows]
    locked = sum(int(num(r.get("db_locked_10min"), 0)) for r in server_rows)
    tracebacks = sum(int(num(r.get("tracebacks_10min"), 0)) for r in server_rows)
    pi_temp = [(utc(r["at"]), num(r["cpu_temp_c"], 0)) for r in hub_rows], [(utc(r["at"]), num(r["cpu_temp_c"], 0)) for r in server_rows]

    # ------------------------------------------------------------------ write it up
    fmt = lambda d: d.astimezone(LOCAL).strftime("%b %d %H:%M")
    med = lambda v: sorted(v)[len(v) // 2] if v else None
    off = [o for _, o in offsets]
    summary = [
        ("Window", f"{fmt(start)} to {fmt(end)} ({hours:.1f} h), a photo every {every} min, check-ins every {cfg.get('CHECKIN_MIN')} min; "
                   f"slots counted from the camera's first contact, {fmt(contacts[0]) if contacts else 'none yet'}"),
        ("Scheduled photos", f"{len(matched)} of {len(slots)} slots ({100 * len(matched) / max(1, len(slots)):.0f}%); "
                             f"{len(missing)} missing" + (f": {', '.join(fmt(s)[7:] for s in missing[:12])}{' …' if len(missing) > 12 else ''}" if missing else "")),
        ("All photos", f"{len(caps)}: " + ", ".join(f"{n} {k}" for k, n in Counter(c['wake_reason'] for c in caps).most_common())),
        ("Wake timing (photo time − slot − 60 s)",
         f"median {med(off):+.1f} s, range {min(off):+.1f} to {max(off):+.1f} s" if off else "no scheduled photos"),
        ("Clock drift (camera's estimate)", f"{drift[-1][1]:+.0f} ppm at the end" if drift else "not reported"),
        ("Delay camera → hub", f"median {med([d for _, d in hub_delay]) or 0:.1f} min, max {max([d for _, d in hub_delay], default=0):.1f} min"),
        ("Delay hub → server", f"median {med([d for _, d in server_delay]) or 0:.1f} min, max {max([d for _, d in server_delay], default=0):.1f} min"),
        ("Signal (rssi)", f"{min(v for _, v in rssi):.0f} to {max(v for _, v in rssi):.0f} dBm, median {med([v for _, v in rssi]):.0f}" if rssi else "—"),
        ("Chip temperature", f"{min(v for _, v in temp):.0f} to {max(v for _, v in temp):.0f} °C" if temp else "—"),
        ("Boots", f"{len(resets)} reset(s) (power lost or crash), {sum(n for _, n in boot_jumps)} wake(s) with no status (didn't reach the hub)"),
        ("Camera errors", ", ".join(f"{k} ×{n}" for k, n in errors.items()) or "none"),
        ("Duplicate photos", f"{len(dup)}" + (f": {', '.join(dup[:5])}" if dup else "")),
        ("Server status", ", ".join(f"{n} {k}" for k, n in status_counts.items()) + (f"; {len(stuck)} stuck at new" if stuck else "")),
        ("Why photos failed", "; ".join(f"{k} ×{n}" for k, n in fail_reasons.most_common()) or "none"),
        ("Take a photo now", "; ".join(f"{fmt(w)[7:]} → {f'{lat:.0f} min' if lat is not None else 'no photo'}" for w, _, lat in asks) or "not tried"),
        ("Hub address", ", ".join(hub_ips) + (" !! CHANGED during the test" if len(hub_ips) > 1 else " (unchanged)") if hub_ips else "—"),
        ("Pi health", f"throttled {', '.join(throttled) or 'never'}; database locked {locked}×, server tracebacks {tracebacks}"),
        ("Awake time", f"{awake_s / 60:.1f} min in {len(wakes)} wakes: " + ", ".join(f"{n} {k} ({awake_by_kind[k] / max(1, n):.1f} s each)" for k, n in by_kind.most_common())),
        ("Power estimate", f"{awake_mah + sleep_mah:.0f} mAh at 5 V over {hours:.1f} h = {(awake_mah + sleep_mah) * 24 / max(hours, 0.1):.0f} mAh/day "
                           f"(awake {awake_mah:.1f} mAh at {args.photo_ma:.0f}/{args.checkin_ma:.0f} mA, asleep {sleep_mah:.0f} mAh at an assumed {args.sleep_ma} mA)"),
    ]

    ev = events
    charts = [
        chart("Wake timing: photo time minus (slot + 60 s)", [("scheduled photos", offsets)], start, end, "s", ev, ref=0),
        chart("Clock drift the camera measured", [("drift", drift)], start, end, "ppm", ev, kind="line", ref=0),
        chart("Delay at each hop", [("camera → hub", hub_delay), ("hub → server", server_delay)], start, end, "min", ev),
        chart("Signal at the window", [("rssi", rssi)], start, end, "dBm", ev, ref=-80),
        chart("Chip temperature", [("ESP32", temp)], start, end, "°C", ev),
        chart("Awake time per wake", [(k, [(w[0], w[2]) for w in wakes if w[1] == k]) for k in by_kind], start, end, "s", ev),
        chart("Hub queue", [("photos waiting on the hub", hub_queue)], start, end, "photos", ev, kind="line"),
        chart("Server memory", [("used", mem), ("swap", swap)], start, end, "MB", ev, kind="line"),
        chart("Pi temperatures", [("hub", pi_temp[0]), ("server", pi_temp[1])], start, end, "°C", ev, kind="line"),
    ]

    # Photos at dawn, noon, dusk and night (the nearest one to each).
    day0 = start.astimezone(LOCAL).date()
    gallery = []
    for label, hh, mm in [("Night", 1, 0), ("Dawn", 7, 30), ("Noon", 12, 30), ("Dusk", 18, 15), ("Night", 22, 30)]:
        for d in (day0, day0 + timedelta(days=1)):
            want = datetime(d.year, d.month, d.day, hh, mm, tzinfo=LOCAL)
            if start <= want <= end and caps:
                c = min(caps, key=lambda c: abs((c["t"] - want).total_seconds()))
                if abs((c["t"] - want).total_seconds()) < 3600:
                    gallery.append((f"{label} {fmt(c['t'])}", f"photos/{c['image_path']}"))
    gallery = list(dict.fromkeys(gallery))

    css = """:root{--bg:#fbfbf8;--fg:#1d1d1b;--muted:#6b6b66;--line:#ddd9cf;--card:#fff}
@media (prefers-color-scheme:dark){:root{--bg:#141412;--fg:#ecebe6;--muted:#a3a29b;--line:#34332e;--card:#1c1c19}}
body{background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;margin:0 auto;max-width:960px;padding:16px}
table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{width:28%;font-weight:600}.muted{color:var(--muted)}svg{width:100%;height:auto;background:var(--card);border:1px solid var(--line);border-radius:6px}
.grid{stroke:var(--line)}.tick{fill:var(--muted);font-size:11px}.ref{stroke:var(--muted);stroke-dasharray:4 4}.event{stroke:#d64b8a;stroke-width:1.5;stroke-dasharray:2 3}
.legend{font-size:13px;margin:-6px 0 6px}.key{margin-right:14px}.key i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px}
.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px}.gallery img{width:100%;border-radius:6px}"""
    page = [f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'><title>ESP32 window day test</title><style>{css}</style>",
            f"<h1>ESP32 window day test</h1><p class=muted>{html.escape(cfg.get('TRAP', ''))} through hub {html.escape(cfg.get('HUB', ''))} "
            f"to {html.escape(cfg.get('SERVER', ''))}. Pink dashed lines on the charts are events (hover for what).</p>",
            "<table>" + "".join(f"<tr><th>{html.escape(k)}</th><td>{html.escape(v)}</td></tr>" for k, v in summary) + "</table>",
            *charts]
    if events:
        page.append("<h3>Events</h3><table>" + "".join(f"<tr><td>{fmt(w)}</td><td>{html.escape(l)}</td></tr>" for w, l in events) + "</table>")
    if gallery:
        page.append("<h3>Photos through the day</h3><div class=gallery>" + "".join(
            f"<figure><img src='{html.escape(p)}' loading=lazy alt='{html.escape(l)}'><figcaption>{html.escape(l)}</figcaption></figure>" for l, p in gallery) + "</div>")
    if missing:
        page.append("<h3>Missing slots</h3><p>" + ", ".join(fmt(s) for s in missing) + "</p>")
    (run / "report.html").write_text("\n".join(page))
    (run / "summary.md").write_text("\n".join(f"- **{k}:** {v}" for k, v in summary) + "\n")
    print("\n".join(f"{k}: {v}" for k, v in summary))


if __name__ == "__main__":
    main()
