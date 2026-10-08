"""Hub for ESP32 camera traps: take their photos over the orchard Wi-Fi and relay them to the server.

One Pi in the orchard is the hub. ESP32 traps in Wi-Fi range wake on the same schedule, photograph
their liner, POST the JPEG here, get back the time and how long to sleep, and deep-sleep again.
Each ESP32 is its own trap on the server with its own API key; the hub keeps a queue per trap
(data_dir/nodes/<trap_id>/) and uploads it with that trap's key, so the server needs no changes.

The cycle (cycle.py) keeps the gateway open for [hub] window_s each wake. On the bench, or to set up
a new ESP32, run it standalone and it stays open:

    sentinel-gateway --config config.toml --forward-every 60

Node protocol (all requests carry "Authorization: Bearer <that trap's server API key>"):

    POST /node/v1/captures   body: the JPEG; header X-Sentinel-Meta: JSON with node_capture_id
                             (random hex, the same on every retry), captured_at + clock_synced, or
                             age_s, new_card, camera, device
    GET  /node/v1/schedule   last call of a wake; marks the node done for this window

Both reply with {"now": unix seconds, "sleep_s": seconds until the node's next wake, "wakes": the next
12 wake times in unix seconds, ...}.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import logging
import re
import secrets
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

from . import config as config_mod
from .schedule import next_wake
from .uploader import Queue, drain

log = logging.getLogger(__name__)

NODE_ID = re.compile(r"[0-9a-fA-F]{8,32}")
TRAP_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")


def hash_key(key: str) -> str:
    """The server's key hash (sentinel_server.services.hash_key)."""
    return hashlib.sha256(key.encode()).hexdigest()


class Gateway:
    """Which ESP32 traps belong to this hub comes from the server (added and removed on the dashboard's
    "Set up traps" page) as {trap_id: key hash}, cached in data_dir/hub_nodes.json for wakes without
    a connection, plus any [hub.nodes.<trap_id>] in the config. A node's key arrives with its first
    request and is kept beside its queue (nodes/<trap_id>/key) to upload its photos."""

    def __init__(self, cfg: dict, data_dir: Path, clock=time.time):
        self.cfg = cfg
        self.hub = cfg["hub"]
        self.clock = clock
        data_dir.mkdir(parents=True, exist_ok=True)
        self.nodes_dir = data_dir / "nodes"
        self.cache = data_dir / "hub_nodes.json"
        self.local_keys: dict[str, str] = {}
        for trap_id, node in (self.hub.get("nodes") or {}).items():
            if not TRAP_ID.fullmatch(trap_id) or not node.get("api_key"):
                raise ValueError(f"[hub.nodes.{trap_id}] needs a plain trap id and an api_key")
            self.local_keys[trap_id] = node["api_key"]
        try:
            server = json.loads(self.cache.read_text())
        except (OSError, ValueError):
            server = {}
        self._set_nodes(server)
        self.done: set[str] = set()  # nodes that asked for their schedule since the window opened
        self.lock = threading.Lock()

    def _set_nodes(self, server: dict[str, str]) -> None:
        hashes = {t: h for t, h in server.items() if TRAP_ID.fullmatch(t) and isinstance(h, str)}
        hashes.update({t: hash_key(k) for t, k in self.local_keys.items()})
        self.hashes = hashes

    def refresh_nodes(self) -> bool:
        """Ask the server which ESP32 traps upload through this hub. Keeps the cached list if it can't."""
        try:
            r = requests.get(f"{self.cfg['server_url'].rstrip('/')}/api/v1/hub/nodes", timeout=5,
                             headers={"Authorization": f"Bearer {self.cfg['api_key']}"})
            r.raise_for_status()
            nodes = r.json()["nodes"]
            assert isinstance(nodes, dict)
        except (requests.RequestException, ValueError, KeyError, AssertionError) as e:
            log.warning("node list not refreshed (%s); using the last one: %s", e.__class__.__name__, ", ".join(self.hashes) or "none")
            return False
        tmp = self.cache.with_suffix(".tmp")
        tmp.write_text(json.dumps(nodes))
        os.replace(tmp, self.cache)
        before = set(self.hashes)
        self._set_nodes(nodes)
        if set(self.hashes) != before:
            log.info("nodes for this hub: %s", ", ".join(sorted(self.hashes)) or "none")
        return True

    def queue(self, trap_id: str) -> Queue:
        return Queue(self.nodes_dir / trap_id)

    def key_for(self, trap_id: str) -> str | None:
        if trap_id in self.local_keys:
            return self.local_keys[trap_id]
        try:
            return (self.nodes_dir / trap_id / "key").read_text().strip() or None
        except OSError:
            return None

    # ------------------------------------------------------------------ requests

    def trap_for(self, authorization: str) -> str | None:
        key = authorization.removeprefix("Bearer ").strip()
        if not key:
            return None
        given, found = hash_key(key), None
        for trap_id, h in self.hashes.items():  # compare against every hash so timing says nothing
            if secrets.compare_digest(given.encode(), h.encode()):
                found = trap_id
        if found and found not in self.local_keys and self.key_for(found) != key:
            path = self.nodes_dir / found / "key"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(mode=0o600)
            path.write_text(key)
        return found

    def schedule_reply(self) -> dict:
        now = datetime.fromtimestamp(self.clock(), timezone.utc)
        offset = timedelta(seconds=self.hub["node_offset_s"])
        # The node wakes node_offset_s after the hub's slot, once the hub has booted and opened the window.
        wakes, t = [], now - offset
        for _ in range(12):  # a node that misses a window still knows when to wake after that
            t = next_wake(t, self.cfg["schedule"]["times"], self.cfg["timezone"], min_gap=timedelta(minutes=2))
            wakes.append(t + offset)
        return {"now": now.timestamp(), "next_wake": wakes[0].isoformat(), "sleep_s": round((wakes[0] - now).total_seconds()),
                "wakes": [round(w.timestamp()) for w in wakes]}

    def capture(self, authorization: str, meta_header: str, body: bytes) -> tuple[int, dict]:
        trap_id = self.trap_for(authorization)
        if trap_id is None:
            return 401, {"error": "unknown or missing trap API key"}
        try:
            meta = json.loads(meta_header or "{}")
            assert isinstance(meta, dict)
        except (ValueError, AssertionError):
            return 422, {"error": "X-Sentinel-Meta is not a JSON object"}
        if meta.get("trap_id") not in (None, trap_id):
            return 422, {"error": f"meta trap_id {meta.get('trap_id')!r} does not match this key's trap {trap_id!r}"}
        node_id = str(meta.get("node_capture_id", ""))
        if not NODE_ID.fullmatch(node_id):
            return 422, {"error": "node_capture_id must be 8-32 hex digits"}
        if len(body) > self.hub["max_image_mb"] * 1_000_000:
            return 413, {"error": "photo too large"}
        if not (body[:2] == b"\xff\xd8" and body.rstrip(b"\x00")[-2:] == b"\xff\xd9"):
            return 415, {"error": "body is not a whole JPEG"}

        now = datetime.fromtimestamp(self.clock(), timezone.utc)
        try:
            if meta.get("clock_synced") and meta.get("captured_at"):
                captured = datetime.fromisoformat(meta["captured_at"]).astimezone(timezone.utc)
            else:  # the node has never been told the time: it says how long ago it took the photo
                captured = now - timedelta(seconds=float(meta.get("age_s", 0)))
        except (ValueError, TypeError):
            return 422, {"error": "bad captured_at or age_s"}

        queue = self.queue(trap_id)
        with self.lock:
            # A retry after a lost reply: same node_capture_id, already queued or already sent.
            for d in (queue.queue_dir, queue.sent_dir):
                if any(d.glob(f"*_{node_id}.jpg")):
                    return 200, {**self.schedule_reply(), "duplicate": True}
            uid = f"{captured.strftime('%Y%m%dT%H%M%SZ')}_{trap_id}_{node_id}"
            meta.update(capture_uid=uid, trap_id=trap_id, captured_at=captured.isoformat(),
                        wake_reason=meta.get("wake_reason", "scheduled"),
                        hub={"received_at": now.isoformat(), "hub_trap_id": self.cfg["trap_id"]})
            tmp = queue.queue_dir / f".{uid}.part"
            tmp.write_bytes(body)
            queue.add(tmp.rename(tmp.with_name(f"{uid}.jpg")), meta)
        log.info("node %s: queued %s (%d kB)", trap_id, uid, len(body) // 1000)
        return 201, {**self.schedule_reply(), "uid": uid}

    def schedule(self, authorization: str, meta_header: str = "") -> tuple[int, dict]:
        trap_id = self.trap_for(authorization)
        if trap_id is None:
            return 401, {"error": "unknown or missing trap API key"}
        with self.lock:
            self.done.add(trap_id)
        if meta_header:
            log.info("node %s status: %s", trap_id, meta_header[:300])
        return 200, self.schedule_reply()

    def all_done(self) -> bool:
        with self.lock:
            return self.done >= set(self.hashes)

    # ------------------------------------------------------------------ upload to the server

    def forward(self, deadline: float | None = None) -> str | None:
        """Upload every node's queue with that node's key, including nodes removed since. Returns the first error."""
        error = None
        trap_ids = {p.name for p in self.nodes_dir.glob("*") if p.is_dir()} if self.nodes_dir.exists() else set()
        for trap_id in sorted(trap_ids):
            queue, key = self.queue(trap_id), self.key_for(trap_id)
            if not queue.pending():
                continue
            if key is None:
                log.error("node %s: photos queued but no key to upload them with", trap_id)
                continue
            n, _, err = drain(queue, self.cfg["server_url"], key, self.cfg["upload"]["timeout_s"],
                              self.cfg["upload"]["max_per_cycle"], deadline=deadline)
            log.info("node %s: uploaded %d, %d still queued%s", trap_id, n, len(queue.pending()), f" ({err})" if err else "")
            error = error or (f"node {trap_id}: {err}" if err else None)
        return error


def make_server(gw: Gateway, host: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def _reply(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path != "/node/v1/captures":
                return self._reply(404, {"error": "not found"})
            length = int(self.headers.get("Content-Length") or 0)
            if length > gw.hub["max_image_mb"] * 1_000_000:
                return self._reply(413, {"error": "photo too large"})
            body = self.rfile.read(length)
            self._reply(*gw.capture(self.headers.get("Authorization", ""), self.headers.get("X-Sentinel-Meta", ""), body))

        def do_GET(self):
            if self.path == "/healthz":
                return self._reply(200, {"ok": True})
            if self.path != "/node/v1/schedule":
                return self._reply(404, {"error": "not found"})
            self._reply(*gw.schedule(self.headers.get("Authorization", ""), self.headers.get("X-Sentinel-Meta", "")))

        def log_message(self, fmt, *args):
            log.debug("%s %s", self.address_string(), fmt % args)

    server = ThreadingHTTPServer((host, port), Handler)
    server.timeout = 1
    return server


def serve_window(gw: Gateway, until: float) -> None:
    """Take node photos until time.monotonic() passes `until` or every node has checked in."""
    gw.refresh_nodes()
    if not gw.hashes:
        log.info("no ESP32 traps use this hub yet")
        return
    try:
        server = make_server(gw, gw.hub["listen"], gw.hub["port"])
    except OSError as e:
        log.error("gateway could not listen on port %s: %s", gw.hub["port"], e)
        return
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.5}, daemon=True)
    thread.start()
    log.info("gateway open on port %d for %s", gw.hub["port"], ", ".join(sorted(gw.hashes)))
    try:
        while time.monotonic() < until and not gw.all_done():
            time.sleep(0.5)
    finally:
        server.shutdown()
        server.server_close()
    missing = sorted(set(gw.hashes) - gw.done)
    log.info("gateway closed; %s", f"no word from {', '.join(missing)}" if missing else "every node checked in")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=None, help="config.toml (default /etc/sentinel/config.toml)")
    ap.add_argument("--forward-every", type=float, default=0, help="also upload node photos every N seconds (0: never)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = config_mod.load(args.config)
    if not cfg["api_key"]:  # an empty or unreadable config would otherwise run as trap T0 against localhost
        ap.error(f"{args.config or config_mod.DEFAULT_CONFIG_PATH} has no api_key: it needs the hub trap's trap_id, api_key and server_url")
    gw = Gateway(cfg, Path(cfg["data_dir"]))
    gw.refresh_nodes()
    server = make_server(gw, cfg["hub"]["listen"], cfg["hub"]["port"])
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("gateway listening on %s:%d for %s", cfg["hub"]["listen"], cfg["hub"]["port"], ", ".join(sorted(gw.hashes)) or "no nodes yet")
    try:
        while True:
            time.sleep(args.forward_every or 60)
            gw.refresh_nodes()  # picks up cameras added on the dashboard
            if args.forward_every:
                gw.forward()
    except KeyboardInterrupt:
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
