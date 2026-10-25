"""Baseline detector on liners that look like the real trap: orange roof, red grid, perspective, vignetting."""

from pathlib import Path

import cv2
import numpy as np
import pytest

from sentinel_server.pipeline.detect import (
    BaselineDetector,
    Box,
    card_outline,
    distort_points,
    estimate_lens_k,
    find_grid,
    merge_tiles,
    on_card,
    tile_origins,
)

W, H = 640, 480
PX_PER_MM = 7.0
GRID_MM = 25.0


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


def total(boxes):
    return sum(b.n for b in boxes)


@pytest.mark.parametrize("pair,label", [
    (((300, 240, 10, 4, 0.35, 90), (329, 240, 10, 4, 0.35, 90)), "side by side, wings touching"),
    (((250, 240, 10, 4, 0.35, 0), (318, 240, 10, 4, 0.35, 0)), "end to end"),
    (((300, 240, 10, 4, 0.35, 60), (318, 250, 10, 4, 0.35, 120)), "crossed, overlapping"),
])
def test_touching_pair_counts_as_two(pair, label):
    boxes = BaselineDetector().detect_array(liner(list(pair), angle=0.0, keystone=0.0))
    assert total(boxes) == 2, f"{label}: {[(round(b.cx), round(b.cy), b.n) for b in boxes]}"


def test_single_moths_are_not_split():
    moths = [(130, 140, 10, 4, 0.35, 70), (500, 120, 12, 5, 0.55, 150), (330, 250, 6, 2.5, 0.35, 20)]
    boxes = BaselineDetector().detect_array(liner(moths, angle=4.0))
    assert len(boxes) == 3 and total(boxes) == 3


def test_clump_is_never_one_insect():
    """Four overlapping moths cover about three moths' area: area can't count them exactly, so
    the guarantee is only that a clump counts as more than one and goes to review (n > 1)."""
    clump = [(300 + dx, 240 + dy, 10, 4, 0.35, a) for dx, dy, a in
             [(0, 0, 90), (26, 0, 90), (13, 20, 0), (13, -22, 10)]]
    boxes = BaselineDetector().detect_array(liner(clump, angle=0.0, keystone=0.0))
    assert total(boxes) >= 2
    assert len(boxes) > 1 or boxes[0].n > 1


def barrel(img: np.ndarray, k: float) -> np.ndarray:
    """What a wide lens with distortion k would see of the flat scene `img`."""
    h, w = img.shape[:2]
    f = 0.5 * np.hypot(w, h)
    cam = np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], np.float64)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    pts = np.stack([xx.ravel(), yy.ravel()], axis=1).reshape(-1, 1, 2)
    src = cv2.undistortPoints(pts, cam, np.array([k, 0, 0, 0], np.float64), P=cam).reshape(h, w, 2)
    return cv2.remap(img, src[..., 0], src[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


INNER_MOTHS = MOTHS[:4]  # the edge moth is cropped away when a wide-lens photo is straightened


def test_lens_estimate_is_zero_for_a_straight_photo():
    assert estimate_lens_k(liner(angle=4.0, keystone=0.08)) == 0.0


@pytest.mark.parametrize("k", [-0.15, -0.3])
def test_wide_lens_liner(k):
    img = barrel(liner([*INNER_MOTHS, SPECK], angle=3.0, keystone=0.0, seed=4), k)
    assert estimate_lens_k(img) == pytest.approx(k, abs=0.05)
    det = BaselineDetector()
    boxes = det.detect_array(img)
    # boxes come back in the original (curved) photo's coordinates
    expected = distort_points(np.array([m[:2] for m in INNER_MOTHS], float), k, W, H)
    found = centres(boxes)
    for x, y in expected:
        assert near(found, x, y, tol=15), f"missed insect at {x:.0f},{y:.0f}"
    assert len(boxes) == len(INNER_MOTHS)
    assert det.last["px_per_mm"] == pytest.approx(PX_PER_MM, rel=0.1)


def test_fisheye_empty_liner_has_no_detections():
    img = barrel(liner(angle=-5.0, keystone=0.05, seed=4), -0.45)
    assert BaselineDetector().detect_array(img) == []
    assert BaselineDetector(lens=0).detect_array(img) != []  # uncorrected, bent grid lines read as insects


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("name,k", [("empty_liner_webcam.jpg", 0.0), ("empty_liner_wide.jpg", -0.2)])
def test_real_empty_liners(name, k):
    """Real trap photos (Sep 24 2026) of liners with nothing on them: USB webcam, and a wide lens."""
    det = BaselineDetector()
    assert det.detect(FIXTURES / name) == []
    assert det.last["lens_k"] == pytest.approx(k, abs=0.05)


def test_lens_estimate_is_cached_per_liner(monkeypatch):
    import sentinel_server.pipeline.detect as d

    calls = []
    monkeypatch.setattr(d, "estimate_lens_k", lambda img: calls.append(1) or 0.0)
    det = BaselineDetector()
    img = liner()
    det.detect_array(img, key=("T1", 1))
    det.detect_array(img, key=("T1", 1))
    det.detect_array(img, key=("T1", 2))
    assert len(calls) == 2


def test_boxes_off_the_card_are_ignored():
    """White card in a red trap, as the wide lens sees it from the peak: the walls are not catch."""
    img = np.zeros((480, 640, 3), np.uint8)
    img[:] = (20, 20, 220)  # red walls (BGR)
    cv2.rectangle(img, (120, 80), (520, 400), (235, 235, 235), -1)
    cv2.ellipse(img, (300, 240), (20, 8), 30, 0, 360, (60, 60, 60), -1)  # a moth on the card
    outline = card_outline(img)
    assert outline is not None
    boxes = [Box(280, 225, 320, 255, 0.9), Box(40, 200, 80, 230, 0.9), Box(121, 200, 141, 220, 0.9)]
    assert on_card(boxes, outline) == [boxes[0], boxes[2]]
    assert on_card(boxes, outline, margin_px=20) == [boxes[0]]  # the rim under the clips is not catch either


@pytest.mark.parametrize("name", ["empty_liner_webcam.jpg", "empty_liner_wide.jpg"])
def test_a_photo_that_is_all_liner_has_no_outline(name):
    """Under the roof's coloured light the whole photo is one colour: nothing may be thrown away."""
    assert card_outline(cv2.imread(str(Path(__file__).parent / "fixtures" / name))) is None
    assert card_outline(liner(MOTHS)) is None


def test_tiles_cover_the_photo_and_an_insect_cut_by_a_tile_edge_counts_once():
    origins = tile_origins(1500, 700, 640, 224)
    assert origins[0] == (0, 0) and max(x for x, _ in origins) == 1500 - 640 and max(y for _, y in origins) == 60
    whole, part = (600, 100, 680, 130, 0.9), (600, 100, 640, 130, 0.6)  # the next tile sees only half of it
    neighbour = (660, 110, 720, 140, 0.8)                               # a second moth touching the first
    assert merge_tiles([whole, part, neighbour], tiles=[1, 0, 1]) == [0, 2]
    assert merge_tiles([whole, part], tiles=[0, 0]) == [0, 1]  # within one tile the detector already chose


# The device's fake camera (sentinel_device.camera.FakeCamera): a faint grid every 290 px (11.6 px/mm) and
# large moths. These six are from an Oct 10 2026 end-to-end run whose photo read as 34.8 px/mm, after
# other photos of the same liner had read 29 and 6.9: the two line families gave different multiples of
# the spacing and were averaged.
FAKE_MOTHS = [(1228, 1031, 70, (90, 90, 90), 65), (1164, 396, 120, (150, 110, 70), 102), (1266, 374, 110, (95, 80, 70), 17),
              (376, 352, 50, (40, 40, 40), 141), (972, 793, 120, (150, 110, 70), 162), (1722, 469, 120, (150, 110, 70), 105)]


def fake_camera_liner() -> np.ndarray:
    from PIL import Image, ImageDraw, ImageFilter

    w, h, step = 2304, 1296, 290
    img = Image.new("RGB", (w, h), (236, 232, 205))
    d = ImageDraw.Draw(img)
    for x in range(0, w, step):
        d.line([(x, 0), (x, h)], fill=(214, 210, 185), width=2)
    for y in range(0, h, step):
        d.line([(0, y), (w, y)], fill=(214, 210, 185), width=2)
    d.rounded_rectangle([w / 2 - 40, h / 2 - 14, w / 2 + 40, h / 2 + 14], radius=8, fill=(170, 40, 40))
    for x, y, length, colour, angle in FAKE_MOTHS:
        moth = Image.new("RGBA", (length * 2, length * 2), (0, 0, 0, 0))
        ImageDraw.Draw(moth).ellipse([length * 0.5, length * 0.75, length * 1.5, length * 1.25], fill=colour + (255,))
        moth = moth.rotate(angle, resample=Image.BICUBIC)
        img.paste(moth, (x - length, y - length), moth)
    rgb = np.asarray(img.filter(ImageFilter.GaussianBlur(0.8)))
    ok, jpg = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 95])
    return cv2.imdecode(jpg, cv2.IMREAD_COLOR)


def test_grid_scale_on_the_fake_camera_liner():
    from sentinel_server.pipeline.detect import photo_scale

    ppm, _ = photo_scale(fake_camera_liner(), 25.0, 0.0)
    assert ppm == pytest.approx(290 / 25, rel=0.03)


def test_dark_frame_with_fine_banding_has_no_grid():
    """A night photo from an ESP32 with no light (T2, Oct 23 2026): dark, with faint fine banding that reads as
    two line families both closer than any real grid. It used to raise inside _agreed_pitch instead of
    coming back as no grid, so the capture got a traceback rather than "no liner grid found"."""
    img = np.full((1200, 1600), 30, np.uint8)
    img[::28, :] = 10
    img[:, ::44] = 10
    assert find_grid(img).pitch_px == 0.0
    assert find_grid(np.zeros((1200, 1600, 3), np.uint8)).pitch_px == 0.0  # all black


def test_line_families_agree_on_one_spacing():
    from sentinel_server.pipeline.detect import _agreed_pitch

    def lines(n, pitch, blobs=()):
        p = np.zeros(n)
        p[::pitch] = 1.0
        for i in blobs:  # insects: strong, wide, irregular
            p[i:i + 15] += 3.0
        return p

    across, down = lines(400, 50, blobs=(20, 140, 330)), lines(225, 50)
    assert _agreed_pitch([50.0, 51.0], [across, down]) == pytest.approx(50.5)  # agree: as before
    assert _agreed_pitch([200.0, 50.0], [across, down]) == pytest.approx(50)    # one a multiple
    assert _agreed_pitch([150.0, 100.0], [across, down]) == pytest.approx(50)   # both multiples
    assert _agreed_pitch([7.0, 11.0], [across, down]) == pytest.approx(9)      # all too fine: no raise


def test_grid_says_which_fraction_of_a_spacing_it_chose():
    """For the ⅓-scale misreads (L-01): a grid taken as a fraction of a measured spacing says which, so the
    failing photos show whether the fraction search is the cause."""
    from sentinel_server.pipeline.detect import _pitch_choice

    def lines(n, pitch):
        p = np.zeros(n)
        p[::pitch] = 1.0
        return p

    across, down = lines(400, 50), lines(225, 50)
    assert _pitch_choice([50.0, 51.0], [across, down]) == (pytest.approx(50.5), 1)
    assert _pitch_choice([200.0, 50.0], [across, down]) == (pytest.approx(50), 1)
    pitch, frac = _pitch_choice([150.0, 200.0], [across, down])
    assert pitch == pytest.approx(50) and frac in (3, 4)
    assert find_grid(cv2.cvtColor(liner(), cv2.COLOR_BGR2GRAY)).fraction == 1
