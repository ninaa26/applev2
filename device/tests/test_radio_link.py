import json
import random
import struct
import threading
from datetime import UTC, datetime
from pathlib import Path

from sentinel_device import config as config_mod, gateway, radio_link as rl

JPEG = b"\xff\xd8" + bytes(range(256)) * 600 + b"\xff\xd9"  # 153.6 kB, every byte value (SLIP's included)
NOW = datetime(2026, 10, 5, 23, 31, 30, tzinfo=UTC).timestamp()


class Camera:
    """The camera's side of the link, as esp32-node/src/radio_link.cpp does it, over a lossy channel."""

    def __init__(self, server: rl.LinkServer, node: int = 0x1A2B3C4D, loss: float = 0.0, seed: int = 1):
        self.server, self.node, self.loss = server, node, loss
        self.rng = random.Random(seed)
        self.xfer = 7
        self.sent = 0

    def _send(self, frame: bytes) -> list[rl.Frame]:
        self.sent += 1
        if self.rng.random() < self.loss:
            return []  # lost on the way to the hub
        got = [rl.parse_frame(r) for r in self.server.handle(frame, rssi=-81)]
        return [f for f in got if f is not None and self.rng.random() >= self.loss]

    def request(self, method: str, path: str, body: bytes = b"", key: str = "", meta: str = "",
                ctype: str = "", max_tries: int = 40) -> tuple[int, bytes]:
        blob = rl.encode_request(method, path, body, key, meta, ctype)
        self.xfer = (self.xfer + 1) & 0xFF
        x, total, n = self.xfer, len(blob), rl.chunks_in(len(blob))
        all_here = False
        for base in range(0, n, rl.WINDOW):
            if all_here:
                break
            missing = list(range(base, min(base + rl.WINDOW, n)))
            resend, tries = missing, 0
            while missing:
                ack = None
                for seq in resend:
                    flags = rl.FLAG_ACK_PLEASE if seq == resend[-1] else 0
                    frame = (rl.header(rl.REQ_DATA, self.node, x) + struct.pack("<HIB", seq, total, flags)
                             + blob[seq * rl.CHUNK:(seq + 1) * rl.CHUNK])
                    for f in self._send(frame):
                        if f.type == rl.REQ_ACK and f.node == self.node and f.xfer == x:
                            ack = struct.unpack("<HIBb", f.body[:8])
                if ack is None:  # the ack, or the window's last frame, was lost: ask again with the last frame
                    tries += 1
                    assert tries < max_tries, "hub stopped answering"
                    resend = missing[-1:]
                    continue
                ack_base, have, flags, _ = ack
                if flags & rl.FLAG_ALL_HERE:
                    all_here = True
                    break
                missing = [s for s in missing if not have >> (s - ack_base) & 1]
                resend = missing
        for _ in range(max_tries):
            info = [f for f in self._send(rl.header(rl.POLL, self.node, x)) if f.type == rl.RESP_INFO]
            if info and info[0].body[0] == rl.READY:
                _, status, size, _ = struct.unpack("<BHIb", info[0].body[:8])
                break
            assert not info or info[0].body[0] != rl.UNKNOWN, "hub lost the request"
        else:
            raise AssertionError("no reply")
        reply = bytearray(size)
        n = rl.chunks_in(size)
        for base in range(0, n, rl.WINDOW):
            missing = {s for s in range(base, min(base + rl.WINDOW, n))}
            for _ in range(max_tries):
                if not missing:
                    break
                want = sum(1 << (s - base) for s in missing)
                for f in self._send(rl.header(rl.PULL, self.node, x) + struct.pack("<HI", base, want)):
                    if f.type == rl.RESP_DATA:
                        (seq,) = struct.unpack("<H", f.body[:2])
                        reply[seq * rl.CHUNK:seq * rl.CHUNK + len(f.body) - 2] = f.body[2:]
                        missing.discard(seq)
            assert not missing, "reply chunks never arrived"
        self._send(rl.header(rl.DONE, self.node, x))
        return status, bytes(reply)


class Recorder:
    def __init__(self, status=201, reply=b'{"ok": true}'):
        self.calls: list[tuple[str, str, dict, bytes]] = []
        self.status, self.reply = status, reply

    def __call__(self, method, path, headers, body):
        self.calls.append((method, path, headers, body))
        return self.status, self.reply


def _server(sender) -> rl.LinkServer:
    return rl.LinkServer(sender, clock=lambda: 0.0, start=lambda f: f())


def test_a_photo_goes_through_the_radio_whole():
    rec = Recorder()
    status, reply = Camera(_server(rec)).request("POST", "/node/v1/captures", JPEG, key="key2",
                                                 meta='{"node_capture_id": "a1b2c3d4", "device": {"rssi": -70}}',
                                                 ctype="image/jpeg")
    assert (status, reply) == (201, b'{"ok": true}')
    [(method, path, headers, body)] = rec.calls
    assert (method, path, body) == ("POST", "/node/v1/captures", JPEG)
    assert headers["Authorization"] == "Bearer key2" and headers["Content-Type"] == "image/jpeg"
    meta = json.loads(headers["X-Sentinel-Meta"])
    assert meta["device"] == {"rssi": -70, "link": "radio", "hub_rssi": -81}


def test_lost_frames_both_ways_are_sent_again():
    rec = Recorder(status=200, reply=bytes(range(256)) * 200)  # a 51 kB reply, like a slice of firmware
    cam = Camera(_server(rec), loss=0.2, seed=3)
    status, reply = cam.request("POST", "/node/v1/captures", JPEG, key="key2", meta="{}")
    assert status == 200 and reply == rec.reply
    assert rec.calls[0][3] == JPEG and len(rec.calls) == 1  # replayed once, however often its chunks came
    assert cam.sent > rl.chunks_in(len(JPEG)) + rl.chunks_in(len(reply))  # some were resent


def test_an_empty_reply_and_a_get_without_body():
    rec = Recorder(status=200, reply=b"")
    assert Camera(_server(rec)).request("GET", "/node/v1/schedule", key="k", meta='{"rssi": -90}') == (200, b"")
    assert json.loads(rec.calls[0][2]["X-Sentinel-Meta"]) == {"rssi": -90, "link": "radio", "hub_rssi": -81}


def test_only_node_requests_are_replayed():
    rec = Recorder()
    status, reply = Camera(_server(rec)).request("GET", "/", key="k")
    assert status == 404 and b"not a node request" in reply and rec.calls == []


def test_the_gateway_down_is_a_502_not_silence():
    def down(*_):
        raise ConnectionError("refused")
    status, reply = Camera(_server(down)).request("GET", "/node/v1/schedule", key="k")
    assert status == 502 and b"ConnectionError" in reply


def test_two_cameras_interleaved_stay_apart():
    rec = Recorder()
    server = _server(rec)
    a, b = Camera(server, node=0xA), Camera(server, node=0xB)
    blob = rl.encode_request("POST", "/node/v1/captures", b"\xff\xd8A" * 4000 + b"\xff\xd9", key="ka")
    # A sends its first window, then B a whole request (same request number), then A the rest.
    a.xfer = b.xfer = 8
    for seq in range(rl.WINDOW):
        server.handle(rl.header(rl.REQ_DATA, 0xA, 9) + struct.pack("<HIB", seq, len(blob), 0)
                      + blob[seq * rl.CHUNK:(seq + 1) * rl.CHUNK])
    assert b.request("POST", "/node/v1/captures", b"\xff\xd8B\xff\xd9", key="kb")[0] == 201
    for seq in range(rl.WINDOW, rl.chunks_in(len(blob))):
        server.handle(rl.header(rl.REQ_DATA, 0xA, 9) + struct.pack("<HIB", seq, len(blob), 0)
                      + blob[seq * rl.CHUNK:(seq + 1) * rl.CHUNK])
    assert [c[3][:3] for c in rec.calls] == [b"\xff\xd8B", b"\xff\xd8A"]
    assert rec.calls[1][3] == b"\xff\xd8A" * 4000 + b"\xff\xd9"


def test_poll_for_a_request_the_hub_never_had():
    server = _server(Recorder())
    [info] = server.handle(rl.header(rl.POLL, 5, 1))
    assert rl.parse_frame(info).body[0] == rl.UNKNOWN


def test_requests_that_stop_arriving_are_dropped():
    t = [0.0]
    server = rl.LinkServer(Recorder(), clock=lambda: t[0], start=lambda f: f())
    server.handle(rl.header(rl.REQ_DATA, 5, 1) + struct.pack("<HIB", 0, 1000, 0) + b"x" * rl.CHUNK)
    assert (5, 1) in server.transfers
    t[0] = rl.RECEIVING_FOR + 1
    server.handle(rl.header(rl.POLL, 6, 1))
    assert (5, 1) not in server.transfers


def test_a_new_request_under_an_old_number_starts_over():
    rec = Recorder()
    server = _server(rec)
    cam = Camera(server)
    cam.xfer = 40
    cam.request("GET", "/node/v1/schedule", key="first")
    server.transfers[(cam.node, 41)] = server.transfers.get((cam.node, 41)) or rl.Transfer(cam.node, 41, 1, 0, 0)
    server.transfers[(cam.node, 41)].state = "ready"  # as if its DONE had been lost
    cam.xfer = 40  # the camera lost power and drew the same number again
    assert cam.request("GET", "/node/v1/schedule", key="second")[0] == 201
    assert [c[2]["Authorization"] for c in rec.calls] == ["Bearer first", "Bearer second"]


def test_frames_from_another_protocol_version_are_ignored():
    frame = bytearray(rl.header(rl.POLL, 5, 1))
    frame[0] = 2 << 4 | rl.POLL
    assert _server(Recorder()).handle(bytes(frame)) == []


def test_serial_framing_round_trip_and_damage():
    payload = bytes([rl.SLIP_END, rl.SLIP_ESC, 0, 255]) * 10
    [msg] = rl.SlipDecoder().feed(rl.serial_message(rl.SER_TX, payload))
    assert rl.parse_serial(msg) == (rl.SER_TX, payload)
    assert rl.parse_serial(msg[:-1] + bytes([msg[-1] ^ 1])) is None
    assert rl.crc16(b"123456789") == 0x29B1  # CRC-16/CCITT-FALSE check value


class FakePort:
    def __init__(self, incoming: bytes):
        self.incoming, self.out = incoming, bytearray()

    @property
    def in_waiting(self):
        return len(self.incoming)

    def read(self, n):
        data, self.incoming = self.incoming[:n], self.incoming[n:]
        return data

    def write(self, data):
        self.out += data


def test_bridge_passes_frames_and_answers():
    poll = rl.header(rl.POLL, 5, 1)
    port = FakePort(rl.serial_message(rl.SER_HELLO, b"\x01bridge 0.1")
                    + rl.serial_message(rl.SER_RX, struct.pack("<b", -77) + poll)[:7])  # arrives in two reads
    bridge = rl.Bridge(port, _server(Recorder()))
    bridge.poll()
    assert port.out == b""
    port.incoming = rl.serial_message(rl.SER_RX, struct.pack("<b", -77) + poll)[7:]
    bridge.poll()
    [msg] = rl.SlipDecoder().feed(bytes(port.out))
    kind, frame = rl.parse_serial(msg)
    assert kind == rl.SER_TX and rl.parse_frame(frame).type == rl.RESP_INFO


def test_through_the_real_gateway(tmp_path: Path):
    cfg = config_mod.deep_merge(config_mod.DEFAULTS, {
        "trap_id": "T1", "api_key": "hubkey", "server_url": "http://server", "schedule": {"times": ["07:00", "19:30"]},
        "hub": {"port": 0, "listen": "127.0.0.1", "nodes": {"T2": {"api_key": "key2"}}},
    })
    gw = gateway.Gateway(cfg, tmp_path, clock=lambda: NOW)
    http = gateway.make_server(gw, "127.0.0.1", 0)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    try:
        server = rl.LinkServer(rl.http_sender(f"http://127.0.0.1:{http.server_address[1]}"), start=lambda f: f())
        cam = Camera(server, loss=0.1, seed=9)
        meta = json.dumps({"node_capture_id": "a1b2c3d4e5f60718", "clock_synced": True,
                           "captured_at": "2026-10-05T23:31:00+00:00", "device": {"rssi": -70}})
        status, reply = cam.request("POST", "/node/v1/captures", JPEG, key="key2", meta=meta, ctype="image/jpeg")
        assert status == 201 and json.loads(reply)["uid"] == "20261005T233100Z_T2_a1b2c3d4e5f60718"
        [photo] = gw.queue("T2").pending()
        assert photo.read_bytes() == JPEG
        assert json.loads(photo.with_suffix(".json").read_text())["device"]["hub_rssi"] == -81
        status, reply = cam.request("GET", "/node/v1/schedule", key="key2", meta='{"awake_ms": 9000}')
        assert status == 200 and len(json.loads(reply)["wakes"]) == 12
        assert cam.request("GET", "/node/v1/schedule", key="wrong")[0] == 401
    finally:
        http.shutdown()
        http.server_close()
