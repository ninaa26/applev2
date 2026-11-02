"""Hub side of the 900 MHz radio link: cameras out of the hub's Wi-Fi send their requests by radio.

An ESP32 with an SX1262 radio (device/esp32-radio-bridge) sits on the hub Pi's USB as a plain modem: it passes
every frame it hears to the Pi and transmits what the Pi gives it. This program reads those frames, puts each
camera's request back together, replays it to the gateway on localhost (the same POST /node/v1/captures,
GET /node/v1/schedule, POST /node/v1/pair and GET /node/v1/firmware a camera on Wi-Fi makes, so the gateway
needs no changes), and hands the reply back in chunks as the camera asks for them. Many cameras can share
one hub: requests are kept apart by the camera's radio address and request number.

    sentinel-radio --port /dev/ttyUSB0 [--gateway http://127.0.0.1:8080]

The frame layout and the radio settings are in device/radio-common/sentinel_radio.h; the constants below
must match it.
"""

from __future__ import annotations

import argparse
import json
import logging
import struct
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import requests

log = logging.getLogger(__name__)

VERSION = 1
REQ_DATA, REQ_ACK, POLL, RESP_INFO, PULL, RESP_DATA, DONE = 1, 2, 3, 4, 5, 6, 7
HEADER = 6
CHUNK = 240
WINDOW = 32
FLAG_ACK_PLEASE = 1
FLAG_ALL_HERE = 1
WORKING, READY, UNKNOWN = 0, 1, 2

SER_RX, SER_LOG, SER_HELLO, SER_TX = 0x01, 0x02, 0x03, 0x10
SLIP_END, SLIP_ESC, SLIP_ESC_END, SLIP_ESC_ESC = 0xC0, 0xDB, 0xDC, 0xDD

# What a camera may ask for over the radio: the gateway's node API and nothing else, so this is no open proxy.
ALLOWED = {("POST", "/node/v1/captures"), ("GET", "/node/v1/schedule"), ("POST", "/node/v1/pair"),
           ("GET", "/node/v1/firmware")}
MAX_REQUEST = 8_000_000   # bytes: larger than any photo the gateway takes
RECEIVING_FOR = 120       # s: a request that stops arriving is dropped
KEEP_REPLY_FOR = 300      # s: a reply the camera never finished pulling is dropped


def crc16(data: bytes) -> int:
    """CRC-16/CCITT-FALSE, as radioCrc16 in sentinel_radio.h."""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def slip_encode(payload: bytes) -> bytes:
    out = bytearray([SLIP_END])
    for b in payload:
        if b == SLIP_END:
            out += bytes([SLIP_ESC, SLIP_ESC_END])
        elif b == SLIP_ESC:
            out += bytes([SLIP_ESC, SLIP_ESC_ESC])
        else:
            out.append(b)
    out.append(SLIP_END)
    return bytes(out)


class SlipDecoder:
    def __init__(self) -> None:
        self.buf = bytearray()
        self.esc = False

    def feed(self, data: bytes) -> list[bytes]:
        out = []
        for b in data:
            if b == SLIP_END:
                if self.buf:
                    out.append(bytes(self.buf))
                self.buf.clear()
                self.esc = False
            elif self.esc:
                self.buf.append(SLIP_END if b == SLIP_ESC_END else SLIP_ESC if b == SLIP_ESC_ESC else b)
                self.esc = False
            elif b == SLIP_ESC:
                self.esc = True
            else:
                self.buf.append(b)
        return out


def serial_message(kind: int, payload: bytes) -> bytes:
    msg = bytes([kind]) + payload
    return slip_encode(msg + struct.pack("<H", crc16(msg)))


def parse_serial(msg: bytes) -> tuple[int, bytes] | None:
    """A message from the bridge without its SLIP framing: (kind, payload), or None if it arrived damaged."""
    if len(msg) < 3 or crc16(msg[:-2]) != struct.unpack("<H", msg[-2:])[0]:
        return None
    return msg[0], msg[1:-2]


@dataclass
class Frame:
    type: int
    node: int
    xfer: int
    body: bytes


def header(type_: int, node: int, xfer: int) -> bytes:
    return struct.pack("<BIB", VERSION << 4 | type_, node, xfer)


def parse_frame(data: bytes) -> Frame | None:
    if len(data) < HEADER or data[0] >> 4 != VERSION:
        return None
    first, node, xfer = struct.unpack("<BIB", data[:HEADER])
    return Frame(first & 0x0F, node, xfer, data[HEADER:])


def encode_request(method: str, path: str, body: bytes = b"", key: str = "", meta: str = "", ctype: str = "") -> bytes:
    """A request as the camera sends it: [head length u16][head JSON][body]."""
    head: dict[str, str] = {"m": method, "p": path}
    if key:
        head["a"] = key
    if meta:
        head["x"] = meta
    if ctype:
        head["t"] = ctype
    h = json.dumps(head, separators=(",", ":")).encode()
    return struct.pack("<H", len(h)) + h + body


def decode_request(blob: bytes) -> tuple[dict, bytes]:
    (n,) = struct.unpack("<H", blob[:2])
    head = json.loads(blob[2:2 + n])
    if not isinstance(head, dict):
        raise ValueError("request head is not a JSON object")
    return head, blob[2 + n:]


def chunks_in(total: int) -> int:
    return (total + CHUNK - 1) // CHUNK


@dataclass
class Transfer:
    node: int
    xfer: int
    total: int
    started: float
    seen: float
    chunks: dict[int, bytes] = field(default_factory=dict)
    frames: int = 0             # REQ_DATA frames heard, resends included
    state: str = "receiving"    # receiving, working, ready
    status: int = 0
    reply: bytes = b""
    rssi: int = 0
    what: str = ""

    def have(self, base: int) -> int:
        bits = 0
        for i in range(WINDOW):
            if base + i in self.chunks:
                bits |= 1 << i
        return bits


# send_request(method, path, headers, body) -> (HTTP status, reply body)
Sender = Callable[[str, str, dict[str, str], bytes], tuple[int, bytes]]


class LinkServer:
    """The protocol, without the serial port: handle() takes one frame the bridge heard and returns the frames to
    transmit in answer. Requests are replayed with send_request in a thread of their own (start), so the
    cameras keep getting answers while the gateway works."""

    def __init__(self, send_request: Sender, clock: Callable[[], float] = time.monotonic,
                 start: Callable[[Callable[[], None]], None] | None = None):
        self.send_request = send_request
        self.clock = clock
        self.start = start or (lambda f: threading.Thread(target=f, daemon=True).start())
        self.transfers: dict[tuple[int, int], Transfer] = {}
        self.lock = threading.RLock()

    def handle(self, data: bytes, rssi: int = 0) -> list[bytes]:
        f = parse_frame(data)
        if f is None:
            return []
        now = self.clock()
        with self.lock:
            self.expire(now)
            if f.type == REQ_DATA:
                return self._req_data(f, rssi, now)
            t = self.transfers.get((f.node, f.xfer))
            if t is not None:
                t.seen, t.rssi = now, rssi
            if f.type == POLL:
                return [self._info(f, t)]
            if f.type == PULL and len(f.body) >= 6:
                base, want = struct.unpack("<HI", f.body[:6])
                if t is None or t.state != "ready":
                    return [self._info(f, t)]
                n = chunks_in(len(t.reply))
                return [header(RESP_DATA, f.node, f.xfer) + struct.pack("<H", base + i)
                        + t.reply[(base + i) * CHUNK:(base + i + 1) * CHUNK]
                        for i in range(WINDOW) if want >> i & 1 and base + i < n]
            if f.type == DONE and t is not None:
                del self.transfers[(f.node, f.xfer)]
        return []

    def _req_data(self, f: Frame, rssi: int, now: float) -> list[bytes]:
        if len(f.body) < 7:
            return []
        seq, total, flags = struct.unpack("<HIB", f.body[:7])
        data = f.body[7:]
        if not 0 < total <= MAX_REQUEST:
            return []
        key = (f.node, f.xfer)
        t = self.transfers.get(key)
        # A different request under the same number (the camera lost power, or never sent DONE and has
        # counted round to it again) starts over: its size or its chunks don't match.
        if t is None or (t.state != "working" and (t.total != total or t.chunks.get(seq, data) != data)):
            t = self.transfers[key] = Transfer(f.node, f.xfer, total, started=now, seen=now)
        t.seen, t.rssi = now, rssi
        if t.state == "receiving":
            n = chunks_in(total)
            expect = CHUNK if seq < n - 1 else total - (n - 1) * CHUNK
            if seq < n and len(data) == expect:
                t.frames += 1
                t.chunks.setdefault(seq, data)
            if len(t.chunks) == n:
                t.state = "working"
                self.start(lambda: self._run(t))
        if not flags & FLAG_ACK_PLEASE:
            return []
        base = seq - seq % WINDOW
        done = FLAG_ALL_HERE if t.state != "receiving" else 0
        return [header(REQ_ACK, f.node, f.xfer) + struct.pack("<HIBb", base, t.have(base), done, _i8(rssi))]

    def _info(self, f: Frame, t: Transfer | None) -> bytes:
        if t is None or t.state == "receiving":
            state, status, total = UNKNOWN, 0, 0
        elif t.state == "working":
            state, status, total = WORKING, 0, 0
        else:
            state, status, total = READY, t.status, len(t.reply)
        return header(RESP_INFO, f.node, f.xfer) + struct.pack("<BHIb", state, status, total, _i8(t.rssi if t else 0))

    def _run(self, t: Transfer) -> None:
        """Replay a whole request to the gateway and keep its reply for the camera to pull."""
        blob = b"".join(t.chunks[i] for i in range(chunks_in(t.total)))
        try:
            head, body = decode_request(blob)
            method, path = str(head.get("m", "")), str(head.get("p", ""))
            t.what = f"{method} {path}"
            if (method, path) not in ALLOWED:
                status, reply = 404, json.dumps({"error": f"{method} {path} is not a node request"}).encode()
            else:
                headers = {}
                if head.get("a"):
                    headers["Authorization"] = f"Bearer {head['a']}"
                if head.get("x"):
                    headers["X-Sentinel-Meta"] = with_hub_rssi(path, str(head["x"]), t.rssi)
                if head.get("t"):
                    headers["Content-Type"] = str(head["t"])
                status, reply = self.send_request(method, path, headers, body)
        except (ValueError, KeyError, UnicodeDecodeError, struct.error) as e:
            status, reply = 400, json.dumps({"error": f"bad request: {e}"}).encode()
            t.what = "bad request"
        except Exception as e:  # the gateway down, or anything else: the camera gets an answer either way
            log.exception("node %08x: request failed", t.node)
            status, reply = 502, json.dumps({"error": f"gateway: {e.__class__.__name__}"}).encode()
        with self.lock:
            t.status, t.reply, t.state, t.seen = status, reply, "ready", self.clock()
        n = chunks_in(t.total)
        log.info("node %08x: %s -> %d (%d kB in %.1f s, %d chunks, %d resent, %d dBm)", t.node, t.what, status,
                 t.total // 1000, self.clock() - t.started, n, max(0, t.frames - n), t.rssi)

    def expire(self, now: float) -> None:
        for key, t in list(self.transfers.items()):
            idle = now - t.seen
            if (t.state == "receiving" and idle > RECEIVING_FOR) or (t.state == "ready" and idle > KEEP_REPLY_FOR):
                del self.transfers[key]


def _i8(v: int) -> int:
    return max(-128, min(127, int(v)))


def with_hub_rssi(path: str, meta: str, rssi: int) -> str:
    """Add how strongly the hub heard the camera to what the camera reports about itself."""
    try:
        m = json.loads(meta)
    except ValueError:
        return meta
    if not isinstance(m, dict):
        return meta
    if path == "/node/v1/captures":
        m.setdefault("device", {})
        if isinstance(m["device"], dict):
            m["device"].update(link="radio", hub_rssi=rssi)
    elif path == "/node/v1/schedule":
        m.update(link="radio", hub_rssi=rssi)
    return json.dumps(m)


def http_sender(base_url: str, timeout: float = 60) -> Sender:
    """Replay requests to the gateway at base_url."""
    session = requests.Session()

    def send(method: str, path: str, headers: dict[str, str], body: bytes) -> tuple[int, bytes]:
        r = session.request(method, base_url.rstrip("/") + path, headers=headers, data=body or None, timeout=timeout)
        return r.status_code, r.content
    return send


class Bridge:
    """The serial port to the radio bridge: frames it heard go to the LinkServer, its answers go back out."""

    def __init__(self, port, server: LinkServer):
        self.port = port  # read(n) with a short timeout, write(data)
        self.server = server
        self.decoder = SlipDecoder()

    def poll(self) -> None:
        data = self.port.read(max(1, getattr(self.port, "in_waiting", 0)))  # all that's there, or wait for one byte
        if not data:
            with self.server.lock:
                self.server.expire(self.server.clock())
            return
        for msg in self.decoder.feed(data):
            got = parse_serial(msg)
            if got is None:
                log.debug("damaged message from the bridge")
                continue
            kind, payload = got
            if kind == SER_RX and payload:
                for frame in self.server.handle(payload[1:], struct.unpack("<b", payload[:1])[0]):
                    self.port.write(serial_message(SER_TX, frame))
            elif kind == SER_LOG:
                log.info("bridge: %s", payload.decode(errors="replace"))
            elif kind == SER_HELLO and payload:
                if payload[0] != VERSION:
                    log.error("bridge speaks radio protocol %d, this program %d: reflash one of them", payload[0], VERSION)
                log.info("bridge ready: %s", payload[1:].decode(errors="replace"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", required=True, help="the radio bridge's serial port, e.g. /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=460800, help="as BRIDGE_BAUD in sentinel_radio.h")
    ap.add_argument("--gateway", default="http://127.0.0.1:8080", help="where sentinel-gateway listens")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    import serial  # pyserial: only the hub with a radio needs it

    server = LinkServer(http_sender(args.gateway))
    while True:  # the bridge can be unplugged or reset: keep coming back
        try:
            with serial.Serial(args.port, args.baud, timeout=0.05) as port:
                log.info("listening on %s for cameras, replaying to %s", args.port, args.gateway)
                bridge = Bridge(port, server)
                while True:
                    bridge.poll()
        except serial.SerialException as e:
            log.warning("bridge on %s: %s; trying again in 5 s", args.port, e)
            time.sleep(5)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    sys.exit(main())
