"""Printable calibration sheets (PNG at 300 dpi; print at 100 %):

  checkerboard.png   lens calibration (fixes the wide lens's barrel distortion)
  tray_markers.png   four ArUco markers for the liner-tray corners (alignment, scale, card-change checks)

    python make_markers.py --out print/

Needs OpenCV with the aruco module (opencv-python-headless >= 4.7, already in the server venv).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

DPI = 300
MM = DPI / 25.4
ARUCO_DICT = cv2.aruco.DICT_4X4_50
TRAY_IDS = (0, 1, 2, 3)  # top-left, top-right, bottom-right, bottom-left


def checkerboard(cols: int, rows: int, square_mm: float) -> np.ndarray:
    sq = round(square_mm * MM)
    margin = round(10 * MM)
    img = np.full((rows * sq + 2 * margin, cols * sq + 2 * margin + round(40 * MM)), 255, np.uint8)
    for r in range(rows):
        for c in range(cols):
            if (r + c) % 2 == 0:
                img[margin + r * sq : margin + (r + 1) * sq, margin + c * sq : margin + (c + 1) * sq] = 0
    cv2.putText(img, f"{cols}x{rows} squares, {square_mm:g} mm", (margin, img.shape[0] - round(3 * MM)),
                cv2.FONT_HERSHEY_SIMPLEX, 1.2, 0, 2)
    return img


def tray_markers(size_mm: float) -> np.ndarray:
    d = cv2.aruco.getPredefinedDictionary(ARUCO_DICT)
    px = round(size_mm * MM)
    pad = round(8 * MM)
    cell = px + 2 * pad
    sheet = np.full((2 * cell + round(15 * MM), 2 * cell), 255, np.uint8)
    for i, mid in enumerate(TRAY_IDS):
        m = cv2.aruco.generateImageMarker(d, mid, px)
        r, c = divmod(i, 2)
        y, x = r * cell + pad, c * cell + pad
        sheet[y : y + px, x : x + px] = m
        cv2.putText(sheet, f"id {mid}", (x, y + px + round(5 * MM)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 0, 2)
    cv2.putText(sheet, f"ArUco 4x4_50, {size_mm:g} mm. Glue to tray corners: 0 TL, 1 TR, 2 BR, 3 BL",
                (pad, sheet.shape[0] - round(4 * MM)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 0, 2)
    return sheet


def save(img: np.ndarray, path: Path) -> None:
    from PIL import Image

    Image.fromarray(img).save(path, dpi=(DPI, DPI))
    print(f"wrote {path} ({img.shape[1] / MM:.0f} × {img.shape[0] / MM:.0f} mm)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("print"))
    ap.add_argument("--square", type=float, default=12.0, help="checkerboard square size, mm")
    ap.add_argument("--marker", type=float, default=15.0, help="ArUco marker size, mm")
    args = ap.parse_args(argv)
    args.out.mkdir(parents=True, exist_ok=True)
    save(checkerboard(13, 9, args.square), args.out / "checkerboard.png")
    save(tray_markers(args.marker), args.out / "tray_markers.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
