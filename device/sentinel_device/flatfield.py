"""Even out colour and brightness across the photo using one picture of a blank white card.

A wide-angle lens on a sensor tuned for its stock lens gives a green centre and pink edges, and
the LEDs light the middle of the liner more than the corners. Photograph a blank white card in
the trap once (`sentinel-flatfield`); every later photo is multiplied by the gain map made from
it, so a white card comes out white and evenly lit everywhere.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

FILENAME = "flatfield.npz"
GRID = (48, 64)          # rows, cols of the gain map; smooth enough to ignore grid lines and specks
MAX_GAIN = 4.0           # outside the card (trap walls) the map would explode; cap it


def build(white: np.ndarray, grid: tuple[int, int] = GRID) -> np.ndarray:
    """Gain map (rows, cols, 3) from an RGB photo of a blank white card.

    Each cell is the median of its block, so printed grid lines and dust don't dent the map.
    The target is the centre's brightness, in neutral grey.
    """
    rows, cols = grid
    h, w = white.shape[:2]
    bh, bw = h // rows, w // cols
    if bh < 1 or bw < 1:
        raise ValueError(f"photo {w}x{h} is too small for a {cols}x{rows} map")
    flat = np.empty((rows, cols, 3), dtype=np.float32)
    for c in range(3):
        blocks = white[: rows * bh, : cols * bw, c].reshape(rows, bh, cols, bw).transpose(0, 2, 1, 3)
        flat[..., c] = np.median(blocks.reshape(rows, cols, bh * bw), axis=2)
    centre = flat[rows // 2 - 2 : rows // 2 + 2, cols // 2 - 2 : cols // 2 + 2]
    target = float(centre.mean())
    return np.clip(target / np.maximum(flat, 1.0), 1.0 / MAX_GAIN, MAX_GAIN).astype(np.float32)


def apply(img: Image.Image, gain: np.ndarray) -> Image.Image:
    """Multiply an RGB image by the gain map (stretched to the image's size)."""
    img = img.convert("RGB")
    out = []
    for c, band in enumerate(img.split()):
        g = Image.fromarray(gain[..., c], mode="F").resize(img.size, Image.BILINEAR)
        out.append(Image.fromarray(np.clip(np.asarray(band, dtype=np.float32) * np.asarray(g), 0, 255).astype(np.uint8)))
    return Image.merge("RGB", out)


def save(data_dir: Path, gain: np.ndarray, **info) -> Path:
    path = Path(data_dir) / FILENAME
    np.savez(path, gain=gain, **{k: np.asarray(v) for k, v in info.items()})
    return path


def load(data_dir: Path) -> np.ndarray | None:
    path = Path(data_dir) / FILENAME
    if not path.exists():
        return None
    with np.load(path) as f:
        return f["gain"].astype(np.float32)
