"""One wake cycle: photograph the liner, queue it, upload, schedule the next wake, halt.

Run by systemd at boot on the trap (see systemd/sentinel-cycle.service), or by
hand on the bench:

    sentinel-cycle --config config.toml --no-halt
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, config as config_mod, hardware
from .camera import CaptureError, make_camera
from .schedule import next_wake, wake_reason
from .state import State
from .uploader import Queue, drain

log = logging.getLogger("sentinel")


def capture_once(cfg: dict, data_dir: Path, reason: str, state: State, new_card: bool = False) -> Path:
    now = datetime.now(timezone.utc)
    stem = f"{now.strftime('%Y%m%dT%H%M%SZ')}_{cfg['trap_id']}"
    tmp = data_dir / f"{stem}.jpg"

    camera = make_camera(cfg, data_dir)
    if new_card and hasattr(camera, "new_card"):
        camera.new_card()
    with hardware.led(cfg["led"]["enabled"], cfg["led"]["gpio"]):
        cam_meta = camera.capture(tmp)

    env = hardware.read_sht4x() if cfg["sensors"]["sht4x"] else None
    power = hardware.read_ina219(cfg["sensors"]["ina219_shunt_ohms"]) if cfg["sensors"]["ina219"] else None
    meta = {
        "capture_uid": stem,
        "trap_id": cfg["trap_id"],
        "captured_at": now.isoformat(),
        "wake_reason": reason,
        "new_card": new_card,
        "camera": cam_meta,
        "env": env,
        "power": power,
        "device": {
            "sw_version": __version__,
            "cpu_temp_c": hardware.cpu_temp_c(),
            "uptime_s": hardware.uptime_s(),
            "last_error": state.get("last_error"),
            "disk_free_mb": round(shutil.disk_usage(data_dir).free / 1e6),
        },
    }
    return Queue(data_dir).add(tmp, meta)


def run(cfg_path: Path | None, halt: bool | None, capture: bool = True, new_card: bool = False) -> int:
    base_cfg = config_mod.load(cfg_path)
    data_dir = Path(base_cfg["data_dir"])
    data_dir.mkdir(parents=True, exist_ok=True)
    state = State(data_dir)
    cfg = config_mod.load(cfg_path, remote=state.get("remote_config"))

    now = datetime.now(timezone.utc)
    reason = wake_reason(now, state.get("expected_wake"))
    # In the field, pressing the Pi 5 power button to wake the trap means "I just put in a fresh liner".
    new_card = new_card or (reason == "manual" and cfg["schedule"].get("manual_wake_is_new_card", False))
    log.info("wake (%s), trap %s, sw %s%s", reason, cfg["trap_id"], __version__, ", NEW CARD" if new_card else "")

    error = None
    if capture:
        try:
            path = capture_once(cfg, data_dir, reason, state, new_card)
            log.info("captured %s", path.name)
        except (CaptureError, OSError) as e:
            error = f"capture failed: {e}"
            log.error(error)

    queue = Queue(data_dir)
    uploaded, reply, up_err = drain(
        queue, cfg["server_url"], cfg["api_key"], cfg["upload"]["timeout_s"], cfg["upload"]["max_per_cycle"]
    )
    log.info("uploaded %d, %d still queued", uploaded, len(queue.pending()))
    error = error or up_err
    if reply and isinstance(reply.get("config"), dict):
        state.set("remote_config", reply["config"])
        cfg = config_mod.load(cfg_path, remote=reply["config"])

    wake_at = next_wake(datetime.now(timezone.utc), cfg["schedule"]["times"], cfg["timezone"])
    state.set("expected_wake", wake_at.isoformat())
    state.set("last_error", error)
    state.save()

    should_halt = cfg["schedule"]["halt_after_cycle"] if halt is None else halt
    if should_halt:
        if not hardware.set_rtc_wake(int(wake_at.timestamp())):
            log.error("not halting: RTC alarm could not be set, so the trap would never wake")
            return 1
        log.info("next wake %s; halting", wake_at.isoformat())
        subprocess.run(["sudo", "systemctl", "poweroff"], check=False)
    else:
        log.info("next scheduled wake would be %s (not halting)", wake_at.isoformat())
    return 0 if error is None else 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=None, help="config.toml (default /etc/sentinel/config.toml)")
    ap.add_argument("--no-halt", action="store_true", help="stay powered on after the cycle (bench use)")
    ap.add_argument("--upload-only", action="store_true", help="skip the photo, just drain the queue")
    ap.add_argument("--new-card", action="store_true", help="a fresh liner was just installed")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return run(args.config, halt=False if args.no_halt else None, capture=not args.upload_only, new_card=args.new_card)


if __name__ == "__main__":
    sys.exit(main())
