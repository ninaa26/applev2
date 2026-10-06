from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from sentinel_device import hardware, schedule, uploader
from sentinel_device.camera import FakeCamera


def test_next_wake_same_day_and_rollover():
    times = ["07:00", "19:30"]
    # 2026-10-05 12:00 EDT == 16:00 UTC -> next is 19:30 EDT == 23:30 UTC
    now = datetime(2026, 10, 5, 16, 0, tzinfo=timezone.utc)
    assert schedule.next_wake(now, times, "America/New_York") == datetime(2026, 10, 5, 23, 30, tzinfo=timezone.utc)
    # 21:00 EDT -> tomorrow 07:00 EDT == 11:00 UTC
    now = datetime(2026, 10, 6, 1, 0, tzinfo=timezone.utc)
    assert schedule.next_wake(now, times, "America/New_York") == datetime(2026, 10, 6, 11, 0, tzinfo=timezone.utc)


def test_next_wake_across_dst_end():
    # DST ends 2026-11-01 in the US: 07:00 EST is 12:00 UTC
    now = datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc)
    assert schedule.next_wake(now, ["07:00"], "America/New_York") == datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def test_wake_reason():
    expected = datetime(2026, 10, 5, 23, 30, tzinfo=timezone.utc)
    assert schedule.wake_reason(datetime(2026, 10, 5, 23, 31, tzinfo=timezone.utc), expected.isoformat()) == "scheduled"
    assert schedule.wake_reason(datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc), expected.isoformat()) == "manual"
    assert schedule.wake_reason(datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc), None) == "first"
    # the alarm time passed with the board off: it had no power, nobody pressed the button
    assert schedule.wake_reason(datetime(2026, 10, 6, 6, 30, tzinfo=timezone.utc), expected.isoformat()) == "power_restored"
    # the last cycle never powered off by itself
    assert schedule.wake_reason(datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc), expected.isoformat(), clean_halt=False) == "interrupted"


def test_sht4x_crc_and_decode():
    # Sensirion datasheet CRC example: 0xBEEF -> 0x92
    assert hardware._crc8_sht(b"\xbe\xef") == 0x92
    t_raw, rh_raw = 0x6666, 0x8000  # ~25 °C, ~56.5 %RH
    raw = bytes([t_raw >> 8, t_raw & 0xFF]) + bytes([hardware._crc8_sht(bytes([t_raw >> 8, t_raw & 0xFF]))])
    raw += bytes([rh_raw >> 8, rh_raw & 0xFF, hardware._crc8_sht(bytes([rh_raw >> 8, rh_raw & 0xFF]))])
    temp_c, rh = hardware.sht4x_decode(raw)
    assert temp_c == pytest.approx(25.0, abs=0.1)
    assert rh == pytest.approx(56.5, abs=0.1)
    with pytest.raises(ValueError):
        hardware.sht4x_decode(raw[:5] + b"\x00")


def test_fake_camera_accumulates(tmp_path: Path):
    cam = FakeCamera({"jpeg_quality": 80}, tmp_path, seed=1)
    counts = []
    for i in range(6):
        meta = cam.capture(tmp_path / f"{i}.jpg")
        counts.append(len(meta["fake_truth"]))
    assert counts == sorted(counts) and counts[-1] > 0
    cam.new_card()
    assert len(cam.capture(tmp_path / "new.jpg")["fake_truth"]) <= 2


def test_queue_keeps_photos_when_server_down(tmp_path: Path, monkeypatch):
    q = uploader.Queue(tmp_path)
    for i in range(3):
        img = tmp_path / f"2026100{i}T000000Z_T1.jpg"
        img.write_bytes(b"jpeg")
        q.add(img, {"capture_uid": img.stem})

    def down(*a, **k):
        raise requests.ConnectionError("nope")

    monkeypatch.setattr(uploader, "upload_one", down)
    n, reply, err = uploader.drain(q, "http://x", "k", 1, 10)
    assert n == 0 and "unreachable" in err and len(q.pending()) == 3

    sent = []
    monkeypatch.setattr(uploader, "upload_one", lambda url, key, image, t: sent.append(image.name) or {"config": {}})
    n, reply, err = uploader.drain(q, "http://x", "k", 1, 2)
    assert n == 2 and err is None and sent == sorted(sent) and len(q.pending()) == 1


def test_clipped_fraction_reports_worst_channel():
    import numpy as np

    from sentinel_device.camera import clipped_fraction

    frame = np.zeros((10, 10, 3), np.uint8)
    frame[..., 2] = 255          # red fully clipped (orange trap roof)
    frame[:5, :, 1] = 255        # half the green clipped
    assert clipped_fraction(frame) == 1.0
    assert clipped_fraction(frame[..., :2]) == 0.5


def _queue_one(tmp_path: Path) -> uploader.Queue:
    q = uploader.Queue(tmp_path)
    img = tmp_path / "20261001T000000Z_T1.jpg"
    img.write_bytes(b"jpeg")
    q.add(img, {"capture_uid": img.stem})
    return q


def _http_error(status: int):
    def fail(*a, **k):
        r = requests.Response()
        r.status_code = status
        raise requests.HTTPError(f"{status}", response=r)
    return fail


@pytest.mark.parametrize("status", [401, 403, 404, 500])
def test_auth_and_server_errors_keep_photos_queued(tmp_path: Path, monkeypatch, status):
    q = _queue_one(tmp_path)
    monkeypatch.setattr(uploader, "upload_one", _http_error(status))
    n, _, err = uploader.drain(q, "http://x", "k", 1, 10)
    assert n == 0 and err and len(q.pending()) == 1


def test_bad_photo_is_parked(tmp_path: Path, monkeypatch):
    q = _queue_one(tmp_path)
    monkeypatch.setattr(uploader, "upload_one", _http_error(422))
    n, _, err = uploader.drain(q, "http://x", "k", 1, 10)
    assert n == 0 and err is None and q.pending() == [] and len(list((q.queue_dir / "rejected").glob("*.jpg"))) == 1


def test_drain_stops_at_deadline(tmp_path: Path, monkeypatch):
    q = _queue_one(tmp_path)
    monkeypatch.setattr(uploader, "upload_one", lambda *a: {"config": {}})
    n, _, err = uploader.drain(q, "http://x", "k", 1, 10, deadline=0.0)  # already past
    assert n == 0 and "out of time" in err and len(q.pending()) == 1


def _field_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'trap_id = "T1"\napi_key = "k"\nserver_url = "http://127.0.0.1:9"\n'
                   f'data_dir = "{tmp_path / "data"}"\n[schedule]\nhalt_after_cycle = true\n'
                   f'[camera]\nbackend = "fake"\n[led]\nenabled = false\n[sensors]\nsht4x = false\n')
    return cfg


def _halt_spies(monkeypatch):
    from sentinel_device import cycle
    calls = {"rtc": [], "poweroff": []}
    monkeypatch.setattr(cycle.hardware, "set_rtc_wake", lambda t: calls["rtc"].append(t) or True)
    monkeypatch.setattr(cycle.subprocess, "run", lambda cmd, **k: calls["poweroff"].append(cmd))
    monkeypatch.setattr(cycle, "drain", lambda *a, **k: (0, None, "server unreachable: test"))
    return cycle, calls


def test_cycle_still_sets_alarm_and_halts_when_capture_crashes(tmp_path: Path, monkeypatch):
    cycle, calls = _halt_spies(monkeypatch)

    def boom(*a, **k):
        raise IndexError("list index out of range")  # what Picamera2() raises with no camera attached
    monkeypatch.setattr(cycle, "capture_once", boom)
    assert cycle.run(_field_config(tmp_path), halt=None) == 2
    assert len(calls["rtc"]) == 1 and calls["poweroff"]


def _boot(tmp_path: Path, monkeypatch, at: datetime, **state) -> dict:
    """Run one field cycle as if the board booted at `at` with `state` on disk; returns the photo's metadata."""
    import json
    cycle, calls = _halt_spies(monkeypatch)
    cfg = _field_config(tmp_path)
    cfg.write_text(cfg.read_text().replace("halt_after_cycle = true", "halt_after_cycle = true\nmanual_wake_is_new_card = true"))
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    (data / "state.json").write_text(json.dumps(state))

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return at
    monkeypatch.setattr(cycle, "datetime", Clock)
    seen = {}
    monkeypatch.setattr(cycle, "capture_once",
                        lambda cfg, d, reason, st, new_card=False: seen.update(reason=reason, new_card=new_card) or d / "x.jpg")
    cycle.run(cfg, halt=None)
    seen["state"] = json.loads((data / "state.json").read_text())
    return seen


def test_only_a_button_press_starts_a_new_liner(tmp_path: Path, monkeypatch):
    expected = datetime(2026, 10, 5, 23, 30, tzinfo=timezone.utc)  # 19:30 in New York
    early, late = datetime(2026, 10, 5, 21, 0, tzinfo=timezone.utc), datetime(2026, 10, 6, 10, 30, tzinfo=timezone.utc)

    press = _boot(tmp_path, monkeypatch, early, expected_wake=expected.isoformat(), clean_halt=True)
    assert (press["reason"], press["new_card"]) == ("manual", True)
    assert press["state"]["clean_halt"] is True  # this cycle powered off by itself too

    flat_battery = _boot(tmp_path, monkeypatch, late, expected_wake=expected.isoformat(), clean_halt=True)
    assert (flat_battery["reason"], flat_battery["new_card"]) == ("power_restored", False)

    cut_mid_cycle = _boot(tmp_path, monkeypatch, early, expected_wake=expected.isoformat(), clean_halt=False)
    assert (cut_mid_cycle["reason"], cut_mid_cycle["new_card"]) == ("interrupted", False)

    old_state_file = _boot(tmp_path, monkeypatch, early, expected_wake=expected.isoformat())
    assert (old_state_file["reason"], old_state_file["new_card"]) == ("manual", True)


def test_cycle_survives_a_broken_schedule_from_the_server(tmp_path: Path, monkeypatch):
    import json
    cycle, calls = _halt_spies(monkeypatch)
    cfg = _field_config(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "state.json").write_text(json.dumps({"remote_config": {"schedule": {"times": ["25:99"]},
                                                                                "camera": {"backend": "nope"}}}))
    assert cycle.run(cfg, halt=None) == 2
    assert len(calls["rtc"]) == 1 and calls["poweroff"]


def test_flat_field_makes_a_tinted_vignetted_card_even(tmp_path: Path):
    import numpy as np
    from PIL import Image
    from sentinel_device import flatfield

    h, w = 480, 640
    yy, xx = np.mgrid[0:h, 0:w]
    r2 = ((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2
    # green centre, pink edges, darker corners: what the wide lens does to a white card
    card = np.stack([200 * (1 - 0.15 * r2), 210 * (1 - 0.35 * r2), 190 * (1 - 0.2 * r2)], axis=2)
    card[::40] = 60  # printed grid lines must not dent the map
    card[:, ::40] = 60
    white = card.astype(np.uint8)

    gain = flatfield.build(white)
    flatfield.save(tmp_path, gain, exposure_us=8000)
    out = np.asarray(flatfield.apply(Image.fromarray(white), flatfield.load(tmp_path)), dtype=np.float32)
    spots = [out[y - 8 : y + 8, x - 8 : x + 8].reshape(-1, 3).mean(axis=0)
             for y, x in ((h // 2 + 20, w // 2 + 20), (60, 60), (60, w - 60), (h - 60, 60), (h - 60, w - 60))]
    spots = np.array(spots)
    assert spots.max() - spots.min() < 12          # even and neutral, centre to corners
    assert out[::40].mean() < 120                  # the grid lines are still there
    assert flatfield.load(tmp_path / "nowhere") is None


def test_flatfield_tool_flags_red_roof_light_and_suggests_white_balance():
    import numpy as np
    from sentinel_device.tools.flatfield import report

    red = np.zeros((100, 100, 3), np.uint8)
    red[...] = (200, 30, 40)
    assert any("coloured roof" in line for line in report(red, (1.9, 1.6)))
    warm = np.zeros((100, 100, 3), np.uint8)
    warm[...] = (200, 180, 150)
    lines = report(warm, (2.0, 1.5))
    assert "Exposure is fine." in lines and any("colour_gains = [1.80, 1.80]" in line for line in lines)


def test_flat_field_ignores_the_red_trap_walls_around_the_card():
    import numpy as np
    from sentinel_device import flatfield

    white = np.zeros((480, 640, 3), np.uint8)
    white[...] = (200, 30, 35)                      # red walls all round
    white[60:420, 100:540] = (180, 185, 175)        # the card
    gain = flatfield.build(white)
    assert gain.max() < 1.2 and gain.min() > 0.9    # walls take the card's gains, no 4x green/blue
    red_only = np.zeros((480, 640, 3), np.uint8)
    red_only[...] = (200, 30, 35)
    assert flatfield.build(red_only).max() > 2      # no card in the centre: left as is
