"""Calibrate colour and lighting from a blank white card. Run once per trap, on the Pi.

Put a blank white card (plain paper cut to the liner's size, or an unused liner) on the trap
floor, close the trap as it will hang, then:

    sentinel-flatfield --config /etc/sentinel/config.toml

It photographs the card with the LEDs on and the settings from [camera], then
- says whether exposure_us is too high or too low,
- prints the colour_gains that make the card neutral (put them in [camera] and run it again),
- writes flatfield.npz into data_dir; from then on every photo is evened out with it.

Redo it after changing the LEDs, the camera, its height, exposure_us or colour_gains.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

from .. import config as config_mod, flatfield, hardware
from ..camera import make_camera


def report(white: np.ndarray, colour_gains: tuple[float, float]) -> list[str]:
    """Advice on exposure and white balance from the centre of the white-card photo."""
    h, w = white.shape[:2]
    centre = white[h * 2 // 5 : h * 3 // 5, w * 2 // 5 : w * 3 // 5].reshape(-1, 3).astype(np.float32)
    r, g, b = centre.mean(axis=0)
    clipped = float((white >= 254).any(axis=2).mean())
    lines = [f"Centre of the card: R {r:.0f}  G {g:.0f}  B {b:.0f} (of 255); {clipped:.1%} of the photo is blown out."]
    if clipped > 0.01 or max(r, g, b) > 235:
        lines.append("Too bright: lower exposure_us by about a third and run again.")
    elif max(r, g, b) < 140:
        lines.append(f"Too dark: raise exposure_us by about {min(4.0, 190 / max(r, g, b, 1)):.1f}x and run again.")
    else:
        lines.append("Exposure is fine.")
    if min(r, g, b) < 0.25 * max(r, g, b):
        lines.append("One colour is nearly missing: the light is coming through the coloured roof, not from the "
                     "white LEDs. Check the LEDs are on and block daylight before trusting the numbers below.")
    new = (colour_gains[0] * g / max(r, 1), colour_gains[1] * g / max(b, 1))
    if max(abs(g / max(r, 1) - 1), abs(g / max(b, 1) - 1)) > 0.05:
        lines.append(f"White balance: set colour_gains = [{new[0]:.2f}, {new[1]:.2f}] and run again.")
    else:
        lines.append("White balance is fine.")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=None)
    ap.add_argument("--shots", type=int, default=3, help="photos to average")
    ap.add_argument("--keep", type=Path, default=None, help="also save the averaged white-card photo here")
    args = ap.parse_args(argv)

    cfg = config_mod.load(args.config)
    data_dir = Path(cfg["data_dir"])
    data_dir.mkdir(parents=True, exist_ok=True)
    raw_cfg = dict(cfg, camera=dict(cfg["camera"], flat_field=False))  # photograph the card uncorrected
    total = None
    with hardware.led(cfg["led"]["enabled"], cfg["led"]["gpio"]):
        for i in range(args.shots):
            tmp = data_dir / f"flatfield_shot{i}.jpg"
            make_camera(raw_cfg, data_dir).capture(tmp)
            shot = np.asarray(Image.open(tmp).convert("RGB"), dtype=np.float32)
            total = shot if total is None else total + shot
            tmp.unlink()
    white = (total / args.shots).astype(np.uint8)
    if args.keep:
        Image.fromarray(white).save(args.keep, quality=95)

    gains = tuple(float(g) for g in cfg["camera"]["colour_gains"])
    for line in report(white, gains):
        print(line)
    gain = flatfield.build(white)
    path = flatfield.save(data_dir, gain, exposure_us=cfg["camera"]["exposure_us"], colour_gains=gains)
    print(f"Corner correction up to {gain.max():.1f}x. Saved {path}; photos are evened out with it from now on.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
