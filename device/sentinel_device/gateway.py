"""Hub for ESP32 camera traps: take their photos over the orchard Wi-Fi and relay them to the server.

One Pi in the orchard is the hub. ESP32 traps in Wi-Fi range wake on the hub's schedule, photograph
their liner, POST the JPEG here, get back the time and how long to sleep, and deep-sleep again.
Each ESP32 is its own trap on the server with its own API key; the hub keeps a queue per trap
(data_dir/nodes/<trap_id>/) and uploads it with that trap's key, so the server needs no changes.

The hub is a Pi with no camera on mains power, and runs this standalone and always on
(systemd/sentinel-gateway.service, installed by install-hub.sh):

    sentinel-gateway --config /etc/sentinel/config.toml --forward-every 30

A Pi camera trap can be a hub too: its cycle (cycle.py) keeps the gateway open for [hub] window_s each wake.

Node protocol (all requests carry "Authorization: Bearer <that trap's server API key>"):

    POST /node/v1/captures   body: the JPEG; header X-Sentinel-Meta: JSON with node_capture_id
                             (random hex, the same on every retry), captured_at + clock_synced, or
                             age_s, new_card, camera, device
    GET  /node/v1/schedule   last call of a wake; marks the node done for this window
    POST /node/v1/preview    header X-Sentinel-Meta: {"url": "http://<node ip>/", "seconds": n}: the node is
                             streaming a live preview for setting it up, listed on the hub's page (GET /)
    GET  /node/v1/firmware   the firmware the dashboard sent this node (the "firmware" in a reply), as a file

All reply with {"now": unix seconds, "sleep_s": seconds until the node's next wake, "wakes": the next
12 wake times in unix seconds, "checkin_s": how often to check in between photos (0: don't),
"photo_now": true when a photo was asked for on the dashboard and this node hasn't sent one since,
and "firmware": {"version", "size", "md5", "sig"} when the dashboard sent it firmware to install; the node
installs it only if "sig" checks out against the signing key built into it}.

A node with no trap id or key yet (a new camera, firmware 0.4.0 or later) pairs instead, with no key:

    POST /node/v1/pair       header X-Sentinel-Meta: {"code": last 6 hex digits of its MAC, "proof": that it
                             has the secret on its sticker (sentinel_server.fleet.pairing_proof), "fw", "rssi"}
                             202 {"waiting": true} until it is added on the dashboard, then
                             200 {"trap_id", "nonce", "box", "tag"}: its key sealed with that secret, which
                             only the camera can open. The hub never has the plain key until the camera uses it.

The hub's own trap id and key come from its config, or, for a hub set up with a pairing code
(install-hub.sh with no arguments), from the server once that code is entered on the dashboard
(kept in data_dir/identity.json).
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import os
import re
import secrets
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests

from . import config as config_mod
from .schedule import next_wake
from .uploader import Queue, drain

log = logging.getLogger(__name__)

NODE_ID = re.compile(r"[0-9a-fA-F]{8,32}")
PREVIEW_URL = re.compile(r"http://[0-9.]{7,15}(:[0-9]{1,5})?/")
TRAP_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")
CAMERA_CODE = re.compile(r"[0-9A-F]{6}")
PROOF = re.compile(r"[0-9a-f]{32}")
SEALED = {"key_hash": re.compile(r"[0-9a-f]{64}"), "nonce": re.compile(r"[0-9a-f]{32}"),
          "box": re.compile(r"(?:[0-9a-f]{2}){8,64}"), "tag": re.compile(r"[0-9a-f]{32}")}
SIG = re.compile(r"(?:[0-9a-f]{2}){0,72}")  # ECDSA P-256 signature, DER, in hex ("" from older servers)
FW_VERSION = re.compile(r"[0-9A-Za-z._-]{1,32}")
WAITING_FOR = 600  # a pairing camera not heard from for this long is no longer reported as waiting


def _sealed(a: object) -> dict | None:
    """A sealed key from the server (sentinel_server.fleet.hub_pairing), checked for shape, or None."""
    if not isinstance(a, dict) or not TRAP_ID.fullmatch(str(a.get("trap_id"))):
        return None
    if not all(pat.fullmatch(str(a.get(k, ""))) for k, pat in SEALED.items()):
        return None
    return {"trap_id": a["trap_id"], **{k: a[k] for k in SEALED}}


def hash_key(key: str) -> str:
    """The server's key hash (sentinel_server.services.hash_key)."""
    return hashlib.sha256(key.encode()).hexdigest()


# The soonest wake a camera is sent. The hub's own 2-minute boot margin made a check-in at 09:59:10 skip the
# 10:01 photo. The node drops wakes under 60 s away itself (untilNextWake in main.cpp), so this matches it.
NODE_MIN_GAP = timedelta(seconds=60)


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
        self.done: set[str] = set()  # nodes that asked for their schedule since the window opened
        self.requests: dict[str, datetime] = {}  # photo asked for on the dashboard: trap_id -> when (from the server)
        self.served: dict[str, datetime] = {}    # requests a node has already sent a newer photo for
        self.previews: dict[str, tuple[str, float]] = {}  # trap_id -> (live preview url, until clock())
        self.firmware_dir = data_dir / "firmware"
        self.firmware: dict[str, dict] = {}  # trap_id -> {version, size, md5}, for firmware this hub has a copy of
        self.waiting: dict[str, dict] = {}   # pairing cameras: code -> {fw, rssi, seen (clock())}
        self.pairing_file = data_dir / "pairing.json"
        try:  # code -> {trap_id, key_hash, nonce, box, tag, handed}: sealed keys for cameras that paired here
            self.assigned: dict[str, dict] = {c: a for c, a in json.loads(self.pairing_file.read_text()).items()
                                              if _sealed(a) is not None}  # not plain keys from older hubs
        except (OSError, ValueError, AttributeError):
            self.assigned = {}
        self.lock = threading.RLock()
        self._set_nodes(server)

    def _set_nodes(self, server: dict[str, str] | None = None) -> None:
        if server is not None:
            self.server_nodes = {t: h for t, h in server.items() if TRAP_ID.fullmatch(t) and isinstance(h, str)}
        hashes = dict(self.server_nodes)
        hashes.update({t: hash_key(k) for t, k in self.local_keys.items()})
        # A camera just added on the dashboard can use its key before the next node list lists it.
        hashes.update({a["trap_id"]: a["key_hash"] for a in self.assigned.values()})
        self.hashes = hashes

    def refresh_nodes(self) -> bool:
        """Ask the server which ESP32 traps upload through this hub. Keeps the cached list if it can't."""
        try:
            r = requests.get(f"{self.cfg['server_url'].rstrip('/')}/api/v1/hub/nodes", timeout=5,
                             headers={"Authorization": f"Bearer {self.cfg['api_key']}"})
            r.raise_for_status()
            nodes = r.json()["nodes"]
            assert isinstance(nodes, dict)
            asked = {t: datetime.fromisoformat(w).astimezone(UTC)
                     for t, w in (r.json().get("photo_requests") or {}).items()}
            firmware = r.json().get("firmware") or {}
            assert isinstance(firmware, dict)
        except (requests.RequestException, ValueError, KeyError, AssertionError, TypeError, AttributeError) as e:
            log.warning("node list not refreshed (%s); using the last one: %s", e.__class__.__name__, ", ".join(self.hashes) or "none")
            return False
        tmp = self.cache.with_suffix(".tmp")
        tmp.write_text(json.dumps(nodes))
        os.replace(tmp, self.cache)
        before = set(self.hashes)
        self._set_nodes(nodes)
        with self.lock:
            new = sorted(t for t, w in asked.items() if self.requests.get(t) != w)
            self.requests = asked
            self.served = {t: w for t, w in self.served.items() if asked.get(t) == w}
        if new:
            log.info("photo asked for on the dashboard: %s", ", ".join(new))
        if set(self.hashes) != before:
            log.info("nodes for this hub: %s", ", ".join(sorted(self.hashes)) or "none")
        self._fetch_firmware(firmware)
        self.sync_pairing()
        return True

    # ------------------------------------------------------------------ firmware for the cameras

    def _fetch_firmware(self, wanted: dict) -> None:
        """Keep a copy of each firmware the dashboard sent this hub's cameras, and offer it only once it is here
        and checks out, so a camera never starts an update the hub can't finish."""
        ready = {}
        for trap_id, fw in wanted.items():
            try:
                version, size, md5 = str(fw["version"]), int(fw["size"]), str(fw["md5"])
                assert FW_VERSION.fullmatch(version) and TRAP_ID.fullmatch(trap_id)
            except (KeyError, TypeError, ValueError, AssertionError):
                continue
            path = self.firmware_dir / f"{version}.bin"
            if not path.exists():
                try:
                    r = requests.get(f"{self.cfg['server_url'].rstrip('/')}/api/v1/hub/firmware/{version}", timeout=60,
                                     headers={"Authorization": f"Bearer {self.cfg['api_key']}"})
                    r.raise_for_status()
                except requests.RequestException as e:
                    log.warning("firmware %s not fetched: %s", version, e.__class__.__name__)
                    continue
                if len(r.content) != size or hashlib.md5(r.content, usedforsecurity=False).hexdigest() != md5:
                    log.error("firmware %s from the server doesn't match its size and md5", version)
                    continue
                self.firmware_dir.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".part")
                tmp.write_bytes(r.content)
                os.replace(tmp, path)
                log.info("firmware %s fetched (%d kB)", version, size // 1000)
            sig = str(fw.get("sig", ""))
            ready[trap_id] = {"version": version, "size": size, "md5": md5, "sig": sig if SIG.fullmatch(sig) else ""}
        with self.lock:
            new = sorted(f"{t} -> {f['version']}" for t, f in ready.items() if self.firmware.get(t) != f)
            self.firmware = ready
        if new:
            log.info("firmware to offer: %s", ", ".join(new))

    def firmware_file(self, authorization: str) -> tuple[int, Path | dict]:
        trap_id = self.trap_for(authorization)
        if trap_id is None:
            return 401, {"error": "unknown or missing trap API key"}
        with self.lock:
            fw = self.firmware.get(trap_id)
        if fw is None:
            return 404, {"error": "no firmware for this node"}
        log.info("node %s: sending firmware %s", trap_id, fw["version"])
        return 200, self.firmware_dir / f"{fw['version']}.bin"

    # ------------------------------------------------------------------ cameras pairing

    def pair(self, meta_header: str) -> tuple[int, dict]:
        """A camera with no trap id or key yet. Reported to the server as waiting until it is added on the
        dashboard; then it gets its trap id and key here."""
        try:
            meta = json.loads(meta_header or "{}")
            code, proof = str(meta["code"]).upper(), str(meta["proof"])
            assert CAMERA_CODE.fullmatch(code) and PROOF.fullmatch(proof)
        except (ValueError, KeyError, TypeError, AttributeError, AssertionError):
            return 422, {"error": 'meta must be {"code": "<6 hex digits>", "proof": "<32 hex digits>", "fw", "rssi"}'}
        with self.lock:
            got = self.assigned.get(code)
            if got:  # sealed: only the camera with the sticker's secret can open it, so it can go to whoever asks
                log.info("camera %s: sending it its sealed key, as %s", code, got["trap_id"])
                return 200, {**self.schedule_reply(got["trap_id"]), "trap_id": got["trap_id"],
                             "nonce": got["nonce"], "box": got["box"], "tag": got["tag"]}
            fw = str(meta.get("fw", ""))
            if code not in self.waiting:
                log.info("camera %s is asking to be added (fw %s)", code, fw)
            self.waiting[code] = {"fw": fw if FW_VERSION.fullmatch(fw) else "", "proof": proof,
                                  "rssi": meta.get("rssi") if isinstance(meta.get("rssi"), int) else None,
                                  "seen": self.clock()}
        return 202, {**self.schedule_reply(), "waiting": True}

    def _save_pairing(self) -> None:
        tmp = self.pairing_file.with_suffix(".tmp")
        tmp.touch(mode=0o600)
        tmp.write_text(json.dumps(self.assigned))
        os.replace(tmp, self.pairing_file)

    def sync_pairing(self) -> None:
        """Tell the server which cameras are waiting and which have their key; get keys for ones added since."""
        now = self.clock()
        with self.lock:
            self.waiting = {c: w for c, w in self.waiting.items() if now - w["seen"] < WAITING_FOR}
            waiting = [{"code": c, "proof": w["proof"], "fw": w["fw"], "rssi": w["rssi"]} for c, w in self.waiting.items()]
            handed = [c for c, a in self.assigned.items() if a.get("handed")]
        if not waiting and not handed and not self.assigned:
            return
        try:
            r = requests.post(f"{self.cfg['server_url'].rstrip('/')}/api/v1/hub/pairing", timeout=10,
                              json={"waiting": waiting, "handed": handed},
                              headers={"Authorization": f"Bearer {self.cfg['api_key']}"})
            r.raise_for_status()
            assigned = r.json()["assigned"]
            assert isinstance(assigned, dict)
        except (requests.RequestException, ValueError, KeyError, AssertionError) as e:
            log.warning("pairing not synced: %s", e.__class__.__name__)
            return
        with self.lock:
            # The server lists a key until told it was handed over, or until the camera is removed or given
            # another key, so one it no longer lists is done either way.
            kept = {c: a for c, a in self.assigned.items() if c in assigned}
            for code, a in assigned.items():
                sealed = _sealed(a)
                if CAMERA_CODE.fullmatch(code) and sealed is not None and code not in kept:
                    kept[code] = {**sealed, "handed": False}
                    self.waiting.pop(code, None)
                    log.info("camera %s was added on the dashboard as %s", code, a["trap_id"])
            changed = kept != self.assigned
            self.assigned = kept
            if changed:
                self._save_pairing()
        self._set_nodes()

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
        if found:
            with self.lock:
                for code, a in self.assigned.items():
                    if a["trap_id"] == found and not a.get("handed"):
                        a["handed"] = True
                        self._save_pairing()
                        log.info("camera %s is using its key, as %s", code, found)
        return found

    def photo_wanted(self, trap_id: str | None) -> bool:
        if not trap_id:
            return False
        with self.lock:
            asked = self.requests.get(trap_id)
            return asked is not None and self.served.get(trap_id) != asked

    def schedule_reply(self, trap_id: str | None = None) -> dict:
        now = datetime.fromtimestamp(self.clock(), UTC)
        offset = timedelta(seconds=self.hub["node_offset_s"])
        # The node wakes node_offset_s after the hub's slot, once the hub has booted and opened the window.
        wakes, t = [], now - offset
        for _ in range(12):  # a node that misses a window still knows when to wake after that
            t = next_wake(t, self.cfg["schedule"]["times"], self.cfg["timezone"], min_gap=NODE_MIN_GAP)
            wakes.append(t + offset)
        reply = {"now": now.timestamp(), "next_wake": wakes[0].isoformat(), "sleep_s": round((wakes[0] - now).total_seconds()),
                 "wakes": [round(w.timestamp()) for w in wakes], "checkin_s": round(float(self.hub["checkin_min"]) * 60),
                 "photo_now": self.photo_wanted(trap_id)}
        with self.lock:
            fw = self.firmware.get(trap_id) if trap_id else None
        if fw:
            reply["firmware"] = fw
        return reply

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

        now = datetime.fromtimestamp(self.clock(), UTC)
        try:
            if meta.get("clock_synced") and meta.get("captured_at"):
                captured = datetime.fromisoformat(meta["captured_at"]).astimezone(UTC)
            else:  # the node has never been told the time: it says how long ago it took the photo
                captured = now - timedelta(seconds=float(meta.get("age_s", 0)))
        except (ValueError, TypeError):
            return 422, {"error": "bad captured_at or age_s"}

        queue = self.queue(trap_id)
        uid = None
        with self.lock:
            # A photo taken after the dashboard's request answers it, and so does the one the node took because
            # it was asked, even if its clock runs behind (judged by time alone, it would be asked again and again).
            if self.requests.get(trap_id) is not None and (
                    captured >= self.requests[trap_id] or meta.get("wake_reason") == "requested"):
                self.served[trap_id] = self.requests[trap_id]
            # A retry after a lost reply: same node_capture_id, already queued or already sent.
            if not any(any(d.glob(f"*_{node_id}.jpg")) for d in (queue.queue_dir, queue.sent_dir)):
                uid = f"{captured.strftime('%Y%m%dT%H%M%SZ')}_{trap_id}_{node_id}"
                meta.update(capture_uid=uid, trap_id=trap_id, captured_at=captured.isoformat(),
                            wake_reason=meta.get("wake_reason", "scheduled"),
                            hub={"received_at": now.isoformat(), "hub_trap_id": self.cfg["trap_id"]})
                tmp = queue.queue_dir / f".{uid}.part"
                tmp.write_bytes(body)
                queue.add(tmp.rename(tmp.with_name(f"{uid}.jpg")), meta)
        if uid is None:
            return 200, {**self.schedule_reply(trap_id), "duplicate": True}
        log.info("node %s: queued %s (%d kB)", trap_id, uid, len(body) // 1000)
        return 201, {**self.schedule_reply(trap_id), "uid": uid}

    def schedule(self, authorization: str, meta_header: str = "") -> tuple[int, dict]:
        trap_id = self.trap_for(authorization)
        if trap_id is None:
            return 401, {"error": "unknown or missing trap API key"}
        with self.lock:
            self.done.add(trap_id)
        if meta_header:
            log.info("node %s status: %s", trap_id, meta_header[:600])
            self._save_status(trap_id, meta_header)
        return 200, self.schedule_reply(trap_id)

    def _save_status(self, trap_id: str, meta_header: str) -> None:
        """Keep each node's end-of-wake status (awake time, signal, errors) in data_dir/nodes/<trap_id>/status.jsonl."""
        try:
            status = json.loads(meta_header)
            assert isinstance(status, dict)
        except (ValueError, AssertionError):
            return
        status = {"at": datetime.fromtimestamp(self.clock(), UTC).isoformat(), **status}
        path = self.nodes_dir / trap_id / "status.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock, path.open("a") as f:
            f.write(json.dumps(status) + "\n")

    def preview(self, authorization: str, meta_header: str) -> tuple[int, dict]:
        """A node in setup mode streams a live preview; list it on the hub's page while it lasts."""
        trap_id = self.trap_for(authorization)
        if trap_id is None:
            return 401, {"error": "unknown or missing trap API key"}
        try:
            meta = json.loads(meta_header or "{}")
            url, seconds = str(meta["url"]), float(meta["seconds"])
            assert PREVIEW_URL.fullmatch(url) and 0 < seconds <= 3600
        except (ValueError, KeyError, TypeError, AssertionError):
            return 422, {"error": 'meta must be {"url": "http://<ip>/", "seconds": 1-3600}'}
        with self.lock:
            self.previews[trap_id] = (url, self.clock() + seconds)
        log.info("node %s: live preview at %s for %.0f s", trap_id, url, seconds)
        return 200, self.schedule_reply(trap_id)

    def status_page(self) -> str:
        """The hub's own page (GET /): each camera, and a link to any live preview. Open it on a phone on
        the hub's Wi-Fi while setting a camera up."""
        now = self.clock()
        with self.lock:
            previews = {t: u for t, (u, until) in self.previews.items() if until > now}
            asked = {t for t in self.requests if self.served.get(t) != self.requests[t]}
            waiting = sorted(c for c, w in self.waiting.items() if now - w["seen"] < WAITING_FOR)
            updating = {t: f["version"] for t, f in self.firmware.items()}
        rows = []
        for c in waiting:
            rows.append(f"<li><b>New camera {html.escape(c)}</b> · waiting to be added on the dashboard (Set up traps)</li>")
        for t in sorted(set(self.hashes) | set(previews)):
            cells = [f"<b>{html.escape(t)}</b>"]
            if t in previews:
                cells.append(f'<a href="{html.escape(previews[t])}">live preview</a>')
            if t in asked:
                cells.append("photo asked for")
            if t in updating:
                cells.append(f"firmware {html.escape(updating[t])} waiting for it")
            rows.append("<li>" + " · ".join(cells) + "</li>")
        return ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                "<meta http-equiv=refresh content=10><title>Hub " + html.escape(self.cfg["trap_id"]) + "</title>"
                "<body style='font:16px system-ui;margin:16px'><h1>Hub " + html.escape(self.cfg["trap_id"]) + "</h1>"
                "<p>Cameras on this hub. A camera streams a live preview for a few minutes after it is powered on, "
                "or after its BOOT button is held for 3 s.</p><ul>" + ("".join(rows) or "<li>No cameras yet</li>") + "</ul>")

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


def make_server(gw: Gateway, host: str, port: int, socket_timeout: float = 60) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        # A node that gives up mid-upload (or sleeps) never closes its connection: without a socket timeout
        # the thread waits on its body for good (11 of them on Oct 22 2026).
        timeout = socket_timeout

        def _reply(self, status: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.path == "/node/v1/pair":
                return self._reply(*gw.pair(self.headers.get("X-Sentinel-Meta", "")))
            if self.path == "/node/v1/preview":
                return self._reply(*gw.preview(self.headers.get("Authorization", ""), self.headers.get("X-Sentinel-Meta", "")))
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
            if self.path == "/":
                data = gw.status_page().encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                return self.wfile.write(data)
            if self.path == "/node/v1/firmware":
                status, got = gw.firmware_file(self.headers.get("Authorization", ""))
                if status != 200:
                    return self._reply(status, got)
                data = got.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                return self.wfile.write(data)
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


def load_identity(cfg: dict, data_dir: Path) -> bool:
    """The hub's trap id and key: from its config, else from data_dir/identity.json (got with its pairing code)."""
    if cfg["api_key"]:
        return True
    try:
        ident = json.loads((data_dir / "identity.json").read_text())
        assert TRAP_ID.fullmatch(ident["trap_id"]) and ident["api_key"]
    except (OSError, ValueError, KeyError, TypeError, AssertionError):
        return False
    cfg.update(trap_id=ident["trap_id"], api_key=ident["api_key"])
    return True


def claim(cfg: dict, data_dir: Path, code: str, sleep=time.sleep, every: float = 30) -> None:
    """Ask the server with the pairing code until the hub is added on the dashboard with it, then keep the
    trap id and key it sends in data_dir/identity.json."""
    url = f"{cfg['server_url'].rstrip('/')}/api/v1/hub/claim"
    log.info("waiting to be added on the dashboard (Set up traps) with pairing code %s-%s", code[:4], code[4:])
    tries = 0
    while True:
        try:
            r = requests.post(url, json={"code": code}, timeout=10)
            if r.status_code == 200:
                ident = r.json()
                assert TRAP_ID.fullmatch(ident["trap_id"]) and ident["api_key"]
                path = data_dir / "identity.json"
                tmp = path.with_suffix(".tmp")
                tmp.touch(mode=0o600)
                tmp.write_text(json.dumps({"trap_id": ident["trap_id"], "api_key": ident["api_key"]}))
                os.replace(tmp, path)
                cfg.update(trap_id=ident["trap_id"], api_key=ident["api_key"])
                log.info("added on the dashboard as hub %s", ident["trap_id"])
                return
            if r.status_code != 404:
                log.warning("server answered the pairing code with %s", r.status_code)
        except (requests.RequestException, ValueError, KeyError, TypeError, AssertionError) as e:
            if tries % 20 == 0:
                log.warning("server not reached for pairing (%s): is %s right?", e.__class__.__name__, cfg["server_url"])
        tries += 1
        sleep(every)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=None, help="config.toml (default /etc/sentinel/config.toml)")
    ap.add_argument("--forward-every", type=float, default=0, help="also upload node photos every N seconds (0: never)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = config_mod.load(args.config)
    data_dir = Path(cfg["data_dir"])
    if not load_identity(cfg, data_dir):
        code_file = data_dir / "claim_code"
        if not code_file.exists():  # an empty or unreadable config would otherwise run as trap T0 against localhost
            ap.error(f"{args.config or config_mod.DEFAULT_CONFIG_PATH} has no api_key and there is no {code_file}: "
                     "run install-hub.sh with no arguments for a pairing code, or put the hub's trap_id and api_key in the config")
        claim(cfg, data_dir, code_file.read_text().strip())
    gw = Gateway(cfg, data_dir)
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
