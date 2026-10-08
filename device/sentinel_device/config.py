"""Load the device config file and merge in overrides sent by the server."""

from __future__ import annotations

import copy
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path("/etc/sentinel/config.toml")

DEFAULTS: dict[str, Any] = {
    "trap_id": "T0",
    "api_key": "",
    "server_url": "http://localhost:8000",
    "data_dir": "/var/lib/sentinel",
    "timezone": "America/New_York",
    "schedule": {"times": ["07:00", "13:00", "19:30"], "halt_after_cycle": False, "manual_wake_is_new_card": False},
    "camera": {
        "backend": "picamera2",
        "lens_position": 6.5,
        "exposure_us": 8000,
        "analogue_gain": 1.0,
        "colour_gains": [1.9, 1.6],
        "lens_shading": True,  # False: drop the sensor's stock lens correction (wide-angle lenses)
        "flat_field": True,  # use data_dir/flatfield.npz when sentinel-flatfield has made one
        "jpeg_quality": 95,
        "settle_s": 1.5,
        "usb_device": "/dev/video0",
        "usb_size": [640, 480],
        "usb_wb_temperature": 0,  # 0 = leave auto white balance on
        "usb_controls": {},  # v4l2 control name -> value, applied before every capture
        "usb_max_clip_frac": 0.02,  # lower brightness while more of a channel than this is saturated
    },
    "led": {"enabled": True, "gpio": 17},
    "sensors": {"sht4x": True, "ina219": False, "ina219_shunt_ohms": 0.1},
    "upload": {"timeout_s": 30, "max_per_cycle": 20},
    # Hub for ESP32 camera traps (gateway.py). nodes: {trap_id: {"api_key": ...}} from [hub.nodes.<trap_id>].
    "hub": {"enabled": False, "listen": "0.0.0.0", "port": 8080, "window_s": 240, "node_offset_s": 60,
            "max_image_mb": 4, "nodes": {}},
}

# Keys the server is allowed to change remotely. Identity and credentials stay local.
REMOTE_KEYS = {"schedule", "camera", "led"}


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load(path: Path | None = None, remote: dict | None = None) -> dict:
    path = path or DEFAULT_CONFIG_PATH
    with open(path, "rb") as f:
        cfg = deep_merge(DEFAULTS, tomllib.load(f))
    if remote:
        cfg = deep_merge(cfg, {k: v for k, v in remote.items() if k in REMOTE_KEYS})
    return cfg
