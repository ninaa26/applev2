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
    assert schedule.wake_reason(datetime(2026, 10, 5, 20, 0, tzinfo=timezone.utc), None) == "manual"


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
