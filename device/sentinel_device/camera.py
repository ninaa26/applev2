"""Camera backends.

`Picamera2Camera` runs on the Pi with the Camera Module 3 Wide, with focus,
exposure and white balance all locked so every photo of the liner looks the same.
`FakeCamera` renders a synthetic sticky liner that slowly collects "moths", so
the whole pipeline (upload, detection, tracking, counting) can be tested on a
laptop before the hardware is ready.
"""

from __future__ import annotations

import json
import logging
import random
import subprocess
import time
from pathlib import Path

log = logging.getLogger(__name__)


class CaptureError(RuntimeError):
    pass


class Picamera2Camera:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    def capture(self, path: Path) -> dict:
        try:
            from libcamera import controls  # type: ignore
            from picamera2 import Picamera2  # type: ignore
        except ImportError as e:  # pragma: no cover - only on the Pi
            raise CaptureError("picamera2 is not installed; set camera.backend = 'fake' to test") from e

        cam = Picamera2()
        try:
            still = cam.create_still_configuration(main={"size": cam.sensor_resolution})
            cam.configure(still)
            cam.options["quality"] = int(self.cfg["jpeg_quality"])
            cam.set_controls(
                {
                    "AfMode": controls.AfModeEnum.Manual,
                    "LensPosition": float(self.cfg["lens_position"]),
                    "AeEnable": False,
                    "ExposureTime": int(self.cfg["exposure_us"]),
                    "AnalogueGain": float(self.cfg["analogue_gain"]),
                    "AwbEnable": False,
                    "ColourGains": tuple(float(g) for g in self.cfg["colour_gains"]),
                }
            )
            cam.start()
            time.sleep(float(self.cfg["settle_s"]))
            request = cam.capture_request()
            try:
                request.save("main", str(path))
                md = request.get_metadata()
            finally:
                request.release()
            cam.stop()
        finally:
            cam.close()
        return {
            "sensor": "imx708_wide",
            "width": still["main"]["size"][0],
            "height": still["main"]["size"][1],
            "lens_position": md.get("LensPosition"),
            "exposure_us": md.get("ExposureTime"),
            "analogue_gain": md.get("AnalogueGain"),
            "colour_gains": md.get("ColourGains"),
            "lux": md.get("Lux"),
            "sensor_temp_c": md.get("SensorTemperature"),
        }


class UsbCamera:
    """A UVC webcam via OpenCV (apt `python3-opencv`, seen through the venv's system site-packages).

    Cheap webcams have no manual exposure. Their auto-exposure meters brightness, not
    individual colours, so under a coloured trap roof the red channel clips even when the
    picture looks fine overall. We set the controls from `usb_controls` (names as
    `v4l2-ctl --list-ctrls` prints them), discard warm-up frames, and then, while more than
    `usb_max_clip_frac` of any colour channel is saturated, lower `brightness` and try again.
    """

    WARMUP_FRAMES = 15
    CLIP_STEP = 16
    CLIP_TRIES = 4

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def _set_controls(self, controls: dict) -> None:
        if not controls:
            return
        # white_balance_automatic must be off before a manual temperature is accepted
        ordered = sorted(controls.items(), key=lambda kv: not kv[0].endswith("_automatic"))
        for key, value in ordered:
            r = subprocess.run(
                ["v4l2-ctl", "-d", str(self.cfg["usb_device"]), f"--set-ctrl={key}={int(value)}"],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                log.warning("camera control %s=%s rejected: %s", key, value, r.stderr.strip())

    def capture(self, path: Path) -> dict:
        try:
            import cv2  # type: ignore
        except ImportError as e:  # pragma: no cover - only on the Pi
            raise CaptureError("OpenCV is not installed: sudo apt install python3-opencv") from e

        controls = dict(self.cfg.get("usb_controls") or {})
        if self.cfg.get("usb_wb_temperature"):
            controls.update(white_balance_automatic=0, white_balance_temperature=self.cfg["usb_wb_temperature"])
        self._set_controls(controls)
        cap = cv2.VideoCapture(str(self.cfg["usb_device"]), cv2.CAP_V4L2)
        if not cap.isOpened():
            raise CaptureError(f"cannot open USB camera {self.cfg['usb_device']}")
        brightness = int(controls.get("brightness", 0))
        max_clip = float(self.cfg.get("usb_max_clip_frac", 0.02))
        try:
            w, h = self.cfg["usb_size"]
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(w))
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(h))
            time.sleep(float(self.cfg["settle_s"]))
            for attempt in range(self.CLIP_TRIES + 1):
                frame, ok = None, False
                for _ in range(self.WARMUP_FRAMES):
                    ok, frame = cap.read()
                if frame is None or not ok:
                    raise CaptureError("USB camera returned no frame")
                clip = clipped_fraction(frame)
                if clip <= max_clip or attempt == self.CLIP_TRIES or brightness <= -64:
                    break
                brightness = max(-64, brightness - self.CLIP_STEP)
                self._set_controls({"brightness": brightness})
            if not cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, int(self.cfg["jpeg_quality"])]):
                raise CaptureError(f"could not write {path}")
            wb = cap.get(cv2.CAP_PROP_WB_TEMPERATURE)
        finally:
            cap.release()
        return {
            "sensor": "usb",
            "device": str(self.cfg["usb_device"]),
            "width": frame.shape[1],
            "height": frame.shape[0],
            "wb_temperature": wb if wb > 0 else None,
            "brightness": brightness,
            "clipped_frac": round(clip, 4),
        }


def clipped_fraction(frame) -> float:
    """Largest share of pixels at the top of any one colour channel (BGR uint8 array)."""
    return max(float((frame[..., c] >= 254).mean()) for c in range(frame.shape[2]))


class FakeCamera:
    """Synthetic liner: pale card, grid lines, a lure in the middle, and moths that accumulate."""

    WIDTH, HEIGHT = 2304, 1296
    # The whole liner (~200 mm) across the frame: ~11.5 px/mm, so the 25.4 mm grid is ~290 px.
    GRID_PX = 290
    SPECIES = {  # rough body length in px at this resolution, and a colour
        "CM": (110, (95, 80, 70)),
        "OBLR": (120, (150, 110, 70)),
        "OFM": (70, (90, 90, 90)),
        "other": (50, (40, 40, 40)),
    }

    def __init__(self, cfg: dict, data_dir: Path, seed: int | None = None):
        self.cfg = cfg
        self.card_path = data_dir / "fake_card.json"
        self.rng = random.Random(seed)

    def _load(self) -> list[dict]:
        if self.card_path.exists():
            return json.loads(self.card_path.read_text())
        return []

    def new_card(self) -> None:
        self.card_path.unlink(missing_ok=True)

    def capture(self, path: Path) -> dict:
        from PIL import Image, ImageDraw, ImageFilter

        insects = self._load()
        for _ in range(self.rng.choice([0, 0, 1, 1, 2])):
            sp = self.rng.choice(list(self.SPECIES))
            insects.append(
                {
                    "species": sp,
                    "x": self.rng.uniform(0.12, 0.88) * self.WIDTH,
                    "y": self.rng.uniform(0.1, 0.9) * self.HEIGHT,
                    "angle": self.rng.uniform(0, 180),
                }
            )
        self.card_path.write_text(json.dumps(insects))

        img = Image.new("RGB", (self.WIDTH, self.HEIGHT), (236, 232, 205))
        d = ImageDraw.Draw(img)
        step = self.GRID_PX
        for x in range(0, self.WIDTH, step):
            d.line([(x, 0), (x, self.HEIGHT)], fill=(214, 210, 185), width=2)
        for y in range(0, self.HEIGHT, step):
            d.line([(0, y), (self.WIDTH, y)], fill=(214, 210, 185), width=2)
        cx, cy = self.WIDTH / 2, self.HEIGHT / 2
        d.rounded_rectangle([cx - 40, cy - 14, cx + 40, cy + 14], radius=8, fill=(170, 40, 40))  # lure
        for ins in insects:
            length, colour = self.SPECIES[ins["species"]]
            moth = Image.new("RGBA", (length * 2, length * 2), (0, 0, 0, 0))
            md = ImageDraw.Draw(moth)
            md.ellipse([length * 0.5, length * 0.75, length * 1.5, length * 1.25], fill=colour + (255,))
            moth = moth.rotate(ins["angle"], resample=Image.BICUBIC)
            img.paste(moth, (int(ins["x"] - length), int(ins["y"] - length)), moth)
        img = img.filter(ImageFilter.GaussianBlur(0.8))
        img.save(path, quality=int(self.cfg.get("jpeg_quality", 95)))
        return {
            "sensor": "fake",
            "width": self.WIDTH,
            "height": self.HEIGHT,
            "fake_truth": [{"species": i["species"], "x": i["x"], "y": i["y"]} for i in insects],
        }


def make_camera(cfg: dict, data_dir: Path):
    backend = cfg["camera"]["backend"]
    if backend == "picamera2":
        return Picamera2Camera(cfg["camera"])
    if backend == "usb":
        return UsbCamera(cfg["camera"])
    if backend == "fake":
        return FakeCamera(cfg["camera"], data_dir)
    raise ValueError(f"unknown camera backend {backend!r}")
