"""Camera backends.

`Picamera2Camera` runs on the Pi with the Camera Module 3 Wide, with focus,
exposure and white balance all locked so every photo of the liner looks the same.
`FakeCamera` renders a synthetic sticky liner that slowly collects "moths", so
the whole pipeline (upload, detection, tracking, counting) can be tested on a
laptop before the hardware is ready.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path


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


class FakeCamera:
    """Synthetic liner: pale card, grid lines, a lure in the middle, and moths that accumulate."""

    WIDTH, HEIGHT = 2304, 1296
    SPECIES = {  # rough body length in px at this resolution, and a colour
        "CM": (70, (95, 80, 70)),
        "OBLR": (80, (150, 110, 70)),
        "OFM": (42, (90, 90, 90)),
        "other": (35, (40, 40, 40)),
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
        step = 60
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
    if backend == "fake":
        return FakeCamera(cfg["camera"], data_dir)
    raise ValueError(f"unknown camera backend {backend!r}")
