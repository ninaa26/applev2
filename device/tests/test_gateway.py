import json
import socket
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
import requests

from sentinel_device import config as config_mod, gateway, uploader

JPEG = b"\xff\xd8" + b"\x00" * 100 + b"\xff\xd9"
# 2026-10-05 19:31:30 in New York: the hub's 19:30 slot opened 90 s ago
NOW = datetime(2026, 10, 5, 23, 31, 30, tzinfo=UTC).timestamp()


def _gw(tmp_path: Path, port: int = 0, **hub) -> gateway.Gateway:
    cfg = config_mod.deep_merge(config_mod.DEFAULTS, {
        "trap_id": "T1", "api_key": "hubkey", "server_url": "http://server", "schedule": {"times": ["07:00", "19:30"]},
        "hub": {"port": port, "listen": "127.0.0.1", "nodes": {"T2": {"api_key": "key2"}, "T3": {"api_key": "key3"}}, **hub},
    })
    return gateway.Gateway(cfg, tmp_path, clock=lambda: NOW)


def _meta(**kw) -> str:
    return json.dumps({"node_capture_id": "a1b2c3d4e5f60718", "clock_synced": True,
                       "captured_at": "2026-10-05T23:31:00+00:00", **kw})


def test_node_photo_is_queued_under_its_own_trap(tmp_path: Path):
    gw = _gw(tmp_path)
    status, reply = gw.capture("Bearer key2", _meta(device={"rssi": -71}), JPEG)
    assert status == 201
    assert reply["uid"] == "20261005T233100Z_T2_a1b2c3d4e5f60718"
    # next wake: the 07:00 slot tomorrow plus the 60 s node offset
    assert reply["next_wake"] == "2026-10-06T11:01:00+00:00" and reply["sleep_s"] == 41370
    assert len(reply["wakes"]) == 12 and reply["wakes"][1] - reply["wakes"][0] == 12.5 * 3600  # then 19:31
    [photo] = gw.queue("T2").pending()
    meta = json.loads(photo.with_suffix(".json").read_text())
    assert meta["trap_id"] == "T2" and meta["capture_uid"] == photo.stem and meta["device"] == {"rssi": -71}
    assert meta["hub"]["hub_trap_id"] == "T1" and gw.queue("T3").pending() == []



def test_a_check_in_just_before_a_slot_keeps_that_slot(tmp_path: Path):
    """Replies to cameras used the hub's own 2-minute boot margin, so a check-in at 09:59:10 got "next wake
    14:01" and the 10:01 photo was skipped. The node itself only drops wakes under 60 s away."""
    def reply_at(local: str) -> dict:
        when = datetime.fromisoformat(f"2026-10-05T{local}-04:00").timestamp()  # New York, EDT
        gw = gateway.Gateway(config_mod.deep_merge(config_mod.DEFAULTS, {
            "trap_id": "T1", "api_key": "hubkey", "server_url": "http://server",
            "schedule": {"times": ["10:00", "14:00"]},
            "hub": {"listen": "127.0.0.1", "nodes": {"T2": {"api_key": "key2"}}},
        }), tmp_path, clock=lambda: when)
        return gw.schedule("Bearer key2")[1]

    assert reply_at("09:59:10")["next_wake"] == "2026-10-05T14:01:00+00:00"  # 10:01 EDT
    assert reply_at("09:59:10")["sleep_s"] == 110
    assert reply_at("10:00:30")["next_wake"] == "2026-10-05T18:01:00+00:00"  # 10:01 is under 60 s away

def test_retry_after_a_lost_reply_is_not_queued_twice(tmp_path: Path):
    gw = _gw(tmp_path)
    assert gw.capture("Bearer key2", _meta(), JPEG)[0] == 201
    status, reply = gw.capture("Bearer key2", _meta(), JPEG)
    assert status == 200 and reply["duplicate"] and len(gw.queue("T2").pending()) == 1
    gw.queue("T2").mark_sent(gw.queue("T2").pending()[0])
    assert gw.capture("Bearer key2", _meta(), JPEG)[0] == 200  # already uploaded to the server


def test_node_that_never_had_the_time_gives_the_photos_age(tmp_path: Path):
    gw = _gw(tmp_path)
    status, reply = gw.capture("Bearer key3", json.dumps({"node_capture_id": "00ff00ff00ff", "age_s": 30}), JPEG)
    assert status == 201 and reply["uid"] == "20261005T233100Z_T3_00ff00ff00ff"


def test_bad_requests_are_refused(tmp_path: Path):
    gw = _gw(tmp_path)
    assert gw.capture("Bearer nope", _meta(), JPEG)[0] == 401
    assert gw.capture("", _meta(), JPEG)[0] == 401
    assert gw.capture("Bearer key2", _meta(trap_id="T3"), JPEG)[0] == 422
    assert gw.capture("Bearer key2", _meta(node_capture_id="../../etc"), JPEG)[0] == 422
    assert gw.capture("Bearer key2", "not json", JPEG)[0] == 422
    assert gw.capture("Bearer key2", _meta(), JPEG[:50])[0] == 415  # cut off mid-transfer
    assert gw.queue("T2").pending() == []


def test_forward_uploads_each_node_with_its_own_key(tmp_path: Path, monkeypatch):
    gw = _gw(tmp_path)
    gw.capture("Bearer key2", _meta(), JPEG)
    gw.capture("Bearer key3", _meta(node_capture_id="1234567890ab"), JPEG)
    sent = []
    monkeypatch.setattr(uploader, "upload_one", lambda url, key, image, t: sent.append((key, image.name)) or {"config": {}})
    assert gw.forward() is None
    assert sorted(k for k, _ in sent) == ["key2", "key3"]
    assert gw.queue("T2").pending() == [] and gw.queue("T3").pending() == []


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_window_over_http_closes_once_every_node_checked_in(tmp_path: Path):
    port = _free_port()
    gw = _gw(tmp_path, port=port)
    t = threading.Thread(target=gateway.serve_window, args=(gw, time.monotonic() + 20))
    t.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            requests.get(f"{base}/healthz", timeout=1)
            break
        except requests.ConnectionError:
            time.sleep(0.05)
    r = requests.post(f"{base}/node/v1/captures", data=JPEG, timeout=5,
                      headers={"Authorization": "Bearer key2", "X-Sentinel-Meta": _meta(), "Content-Type": "image/jpeg"})
    assert r.status_code == 201 and r.json()["sleep_s"] > 0
    assert requests.get(f"{base}/node/v1/schedule", headers={"Authorization": "Bearer key2"}, timeout=5).status_code == 200
    assert t.is_alive()  # T3 has not checked in yet
    requests.get(f"{base}/node/v1/schedule", headers={"Authorization": "Bearer key3"}, timeout=5)
    t.join(timeout=5)
    assert not t.is_alive() and len(gw.queue("T2").pending()) == 1


def test_hub_cycle_opens_the_window_then_uploads_node_photos_and_halts(tmp_path: Path, monkeypatch):
    from sentinel_device import cycle

    port = _free_port()
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'trap_id = "T1"\napi_key = "k1"\nserver_url = "http://127.0.0.1:9"\ndata_dir = "{tmp_path / "data"}"\n'
                   f'[schedule]\nhalt_after_cycle = true\n[camera]\nbackend = "fake"\n[led]\nenabled = false\n'
                   f'[sensors]\nsht4x = false\n[hub]\nenabled = true\nlisten = "127.0.0.1"\nport = {port}\nwindow_s = 1\n'
                   f'[hub.nodes.T2]\napi_key = "key2"\n')
    calls = {"rtc": [], "poweroff": [], "keys": []}
    monkeypatch.setattr(cycle.hardware, "set_rtc_wake", lambda t: calls["rtc"].append(t) or True)
    monkeypatch.setattr(cycle.subprocess, "run", lambda cmd, **k: calls["poweroff"].append(cmd))
    monkeypatch.setattr(uploader, "upload_one", lambda url, key, image, t: calls["keys"].append(key) or {"config": {}})
    queued = gateway.Gateway(config_mod.load(cfg), tmp_path / "data")  # a node photo left from an earlier window
    queued.capture("Bearer key2", _meta(), JPEG)
    assert cycle.run(cfg, halt=None) == 0
    assert calls["keys"] == ["k1", "key2"] and len(calls["rtc"]) == 1 and calls["poweroff"]


class _Reply:
    def __init__(self, status: int, body: dict):
        self.status_code, self.body = status, body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self.body


def test_cameras_added_and_removed_on_the_dashboard_reach_the_hub(tmp_path: Path, monkeypatch):
    nodes = {"T4": gateway.hash_key("key4")}
    asked = []
    monkeypatch.setattr(gateway.requests, "get",
                        lambda url, headers, timeout: asked.append((url, headers["Authorization"])) or _Reply(200, {"nodes": dict(nodes)}))
    gw = _gw(tmp_path)
    assert gw.capture("Bearer key4", _meta(), JPEG)[0] == 401  # not on the list yet
    assert gw.refresh_nodes()
    assert asked == [("http://server/api/v1/hub/nodes", "Bearer hubkey")]
    assert set(gw.hashes) == {"T2", "T3", "T4"}  # the server's list plus the config's
    assert gw.capture("Bearer key4", _meta(), JPEG)[0] == 201
    assert (tmp_path / "nodes" / "T4" / "key").read_text() == "key4"

    # The server is down at the next wake: the hub still knows T4 from its cache.
    monkeypatch.setattr(gateway.requests, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError()))
    gw = _gw(tmp_path)
    assert not gw.refresh_nodes() and "T4" in gw.hashes

    # Removed on the dashboard: new photos are refused, the ones already queued still go up.
    del nodes["T4"]
    monkeypatch.setattr(gateway.requests, "get", lambda url, headers, timeout: _Reply(200, {"nodes": dict(nodes)}))
    gw.refresh_nodes()
    assert gw.capture("Bearer key4", _meta(node_capture_id="feedfacecafe"), JPEG)[0] == 401
    sent = []
    monkeypatch.setattr(uploader, "upload_one", lambda url, key, image, t: sent.append(key) or {"config": {}})
    assert gw.forward() is None and sent == ["key4"]


def test_standalone_gateway_refuses_a_config_without_a_key(tmp_path: Path, capsys):
    empty = tmp_path / "config.toml"
    empty.write_text("")
    with pytest.raises(SystemExit) as e:
        gateway.main(["--config", str(empty)])
    assert e.value.code == 2
    assert "has no api_key" in capsys.readouterr().err


def test_photo_asked_for_on_the_dashboard_goes_to_its_node_until_a_newer_photo_comes(tmp_path: Path, monkeypatch):
    asked = {"T2": "2026-10-05T23:30:00+00:00"}  # a minute before _meta's photo
    monkeypatch.setattr(gateway.requests, "get", lambda url, headers, timeout: _Reply(200, {"nodes": {}, "photo_requests": dict(asked)}))
    gw = _gw(tmp_path, checkin_min=20)
    assert gw.refresh_nodes()
    status, reply = gw.schedule("Bearer key2")
    assert status == 200 and reply["photo_now"] and reply["checkin_s"] == 1200
    assert not gw.schedule("Bearer key3")[1]["photo_now"]  # only the camera it was asked of

    old = _meta(node_capture_id="0123456789ab", captured_at="2026-10-05T23:29:00+00:00")
    assert gw.capture("Bearer key2", old, JPEG)[1]["photo_now"]  # a queued photo from before the request
    assert not gw.capture("Bearer key2", _meta(), JPEG)[1]["photo_now"]  # taken after it: done
    assert not gw.schedule("Bearer key2")[1]["photo_now"]
    gw.refresh_nodes()  # the server hasn't seen it yet and still lists it: the hub doesn't ask again
    assert not gw.schedule("Bearer key2")[1]["photo_now"]

    asked["T2"] = "2026-10-05T23:31:20+00:00"  # asked again later
    gw.refresh_nodes()
    assert gw.schedule("Bearer key2")[1]["photo_now"]
    asked.clear()
    gw.refresh_nodes()
    assert not gw.schedule("Bearer key2")[1]["photo_now"]



def test_a_requested_photo_answers_the_request_even_from_a_clock_that_runs_behind(tmp_path: Path, monkeypatch):
    """The photo a node took because it was asked answers the request, whatever its clock says. Judged by
    time alone, a node whose clock is a few minutes behind sent a photo "from before the request", was told
    photo_now again, and took photo after photo."""
    asked = {"T2": "2026-10-05T23:30:00+00:00"}
    monkeypatch.setattr(gateway.requests, "get", lambda url, headers, timeout: _Reply(200, {"nodes": {}, "photo_requests": asked}))
    gw = _gw(tmp_path)
    assert gw.refresh_nodes() and gw.schedule("Bearer key2")[1]["photo_now"]
    behind = _meta(captured_at="2026-10-05T23:28:00+00:00", wake_reason="requested")
    assert not gw.capture("Bearer key2", behind, JPEG)[1]["photo_now"]
    assert not gw.schedule("Bearer key2")[1]["photo_now"]

def test_live_preview_is_listed_on_the_hub_page_while_it_lasts(tmp_path: Path):
    now = [NOW]
    gw = _gw(tmp_path)
    gw.clock = lambda: now[0]
    assert gw.preview("Bearer nope", json.dumps({"url": "http://10.42.0.23/", "seconds": 300}))[0] == 401
    assert gw.preview("Bearer key2", json.dumps({"url": "javascript:alert(1)", "seconds": 300}))[0] == 422
    assert gw.preview("Bearer key2", json.dumps({"url": "http://10.42.0.23/", "seconds": 300}))[0] == 200
    page = gw.status_page()
    assert 'href="/preview/T2/"' in page and "<b>T3</b>" in page
    assert gw.preview_source("T2", "stream") == "http://10.42.0.23:81/stream"
    assert gw.preview_source("T2", "still") == "http://10.42.0.23/still"
    assert gw.preview_source("T3", "stream") is None and gw.preview_page("T3") is None
    now[0] += 301
    assert "/preview/T2/" not in gw.status_page()
    assert gw.preview_source("T2", "stream") is None and gw.preview_page("T2") is None


def test_live_preview_opens_by_the_hub_name(tmp_path: Path, monkeypatch):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Camera(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b"frames" if self.path == "/stream" else JPEG
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace" if self.path == "/stream" else "image/jpeg")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    camera = ThreadingHTTPServer(("127.0.0.1", 0), Camera)
    monkeypatch.setattr(gateway, "PREVIEW_STREAM_PORT", camera.server_address[1])
    gw = _gw(tmp_path)
    server = gateway.make_server(gw, "127.0.0.1", 0, socket_timeout=5)
    for s in (camera, server):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    hub = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert requests.get(f"{hub}/preview/T2/", timeout=5).status_code == 404
        gw.preview("Bearer key2", json.dumps({"url": f"http://127.0.0.1:{camera.server_address[1]}/", "seconds": 300}))
        page = requests.get(f"{hub}/preview/T2/", timeout=5)
        assert page.status_code == 200 and "src='/preview/T2/stream'" in page.text
        stream = requests.get(f"{hub}/preview/T2/stream", timeout=5)
        assert stream.content == b"frames" and stream.headers["Content-Type"] == "multipart/x-mixed-replace"
        assert requests.get(f"{hub}/preview/T2/still", timeout=5).content == JPEG
        assert requests.get(f"{hub}/preview/T3/stream", timeout=5).status_code == 404
    finally:
        for s in (camera, server):
            s.shutdown()
            s.server_close()


def test_end_of_wake_status_is_kept_for_power_and_signal_logs(tmp_path: Path):
    gw = _gw(tmp_path)
    gw.schedule("Bearer key2", json.dumps({"wake": "checkin", "awake_ms": 2900, "rssi": -60}))
    gw.schedule("Bearer key2", "not json")
    [line] = (tmp_path / "nodes" / "T2" / "status.jsonl").read_text().splitlines()
    assert json.loads(line) == {"at": "2026-10-05T23:31:30+00:00", "wake": "checkin", "awake_ms": 2900, "rssi": -60}


def test_upload_that_stops_mid_body_does_not_hold_its_connection(tmp_path: Path):
    server = gateway.make_server(_gw(tmp_path), "127.0.0.1", 0, socket_timeout=0.5)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with socket.create_connection(server.server_address, timeout=5) as s:
            s.sendall(b"POST /node/v1/captures HTTP/1.1\r\nHost: hub\r\nContent-Length: 1000\r\n\r\n" + JPEG[:10])
            t0 = time.monotonic()
            assert s.recv(1024) == b""  # the hub hangs up instead of waiting for the rest
            assert time.monotonic() - t0 < 3
    finally:
        server.shutdown()
        server.server_close()
