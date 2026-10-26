"""The hub's side of adding and updating cameras: pairing new cameras, passing on firmware sent from the
dashboard, and a new hub fetching its own key with its pairing code. The server is faked with the replies
sentinel_server sends (server/tests/test_fleet.py checks those)."""
import hashlib
import json
from pathlib import Path

import requests

from sentinel_device import config as config_mod, gateway

NOW = 1_790_000_000.0


class _Reply:
    def __init__(self, status: int, body=None, content: bytes = b""):
        self.status_code, self._body, self.content = status, body, content

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


def _gw(tmp_path: Path, clock=lambda: NOW) -> gateway.Gateway:
    cfg = config_mod.deep_merge(config_mod.DEFAULTS, {
        "trap_id": "T1", "api_key": "hubkey", "server_url": "http://server", "schedule": {"times": ["07:00", "19:30"]},
        "hub": {"listen": "127.0.0.1"},
    })
    return gateway.Gateway(cfg, tmp_path, clock=clock)


PROOF = "ab" * 16
SEALED = {"trap_id": "T2", "key_hash": gateway.hash_key("newkey"), "nonce": "01" * 16, "box": "5a" * 32, "tag": "cd" * 16}


def test_a_new_camera_waits_until_it_is_added_on_the_dashboard_then_gets_its_sealed_key(tmp_path: Path, monkeypatch):
    gw = _gw(tmp_path)
    status, reply = gw.pair(json.dumps({"code": "7f3a2c", "proof": PROOF, "fw": "0.4.0", "rssi": -61}))
    assert status == 202 and reply["waiting"] and "now" in reply
    assert gw.pair(json.dumps({"code": "zz", "proof": PROOF}))[0] == 422 and gw.pair("not json")[0] == 422
    assert gw.pair('{"code": "7F3A2C"}')[0] == 422  # older firmware with no secret can't pair
    assert "New camera 7F3A2C" in gw.status_page()

    sent, assigned = [], {}
    monkeypatch.setattr(gateway.requests, "post",
                        lambda url, json, headers, timeout: sent.append(json) or _Reply(200, {"assigned": dict(assigned)}))
    gw.sync_pairing()
    assert sent[-1] == {"waiting": [{"code": "7F3A2C", "proof": PROOF, "fw": "0.4.0", "rssi": -61}], "handed": []}
    assert gw.pair(json.dumps({"code": "7F3A2C", "proof": PROOF}))[0] == 202  # not added yet

    assigned["7F3A2C"] = {**SEALED, "box": "zz"}  # not a sealed key: ignored
    gw.sync_pairing()
    assert gw.assigned == {}
    assigned["7F3A2C"] = dict(SEALED)  # added on the dashboard
    gw.sync_pairing()
    status, reply = gw.pair(json.dumps({"code": "7F3A2C", "proof": PROOF}))
    assert status == 200 and {k: reply[k] for k in ("trap_id", "nonce", "box", "tag")} == \
        {k: SEALED[k] for k in ("trap_id", "nonce", "box", "tag")}
    assert "api_key" not in reply and "newkey" not in (tmp_path / "pairing.json").read_text()
    assert json.loads((tmp_path / "pairing.json").read_text())["7F3A2C"]["handed"] is False  # survives a restart
    assert gateway.Gateway(gw.cfg, tmp_path, clock=gw.clock).pair(json.dumps({"code": "7F3A2C", "proof": PROOF}))[0] == 200

    # The camera opens it and uses its key before the next node list from the server includes it.
    assert gw.schedule("Bearer newkey")[0] == 200
    assert (tmp_path / "nodes" / "T2" / "key").read_text() == "newkey"
    gw.sync_pairing()
    assert sent[-1] == {"waiting": [], "handed": ["7F3A2C"]}
    del assigned["7F3A2C"]  # the server has forgotten its copy
    gw.sync_pairing()
    assert gw.assigned == {}
    assert gw.pair(json.dumps({"code": "7F3A2C", "proof": PROOF}))[0] == 202  # held 10 s and reset, it would pair again


def test_a_key_the_server_stops_listing_before_the_camera_has_it_is_dropped(tmp_path: Path, monkeypatch):
    """The camera was removed, or given another key, on the dashboard: the hub stops handing out the old one."""
    gw = _gw(tmp_path)
    assigned = {"7F3A2C": dict(SEALED)}
    monkeypatch.setattr(gateway.requests, "post", lambda url, json, headers, timeout: _Reply(200, {"assigned": dict(assigned)}))
    gw.pair(json.dumps({"code": "7F3A2C", "proof": PROOF}))
    gw.sync_pairing()
    assert gw.pair(json.dumps({"code": "7F3A2C", "proof": PROOF}))[0] == 200 and "T2" in gw.hashes
    assigned.clear()
    gw.sync_pairing()
    assert gw.assigned == {} and "T2" not in gw.hashes
    old = tmp_path / "pairing.json"
    old.write_text(json.dumps({"7F3A2C": {"trap_id": "T2", "api_key": "plain", "handed": False}}))  # an older hub's file
    assert gateway.Gateway(gw.cfg, tmp_path, clock=gw.clock).assigned == {}


def test_firmware_sent_from_the_dashboard_is_offered_only_once_the_hub_has_a_good_copy(tmp_path: Path, monkeypatch):
    fw = b"\xe9firmware" * 1000
    good = {"version": "0.3.1", "size": len(fw), "md5": hashlib.md5(fw).hexdigest(), "sig": "3044" + "00" * 68}
    nodes = {"nodes": {"T2": gateway.hash_key("key2")}, "firmware": {"T2": good}}
    served = {"content": fw}

    def get(url, headers, timeout):
        if url.endswith("/api/v1/hub/nodes"):
            return _Reply(200, nodes)
        assert url == "http://server/api/v1/hub/firmware/0.3.1" and headers["Authorization"] == "Bearer hubkey"
        return _Reply(200, content=served["content"])

    monkeypatch.setattr(gateway.requests, "get", get)
    gw = _gw(tmp_path)
    served["content"] = fw[:-1]  # cut short on the way: not offered
    gw.refresh_nodes()
    assert "firmware" not in gw.schedule("Bearer key2")[1]
    assert gw.firmware_file("Bearer key2")[0] == 404

    served["content"] = fw
    gw.refresh_nodes()
    assert gw.schedule("Bearer key2")[1]["firmware"] == good
    status, path = gw.firmware_file("Bearer key2")
    assert status == 200 and path.read_bytes() == fw
    assert gw.firmware_file("Bearer nope")[0] == 401
    assert "firmware 0.3.1 waiting for it" in gw.status_page()

    nodes["firmware"] = {}  # the camera runs it now, or the update was stopped
    gw.refresh_nodes()
    assert "firmware" not in gw.schedule("Bearer key2")[1]


def test_a_hub_with_a_pairing_code_fetches_its_key_once_added_on_the_dashboard(tmp_path: Path, monkeypatch):
    cfg = config_mod.deep_merge(config_mod.DEFAULTS, {"server_url": "http://server", "api_key": ""})
    assert not gateway.load_identity(cfg, tmp_path)
    replies = [_Reply(404, {}), requests.ConnectionError(), _Reply(200, {"trap_id": "T4", "api_key": "hubkey4"})]
    asked = []

    def post(url, json, timeout):
        asked.append((url, json))
        r = replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(gateway.requests, "post", post)
    gateway.claim(cfg, tmp_path, "K7QM3XTP9R", sleep=lambda s: None)
    assert asked[0] == ("http://server/api/v1/hub/claim", {"code": "K7QM3XTP9R"}) and len(asked) == 3
    assert (cfg["trap_id"], cfg["api_key"]) == ("T4", "hubkey4")
    assert (tmp_path / "identity.json").stat().st_mode & 0o077 == 0  # the key isn't readable by others

    fresh = config_mod.deep_merge(config_mod.DEFAULTS, {"server_url": "http://server", "api_key": ""})
    assert gateway.load_identity(fresh, tmp_path) and fresh["trap_id"] == "T4"


def test_standalone_gateway_without_a_key_or_code_says_how_to_set_it_up(tmp_path: Path, capsys):
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'trap_id = ""\napi_key = ""\ndata_dir = "{tmp_path}"\n')
    try:
        gateway.main(["--config", str(cfg)])
    except SystemExit as e:
        assert e.code == 2
    assert "pairing code" in capsys.readouterr().err
