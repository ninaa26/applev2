"""Find the fixed lens position for this trap's mount height.

Put a liner (ideally with a few insects or a printed pattern) in the trap,
then run on the Pi:

    sentinel-focus-sweep --config /etc/sentinel/config.toml --out /tmp/focus

It photographs the liner at a range of lens positions with the LEDs on, scores
sharpness (variance of the Laplacian) in the centre and the four corners, and
prints the best position. Put that number in [camera] lens_position.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

from .. import config as config_mod, hardware
from ..camera import Picamera2Camera


def sharpness(gray: np.ndarray) -> float:
    lap = -4 * gray[1:-1, 1:-1] + gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:]
    return float(lap.var())


def regions(gray: np.ndarray, frac: float = 0.2) -> dict[str, np.ndarray]:
    h, w = gray.shape
    rh, rw = int(h * frac), int(w * frac)
    cy, cx = h // 2, w // 2
    return {
        "centre": gray[cy - rh // 2 : cy + rh // 2, cx - rw // 2 : cx + rw // 2],
        "top_left": gray[:rh, :rw],
        "top_right": gray[:rh, -rw:],
        "bottom_left": gray[-rh:, :rw],
        "bottom_right": gray[-rh:, -rw:],
    }


def score_image(path: Path) -> dict[str, float]:
    gray = np.asarray(Image.open(path).convert("L"), dtype=np.float32)
    return {name: sharpness(r) for name, r in regions(gray).items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=Path("/tmp/focus_sweep"))
    ap.add_argument("--start", type=float, default=3.0, help="dioptres (1/m); 3 = 33 cm")
    ap.add_argument("--stop", type=float, default=12.0, help="dioptres; 12 = 8 cm")
    ap.add_argument("--step", type=float, default=0.5)
    args = ap.parse_args(argv)

    cfg = config_mod.load(args.config)
    args.out.mkdir(parents=True, exist_ok=True)
    results = []
    with hardware.led(cfg["led"]["enabled"], cfg["led"]["gpio"]):
        for pos in np.arange(args.start, args.stop + 1e-9, args.step):
            cam_cfg = dict(cfg["camera"], lens_position=float(pos))
            path = args.out / f"lens_{pos:05.2f}.jpg"
            Picamera2Camera(cam_cfg).capture(path)
            s = score_image(path)
            results.append((float(pos), s))
            print(f"lens {pos:5.2f}  centre {s['centre']:9.1f}  worst corner {min(v for k, v in s.items() if k != 'centre'):9.1f}")

    # Best = highest worst-region score, so the whole liner is acceptably sharp, not just the middle.
    best_pos, best = max(results, key=lambda r: min(r[1].values()))
    print(f"\nBest lens_position = {best_pos:.2f}  (≈ {100 / best_pos:.1f} cm to the liner)")
    print("Put this in [camera] lens_position. Images are in", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
