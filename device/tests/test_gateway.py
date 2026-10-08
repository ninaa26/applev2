import json
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from sentinel_device import config as config_mod, gateway, uploader

JPEG = b"\xff\xd8" + b"\x00" * 100 + b"\xff\xd9"
# 2026-10-05 19:31:30 in New York: the hub's 19:30 slot opened 90 s ago
NOW = datetime(2026, 10, 5, 23, 31, 30, tzinfo=timezone.utc).timestamp()


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
