"""Score candidate cameras on the same printed checkerboard so we can pick one.

Print hardware/print/checkerboard.png at 100 % (13 x 9 squares of 12 mm; check
one square with a ruler), lay it flat where the liner would sit, and hold the
camera at trap height (150 mm lens-to-card by default). Then, per camera:

    sentinel-camera-bench shoot --camera brio101 --backend usb --device 0
    sentinel-camera-bench shoot --camera cm3wide --backend picamera2
    sentinel-camera-bench score --camera phone --image IMG_0412.jpg   # any photo
    sentinel-camera-bench compare

`shoot` captures at the camera's largest size; `score` measures a photo taken
some other way (Photo Booth, a phone, libcamera-still). Add `--tag corner` for a
second shot with the board in a corner of the frame to check edge sharpness.

What is measured, from the checkerboard alone (so the exact height doesn't matter):
  px/mm           pixels per millimetre on the card: nominal detail
  OFM px          pixels along a 6 mm oriental fruit moth, the smallest target
  edge blur       10-90 % width of the black/white edges, in mm: real detail after
                  focus, lens and compression. Needs to be well under ~0.3 mm to
                  see wing pattern; a fixed-focus webcam too close shows up here
  contrast/noise  (white - black) / noise inside the squares: low-light quality
  field of view   mm of card covered at this height, and whether the liner fits
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .focus_sweep import sharpness

BOARD_SQUARES = (13, 9)  # as printed by hardware/make_markers.py
INNER = (BOARD_SQUARES[0] - 1, BOARD_SQUARES[1] - 1)
OFM_MM = 6.0  # body length of an oriental fruit moth at rest
USB_SIZES = [(3840, 2160), (2592, 1944), (2560, 1440), (2304, 1296), (1920, 1080), (1600, 1200),
             (1280, 960), (1280, 720), (1024, 768), (800, 600), (640, 480)]


def _cv2():
    try:
        import cv2  # type: ignore
    except ImportError:
        sys.exit("OpenCV is needed: on the Pi `sudo apt install python3-opencv`; "
                 "on a Mac `uv run --with opencv-python sentinel-camera-bench ...`")
    return cv2


# ---------------------------------------------------------------- capture

def shoot_usb(device: str, out: Path, warmup: int = 20) -> dict:
    """Largest size the webcam delivers, MJPEG so big frames don't drop to a few fps."""
    cv2 = _cv2()
    api = cv2.CAP_AVFOUNDATION if platform.system() == "Darwin" else cv2.CAP_V4L2
    cap = cv2.VideoCapture(int(device) if device.isdigit() else device, api)
    if not cap.isOpened():
        hint = " (macOS: allow your terminal app under Privacy & Security > Camera)" if api == cv2.CAP_AVFOUNDATION else ""
        sys.exit(f"cannot open camera {device}{hint}")
    try:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        for w, h in USB_SIZES:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
            ok, frame = cap.read()
            if ok and frame.shape[1] == w and frame.shape[0] == h:
                break
        # Let auto exposure / focus settle, then time a burst for the achievable frame rate.
        for _ in range(warmup):
            ok, frame = cap.read()
        t0, n = time.monotonic(), 0
        while time.monotonic() - t0 < 1.0:
            n += cap.read()[0]
        fps = n / (time.monotonic() - t0)
        ok, frame = cap.read()
        if not ok:
            sys.exit("camera returned no frame")
        cv2.imwrite(str(out), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
    finally:
        cap.release()
    return {"backend": "usb", "device": device, "stream_fps": round(fps, 1)}


def shoot_picamera2(out: Path, lens_position: float | None) -> dict:
    """Full sensor still; autofocus once unless a lens position is given."""
    from libcamera import controls  # type: ignore
    from picamera2 import Picamera2  # type: ignore

    cam = Picamera2()
    try:
        cam.configure(cam.create_still_configuration(main={"size": cam.sensor_resolution}))
        cam.options["quality"] = 95
        cam.start()
        if lens_position is None and "AfMode" in cam.camera_controls:
            cam.autofocus_cycle()
        elif lens_position is not None:
            cam.set_controls({"AfMode": controls.AfModeEnum.Manual, "LensPosition": lens_position})
        time.sleep(2)
        md = cam.capture_file(str(out))
        cam.stop()
    finally:
        cam.close()
    return {"backend": "picamera2", "model": cam.camera_properties.get("Model"),
            "lens_position": md.get("LensPosition"), "exposure_us": md.get("ExposureTime"),
            "analogue_gain": md.get("AnalogueGain")}


# ---------------------------------------------------------------- scoring

def _edge_widths(gray: np.ndarray, corners: np.ndarray) -> list[float]:
    """10-90 % rise distance (px) across each checkerboard edge, sampled perpendicular at its midpoint."""
    cv2 = _cv2()
    grid = corners.reshape(INNER[1], INNER[0], 2)
    widths = []
    for a, b in [(grid[r, c], grid[r, c + 1]) for r in range(INNER[1]) for c in range(INNER[0] - 1)] + \
                [(grid[r, c], grid[r + 1, c]) for r in range(INNER[1] - 1) for c in range(INNER[0])]:
        seg = b - a
        length = float(np.hypot(*seg))
        normal = np.array([-seg[1], seg[0]]) / length
        t = np.arange(-0.35 * length, 0.35 * length, 0.1, dtype=np.float32)
        # Average parallel profiles along the middle half of the edge so sensor noise cancels out.
        along = np.linspace(-0.25, 0.25, 15, dtype=np.float32)[:, None, None] * seg
        pts = ((a + b) / 2 + t[:, None] * normal)[None] + along
        prof = cv2.remap(gray, pts[..., 0].astype(np.float32), pts[..., 1].astype(np.float32),
                         cv2.INTER_LINEAR).mean(axis=0)
        lo, hi = np.percentile(prof, 5), np.percentile(prof, 95)
        if hi - lo < 20:
            continue
        if prof[0] > prof[-1]:
            prof = prof[::-1]
        norm = (prof - lo) / (hi - lo)
        i10, i90 = np.argmax(norm >= 0.1), np.argmax(norm >= 0.9)
        if i90 > i10:
            widths.append(float(t[i90] - t[i10]))
    return widths


def _contrast_noise(gray: np.ndarray, corners: np.ndarray) -> float:
    """Mean white-minus-black level over the pixel noise inside the squares."""
    grid = corners.reshape(INNER[1], INNER[0], 2)
    means, noise = {0: [], 1: []}, []
    for r in range(INNER[1] - 1):
        for c in range(INNER[0] - 1):
            quad = np.array([grid[r, c], grid[r, c + 1], grid[r + 1, c + 1], grid[r + 1, c]])
            cx, cy = quad.mean(axis=0)
            half = 0.25 * float(np.hypot(*(grid[r, c + 1] - grid[r, c])))
            patch = gray[int(cy - half):int(cy + half), int(cx - half):int(cx + half)]
            if patch.size < 16:
                continue
            means[(r + c) % 2].append(patch.mean())
            noise.append(patch.std())
    diff = abs(np.mean(means[0]) - np.mean(means[1]))
    return float(diff / max(np.median(noise), 0.5))


def score(image: Path, liner_mm: tuple[float, float]) -> dict:
    cv2 = _cv2()
    bgr = cv2.imread(str(image))
    if bgr is None:
        sys.exit(f"cannot read {image}")
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    res = {"image": str(image), "width": w, "height": h, "megapixels": round(w * h / 1e6, 2),
           "centre_sharpness": round(sharpness(gray[h // 3:2 * h // 3, w // 3:2 * w // 3].astype(np.float32)), 1)}
    found, corners = cv2.findChessboardCornersSB(gray, INNER, flags=cv2.CALIB_CB_EXHAUSTIVE | cv2.CALIB_CB_ACCURACY)
    if not found:
        res["error"] = (f"checkerboard ({INNER[0]}x{INNER[1]} inner corners) not found: "
                        "whole board in frame, flat, evenly lit, no glare?")
        return res
    corners = corners.reshape(-1, 2)
    grid = corners.reshape(INNER[1], INNER[0], 2)
    square_px = float(np.median(np.concatenate([
        np.hypot(*np.moveaxis(np.diff(grid, axis=1), -1, 0)).ravel(),
        np.hypot(*np.moveaxis(np.diff(grid, axis=0), -1, 0)).ravel()])))
    square_mm = 12.0
    px_per_mm = square_px / square_mm
    widths = _edge_widths(gray.astype(np.float32), corners)
    blur_px = float(np.median(widths)) if widths else float("nan")
    fov = (w / px_per_mm, h / px_per_mm)
    fits = max(fov) >= max(liner_mm) and min(fov) >= min(liner_mm)
    res.update({
        "px_per_mm": round(px_per_mm, 2),
        "ofm_px": round(OFM_MM * px_per_mm),
        "edge_blur_px": round(blur_px, 2),
        "edge_blur_mm": round(blur_px / px_per_mm, 3),
        "contrast_noise": round(_contrast_noise(gray.astype(np.float32), corners), 1),
        "fov_mm": [round(fov[0]), round(fov[1])],
        "liner_fits": bool(fits),
        "board_centre_frac": [round(float(corners[:, 0].mean()) / w, 2), round(float(corners[:, 1].mean()) / h, 2)],
    })
    return res


# ---------------------------------------------------------------- report

def compare(out: Path) -> str:
    rows = [json.loads(p.read_text()) for p in sorted(out.glob("*/*.json"))]
    if not rows:
        return f"no results in {out}"
    head = ["camera", "tag", "size", "MP", "px/mm", "OFM px", "edge blur mm", "contrast/noise", "FOV mm", "liner fits", "fps"]
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        s = r["score"]
        if "error" in s:
            lines.append(f"| {r['camera']} | {r['tag']} | {s['width']}x{s['height']} | {s['megapixels']} | "
                         + " | ".join(["—"] * 5) + f" | — | {r.get('capture', {}).get('stream_fps', '')} |")
            continue
        lines.append(" | ".join([
            f"| {r['camera']}", r["tag"], f"{s['width']}x{s['height']}", str(s["megapixels"]), str(s["px_per_mm"]),
            str(s["ofm_px"]), str(s["edge_blur_mm"]), str(s["contrast_noise"]), f"{s['fov_mm'][0]}x{s['fov_mm'][1]}",
            "yes" if s["liner_fits"] else "NO", f"{r.get('capture', {}).get('stream_fps', '')} |"]))
    lines.append("\nHigher px/mm, OFM px and contrast/noise are better; lower edge blur is better. "
                 "Edge blur much larger than 1/px_per_mm means the camera is out of focus at this distance.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("shoot", "score"):
        p = sub.add_parser(name)
        p.add_argument("--camera", required=True, help="short name, e.g. brio101")
        p.add_argument("--tag", default="centre", help="shot label, e.g. centre / corner / dim")
        p.add_argument("--distance-mm", type=float, default=150, help="lens to card (recorded only)")
        p.add_argument("--liner", default="180x180", help="liner WxL in mm, for the fits-in-view check")
        p.add_argument("--out", type=Path, default=Path("camera_bench"))
        if name == "shoot":
            p.add_argument("--backend", choices=["usb", "picamera2"], required=True)
            p.add_argument("--device", default="0", help="usb: index (Mac) or /dev/video path (Pi)")
            p.add_argument("--lens-position", type=float, default=None, help="picamera2: dioptres; default autofocus")
        else:
            p.add_argument("--image", type=Path, required=True)
    p = sub.add_parser("compare")
    p.add_argument("--out", type=Path, default=Path("camera_bench"))
    args = ap.parse_args(argv)

    if args.cmd == "compare":
        print(compare(args.out))
        return 0

    folder = args.out / args.camera
    folder.mkdir(parents=True, exist_ok=True)
    capture: dict = {}
    if args.cmd == "shoot":
        image = folder / f"{args.tag}.jpg"
        capture = (shoot_usb(args.device, image) if args.backend == "usb"
                   else shoot_picamera2(image, args.lens_position))
    else:
        image = args.image
    liner = tuple(float(v) for v in args.liner.lower().split("x"))
    result = {"camera": args.camera, "tag": args.tag, "distance_mm": args.distance_mm,
              "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "capture": capture, "score": score(image, liner)}
    (folder / f"{args.tag}.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result["score"], indent=2))
    return 1 if "error" in result["score"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
