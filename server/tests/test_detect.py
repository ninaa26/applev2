"""Baseline detector on liners that look like the real trap: orange roof, red grid, perspective, vignetting."""

import cv2
import numpy as np
import pytest

from sentinel_server.pipeline.detect import BaselineDetector, find_grid

W, H = 640, 480
PX_PER_MM = 7.0
GRID_MM = 25.4


def liner(moths=(), angle=4.0, keystone=0.08, seed=0) -> np.ndarray:
    """BGR photo of a gridded liner under orange light, like the USB webcam in the orange Pherocon VI."""
    rng = np.random.default_rng(seed)
    big = 2 * max(W, H)
    flat = np.full((big, big), 1.0, np.float32)  # reflectance, liner coordinates
    pitch = int(GRID_MM * PX_PER_MM)
    ink = np.zeros_like(flat)
    for k in range(0, big, pitch):
        cv2.line(ink, (k, 0), (k, big), 1.0, 5)
        cv2.line(ink, (0, k), (big, k), 1.0, 5)
    # perspective: the far side of the liner looks narrower
    src = np.float32([[0, 0], [big, 0], [big, big], [0, big]])
    k = keystone * big
    dst = np.float32([[k, 0], [big - k, 0], [big, big], [0, big]])
    m = cv2.getPerspectiveTransform(src, dst)
    r = cv2.getRotationMatrix2D((big / 2, big / 2), angle, 1.0)
    m = np.vstack([r, [0, 0, 1]]) @ m
    m[:2, 2] -= ((big - W) / 2, (big - H) / 2)
    ink = cv2.warpPerspective(ink, m, (W, H))
    refl = np.ones((H, W), np.float32)
    for cx, cy, length_mm, width_mm, dark, ang in moths:
        mask = np.zeros((H, W), np.float32)
        axes = (int(length_mm * PX_PER_MM / 2), int(width_mm * PX_PER_MM / 2))
        cv2.ellipse(mask, (int(cx), int(cy)), axes, ang, 0, 360, 1.0, -1)
        mask = cv2.GaussianBlur(mask, (0, 0), 1.0)
        refl = refl * (1 - mask) + mask * dark
    # white liner, red ink (keeps red, loses green/blue)
    b = refl * (1 - 0.9 * ink)
    g = refl * (1 - 0.6 * ink)
    rch = refl * (1 - 0.1 * ink)
    # orange light, brighter in the middle (corners ~0.65 of centre, as measured on the webcam)
    yy, xx = np.mgrid[0:H, 0:W]
    vig = 1 - 0.18 * (((xx - W / 2) / W) ** 2 + ((yy - H / 2) / H) ** 2) * 4
    light = np.array([25, 110, 230], np.float32)
    img = np.stack([b, g, rch], axis=-1) * light * vig[..., None]
    img += rng.normal(0, 3, img.shape)
    ok, buf = cv2.imencode(".jpg", np.clip(img, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 92])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


MOTHS = [
    # x, y, length mm, width mm, reflectance, angle
    (130, 140, 10, 4, 0.35, 70),   # codling moth
    (330, 250, 6, 2.5, 0.35, 20),  # oriental fruit moth
    (500, 120, 10, 5, 0.55, 150),  # obliquebanded leafroller (tan, lighter)
    (220, 380, 4, 2, 0.25, 90),    # small fly
    (20, 250, 10, 4, 0.35, 5),     # cut off by the photo edge
]
SPECK = (450, 380, 1, 1, 0.3, 0)   # dust: too small to count


def centres(boxes):
    return [(b.cx, b.cy) for b in boxes]


def near(found, x, y, tol=25):
    return any(abs(fx - x) < tol and abs(fy - y) < tol for fx, fy in found)


def test_grid_gives_scale_and_angles():
    g = find_grid(liner(angle=4.0, keystone=0.0))
    assert g.score > 0
    assert g.pitch_px == pytest.approx(GRID_MM * PX_PER_MM, rel=0.05)
    # one line family is tilted 4° from the image axes (sign depends on the y-down convention)
    assert any(abs((abs(a) + 45) % 90 - 45 - 4) < 1.5 or abs((abs(a) + 45) % 90 - 45 + 4) < 1.5 for a in g.angles)


@pytest.mark.parametrize("angle,keystone", [(0.0, 0.0), (4.0, 0.08), (-8.0, 0.12)])
def test_empty_liner_has_no_detections(angle, keystone):
    assert BaselineDetector().detect_array(liner(angle=angle, keystone=keystone)) == []


@pytest.mark.parametrize("seed,angle", [(1, 0.0), (2, 4.0), (3, -8.0)])
def test_finds_each_insect_once_and_ignores_dust(seed, angle):
    det = BaselineDetector()
    boxes = det.detect_array(liner([*MOTHS, SPECK], angle=angle, seed=seed))
    found = centres(boxes)
    for x, y, *_ in MOTHS:
        assert near(found, x, y), f"missed insect at {x},{y}"
    assert not near(found, SPECK[0], SPECK[1]), "counted a dust speck"
    assert len(boxes) == len(MOTHS)
    assert det.last["px_per_mm"] == pytest.approx(PX_PER_MM, rel=0.1)


def test_insect_on_a_grid_line_is_found():
    pitch = int(GRID_MM * PX_PER_MM)
    offset = (2 * max(W, H) - W) / 2  # liner() draws on a bigger canvas centred on the photo
    x_line = min((k * pitch - offset for k in range(20)), key=lambda x: abs(x - W / 2))
    on_line = (x_line, H / 2, 9, 4, 0.35, 88)  # lies along a vertical grid line
    img = liner([on_line], angle=0.0, keystone=0.0)
    assert near(centres(BaselineDetector().detect_array(img)), on_line[0], on_line[1])
