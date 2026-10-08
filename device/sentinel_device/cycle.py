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
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, config as config_mod, hardware
from .camera import make_camera
from .gateway import Gateway, serve_window
from .schedule import next_wake, wake_reason
from .state import State
from .uploader import Queue, drain

log = logging.getLogger("sentinel")


def capture_once(cfg: dict, data_dir: Path, reason: str, state: State, new_card: bool = False,
                 new_card_source: str | None = None) -> Path:
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
        # "button": worked out from an unscheduled boot, which the server checks against the last photo;
        # "flag": someone ran --new-card, taken at their word
        "new_card_source": new_card_source if new_card else None,
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


# The systemd unit kills the cycle after 300 s (15 s of it waiting for Wi-Fi). A killed cycle never
# sets the wake alarm or powers off, so uploads stop starting after this many seconds of the cycle.
UPLOAD_BUDGET_S = 180
# A hub also stays open this long for its ESP32 traps ([hub] window_s), so the unit allows 600 s.


def _schedule(cfgs: list[dict]) -> tuple[datetime, bool]:
    """(next wake, halt?) from the first config whose schedule works: a bad schedule pushed by the
    server falls back to the local file, then the built-in defaults, so the trap always wakes again."""
    for cfg in cfgs:
        try:
            sched = cfg["schedule"]
            return next_wake(datetime.now(timezone.utc), sched["times"], cfg["timezone"]), bool(sched["halt_after_cycle"])
        except Exception as e:
            log.error("unusable schedule %r: %s", cfg.get("schedule"), e)
    raise RuntimeError("no usable schedule")  # the built-in defaults always work


def run(cfg_path: Path | None, halt: bool | None, capture: bool = True, new_card: bool = False) -> int:
    started = time.monotonic()
    base_cfg = config_mod.load(cfg_path)
    data_dir = Path(base_cfg["data_dir"])
    data_dir.mkdir(parents=True, exist_ok=True)
    state = State(data_dir)
    cfg = config_mod.load(cfg_path, remote=state.get("remote_config"))

    # Whatever goes wrong from here on (no camera, bad settings from the server, network trouble),
    # the cycle must still reach the end: set the wake alarm and power off.
    error = None
    try:
        now = datetime.now(timezone.utc)
        # State files from before clean_halt existed have no entry: treat those as a clean power-off.
        reason = wake_reason(now, state.get("expected_wake"), state.get("clean_halt", True))
        state.set("clean_halt", False)  # until this cycle reaches its own power-off
        state.save()
        # In the field, pressing the Pi 5 power button to wake the trap means "I just put in a fresh liner".
        # A boot after a power cut is not that (see wake_reason); power pulled and put back between two wakes
        # looks the same from here, so the server checks the photo before it believes a button press.
        source = "flag" if new_card else "button"
        new_card = new_card or (reason == "manual" and cfg["schedule"].get("manual_wake_is_new_card", False))
        log.info("wake (%s), trap %s, sw %s%s", reason, cfg["trap_id"], __version__, ", NEW CARD" if new_card else "")

        # A hub takes its ESP32 traps' photos while it photographs its own liner.
        gateway, window, budget = None, None, UPLOAD_BUDGET_S
        if cfg["hub"]["enabled"]:
            try:
                gateway = Gateway(cfg, data_dir)
                budget += cfg["hub"]["window_s"]
                window = threading.Thread(target=serve_window, args=(gateway, started + cfg["hub"]["window_s"]), daemon=True)
                window.start()
            except Exception as e:
                error = f"hub failed: {e.__class__.__name__}: {e}"
                log.exception(error)

        if capture:
            try:
                path = capture_once(cfg, data_dir, reason, state, new_card, source)
                log.info("captured %s", path.name)
            except Exception as e:
                error = f"capture failed: {e.__class__.__name__}: {e}"
                log.exception(error)

        if window is not None:
            window.join()

        queue = Queue(data_dir)
        uploaded, reply, up_err = drain(
            queue, cfg["server_url"], cfg["api_key"], cfg["upload"]["timeout_s"], cfg["upload"]["max_per_cycle"],
            deadline=started + budget,
        )
        log.info("uploaded %d, %d still queued", uploaded, len(queue.pending()))
        error = error or up_err
        if gateway is not None:
            error = error or gateway.forward(deadline=started + budget)
        if reply and isinstance(reply.get("config"), dict):
            state.set("remote_config", reply["config"])
            cfg = config_mod.load(cfg_path, remote=reply["config"])
    except Exception as e:
        error = error or f"cycle failed: {e.__class__.__name__}: {e}"
        log.exception(error)

    wake_at, cfg_halt = _schedule([cfg, base_cfg, config_mod.DEFAULTS])
    state.set("expected_wake", wake_at.isoformat())
    state.set("last_error", error)
    state.save()

    should_halt = cfg_halt if halt is None else halt
    if should_halt:
        if not hardware.set_rtc_wake(int(wake_at.timestamp())):
            log.error("not halting: RTC alarm could not be set, so the trap would never wake")
            return 1
        state.set("clean_halt", True)
        state.save()
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
