"""Stage 1: find every insect on the liner (species-agnostic).

`baseline` is a classical OpenCV detector (dark blobs on a pale liner). It
needs no model download, so the whole pipeline runs today on staged cards and
fake-camera photos. `flatbug` is the pretrained arthropod detector from the
architecture plan; it is used automatically when installed and selected with
SENTINEL_DETECTOR=flatbug.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class Box:
    x1: float
    y1: float
    x2: float
    y2: float
    conf: float

    @property
    def w(self) -> float:
        return self.x2 - self.x1

    @property
    def h(self) -> float:
        return self.y2 - self.y1

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2


def in_mask(box: Box, mask: list[list[float]], width: int, height: int) -> bool:
    for fx1, fy1, fx2, fy2 in mask or []:
        if fx1 * width <= box.cx <= fx2 * width and fy1 * height <= box.cy <= fy2 * height:
            return True
    return False


@dataclass
class Grid:
    """The liner's printed grid as seen in one photo."""

    angles: tuple[float, ...]  # degrees; line directions found (usually two, ~90° apart)
    pitch_px: float            # spacing between neighbouring lines, in working-image pixels
    score: float               # how strongly periodic the lines are (0 = no grid found)


class BaselineDetector:
    """Dark compact blobs on a liner, after removing the printed grid.

    Works on photos from any camera and trap colour:
    - darkness is measured on each pixel's brightest colour channel, so a tinted
      roof (the orange Pherocon VI turns everything orange) or coloured grid ink
      doesn't read as "dark";
    - uneven light and lens vignetting are divided out;
    - the grid is located (angle + spacing), which also gives the image scale, and
      its lines are subtracted, so an insect sitting on a line is still found;
    - blobs are kept by physical size in mm, not by pixel size.
    """

    version = "baseline-cv-0.3"
    WORK_MAX_SIDE = 1600

    def __init__(self, grid_mm: float = 25.4, min_len_mm: float = 3.0, max_len_mm: float = 30.0,
                 min_contrast: float = 0.20, fallback_liner_mm: float = 200.0, bg_object_mm: float = 15.0,
                 lens: str | float = "auto"):
        self.grid_mm = grid_mm
        # Barrel distortion bends the grid lines, which breaks grid finding and line removal.
        # "auto": estimated from the grid on a liner's first photo, then reused for that liner.
        self.lens = lens
        self._lens_cache: dict = {}
        self.min_len_mm = min_len_mm
        self.max_len_mm = max_len_mm
        self.min_contrast = min_contrast
        self.fallback_liner_mm = fallback_liner_mm
        self.bg_object_mm = bg_object_mm  # background estimate looks past dark things up to this size  # no grid found: assume the liner spans the image width
        self.last: dict = {}

    def detect(self, image_path: Path, key=None) -> list[Box]:
        """`key` names the camera + liner (e.g. (trap, card)): photos with the same key share a lens estimate."""
        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"cannot read image {image_path}")
        return self.detect_array(img, key)

    def lens_k(self, img: np.ndarray, key=None) -> float:
        if self.lens != "auto":
            return float(self.lens)
        if key is None:
            return estimate_lens_k(img)
        if key not in self._lens_cache:
            self._lens_cache[key] = estimate_lens_k(img)
        return self._lens_cache[key]

    def detect_array(self, img: np.ndarray, key=None) -> list[Box]:
        k = self.lens_k(img, key)
        if k == 0:
            boxes = self._detect(img)
        else:
            boxes = [distort_box(b, k, img.shape[1], img.shape[0]) for b in self._detect(undistort(img, k))]
        self.last["lens_k"] = k
        return boxes

    def _detect(self, img: np.ndarray) -> list[Box]:
        h0, w0 = img.shape[:2]
        f = min(1.0, self.WORK_MAX_SIDE / max(h0, w0))
        work = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA) if f < 1 else img
        h, w = work.shape[:2]

        v = cv2.GaussianBlur(work.max(axis=2).astype(np.float32), (3, 3), 0)
        grid = find_grid(work)
        if grid.score > 0:
            px_per_mm = grid.pitch_px / self.grid_mm
        else:
            px_per_mm = w / self.fallback_liner_mm
        dark = darkness(v, int(self.bg_object_mm * px_per_mm))
        lines = np.zeros_like(dark)
        if grid.score > 0:
            # Longer than any insect, shorter than a grid square: only lines survive the opening.
            length = int(max(self.max_len_mm * 0.6 * px_per_mm, 0.6 * grid.pitch_px))
            # Perspective and lens distortion fan the lines out, so try a spread of angles around
            # each grid direction. Safe for insects: none is `length` long in any direction.
            step = max(0.5, float(np.degrees(np.arctan(2.5 * px_per_mm * 0.8 / length))))
            for base in grid.angles:
                for angle in np.arange(base - 15, base + 15 + 1e-6, step):
                    lines = np.maximum(lines, line_opening(dark, float(angle), length))
        resid = np.clip(dark - lines, 0, 1)

        noise = 1.4826 * float(np.median(np.abs(resid - np.median(resid))))
        thresh = max(self.min_contrast, 6 * noise)
        binary = (resid > thresh).astype(np.uint8)
        k = max(3, int(0.6 * px_per_mm) | 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        min_len, max_len = self.min_len_mm * px_per_mm, self.max_len_mm * px_per_mm
        boxes = []
        for i in range(1, n):
            x, y, bw, bh, area = stats[i]
            if not (min_len <= max(bw, bh) <= max_len):
                continue
            if area < 0.25 * min_len * min_len:  # thin wisps: hairs, line fragments
                continue
            touches_edge = x <= 1 or y <= 1 or x + bw >= w - 1 or y + bh >= h - 1
            if touches_edge and min(bw, bh) < 0.35 * max(bw, bh):
                continue  # a grid line cut off by the photo edge; insects cut off by the edge are fatter
            contrast = float(resid[labels == i].mean())
            conf = float(np.clip(contrast * 2.0, 0.05, 0.99))
            pad = 0.15
            boxes.append(Box(
                max(0, x - pad * bw) / f, max(0, y - pad * bh) / f,
                min(w, x + bw * (1 + pad)) / f, min(h, y + bh * (1 + pad)) / f, conf,
            ))
        self.last = {"px_per_mm": px_per_mm / f, "grid": grid, "threshold": thresh, "work_scale": f}
        return boxes


def darkness(v: np.ndarray, object_px: int) -> np.ndarray:
    """0 on bare liner, towards 1 for dark things; divides out vignetting and uneven light."""
    h, w = v.shape
    s = max(1.0, max(h, w) / 320)  # estimate the background at low resolution: fast with big kernels
    small = cv2.resize(v, (max(8, int(w / s)), max(8, int(h / s))), interpolation=cv2.INTER_AREA)
    k = max(3, int(1.5 * object_px / s) | 1)
    bg = cv2.morphologyEx(small, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    bg = cv2.GaussianBlur(bg, (0, 0), k / 4)
    bg = cv2.resize(bg, (w, h), interpolation=cv2.INTER_LINEAR)
    return np.clip(1.0 - v / np.maximum(bg, 1.0), 0, 1)


def _rotate(a: np.ndarray, angle: float, size: tuple[int, int] | None = None, inverse_of=None) -> np.ndarray:
    h, w = a.shape[:2]
    if inverse_of is None:
        diag = int(np.ceil(np.hypot(h, w)))
        m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        m[:, 2] += ((diag - w) / 2, (diag - h) / 2)
        return cv2.warpAffine(a, m, (diag, diag), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    oh, ow = inverse_of
    m = cv2.getRotationMatrix2D((w / 2, h / 2), -angle, 1.0)
    m[:, 2] -= ((w - ow) / 2, (h - oh) / 2)
    return cv2.warpAffine(a, m, (ow, oh), flags=cv2.INTER_LINEAR)


def line_opening(dark: np.ndarray, angle: float, length: int) -> np.ndarray:
    """Dark structures that run straight for `length` px in direction `angle` (degrees, image x axis)."""
    rot = _rotate(dark, angle)  # lines at `angle` become horizontal
    opened = cv2.morphologyEx(rot, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (length, 1)))
    # a line may bend slightly (lens distortion): also accept it one pixel up or down
    opened = cv2.dilate(opened, np.ones((3, 1), np.uint8))
    return _rotate(opened, angle, inverse_of=dark.shape)


def find_grid(img: np.ndarray, min_score: float = 5.0) -> Grid:
    """Find the printed grid (angle + spacing) by projecting the image along every direction.

    `img` is BGR or single-channel. The grid ink can be nearly invisible in some colour
    channels (red ink under an orange roof), so each channel is tried and the clearest wins.
    """
    chans = [img] if img.ndim == 2 else [img[..., c] for c in range(img.shape[2])]
    best = Grid((), 0.0, 0.0)
    for ch in chans:
        if (ch >= 250).mean() > 0.9 or np.median(ch) < 15:
            continue  # clipped or black channel: JPEG noise there looks like lines
        g = _find_grid_1ch(ch.astype(np.float32), min_score)
        if g.pitch_px < 0.03 * max(ch.shape):  # finer than any real liner grid at our distances: noise
            continue
        if g.score > best.score:
            best = g
    return best


def _find_grid_1ch(v: np.ndarray, min_score: float) -> Grid:
    h, w = v.shape
    s = max(1.0, max(h, w) / 400)
    small = cv2.resize(v, (int(w / s), int(h / s)), interpolation=cv2.INTER_AREA)
    # high-pass: keep thin dark line structure, drop lighting gradients
    hp = np.clip(cv2.GaussianBlur(small, (0, 0), 5) - small, 0, None)
    hp /= float(np.percentile(hp, 99.5)) + 1e-6
    hh, ww = hp.shape
    ones = np.ones_like(hp)

    def profile(angle: float) -> np.ndarray:
        num = _rotate(hp, angle).sum(axis=1)
        den = _rotate(ones, angle).sum(axis=1)
        keep = den > 0.5 * min(hh, ww)  # only rows that cross enough of the photo
        return num[keep] / den[keep]

    def peakiness(p: np.ndarray) -> float:
        if p.size < 20:
            return 0.0
        med = np.median(p)
        mad = np.median(np.abs(p - med)) + 1e-6
        return float((np.percentile(p, 98) - med) / mad)

    coarse = np.arange(0, 180, 1.0)
    scores = np.array([peakiness(profile(a)) for a in coarse])

    def refine(a0: float) -> tuple[float, float]:
        fine = np.arange(a0 - 1, a0 + 1.01, 0.25)
        fs = [peakiness(profile(a)) for a in fine]
        i = int(np.argmax(fs))
        return float(fine[i]) % 180, float(fs[i])

    a1, s1 = refine(float(coarse[int(np.argmax(scores))]))
    if s1 < min_score:
        return Grid((), 0.0, 0.0)
    cand = [i for i, a in enumerate(coarse) if 60 <= (a - a1) % 180 <= 120]  # the other family, ~perpendicular
    angles = [a1]
    if cand:
        a2, s2 = refine(float(coarse[max(cand, key=lambda i: scores[i])]))
        if s2 >= min_score:
            angles.append(a2)

    pitches = [p for p in (_period(profile(a)) for a in angles) if p]
    if not pitches:
        return Grid((), 0.0, 0.0)
    return Grid(tuple(angles), float(np.median(pitches) * s), s1)


def _period(p: np.ndarray, min_lag: int = 6) -> float | None:
    """Spacing of a periodic profile: first clear peak of its autocorrelation."""
    x = p - p.mean()
    n = len(x)
    if n < 3 * min_lag:
        return None
    ac = np.correlate(x, x, mode="full")[n - 1:]
    ac /= ac[0] + 1e-9
    ac /= (n - np.arange(n)) / n  # unbiased: long lags have fewer overlapping samples
    for lag in range(min_lag, int(n * 0.7)):
        if ac[lag] > 0.25 and ac[lag] >= ac[lag - 1] and ac[lag] >= ac[lag + 1]:
            # sub-sample peak position
            d = ac[lag - 1] - 2 * ac[lag] + ac[lag + 1]
            return lag + (0.5 * (ac[lag - 1] - ac[lag + 1]) / d if d < 0 else 0.0)
    return None


# --- lens distortion -------------------------------------------------------------------------
# One-parameter radial model (OpenCV's k1): a point at normalised radius r from the photo centre
# is seen at r * (1 + k r^2), with r measured in half-diagonals, so k doesn't depend on resolution.
# k < 0 is barrel distortion (wide and fisheye lenses). A checkerboard calibration would give
# more terms; for finding insects on a grid, straight lines are what matters.

def _camera(w: int, h: int) -> np.ndarray:
    f = 0.5 * float(np.hypot(w, h))
    return np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], np.float64)


def undistort(img: np.ndarray, k: float) -> np.ndarray:
    """Straighten the photo. Same size and centre scale; the outermost corners are cropped."""
    h, w = img.shape[:2]
    cam = _camera(w, h)
    m1, m2 = cv2.initUndistortRectifyMap(cam, np.array([k, 0, 0, 0], np.float64), None, cam, (w, h), cv2.CV_32FC1)
    return cv2.remap(img, m1, m2, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def distort_points(pts: np.ndarray, k: float, w: int, h: int) -> np.ndarray:
    """Straightened-photo pixel coordinates (N×2) -> where they are in the original photo."""
    f = 0.5 * float(np.hypot(w, h))
    c = np.array([w / 2, h / 2])
    n = (np.asarray(pts, np.float64) - c) / f
    r2 = (n ** 2).sum(axis=1, keepdims=True)
    return n * (1 + k * r2) * f + c


def distort_box(b: Box, k: float, w: int, h: int) -> Box:
    xs, ys = (b.x1, b.cx, b.x2), (b.y1, b.cy, b.y2)
    p = distort_points(np.array([(x, y) for x in xs for y in ys]), k, w, h)
    return Box(float(max(0, p[:, 0].min())), float(max(0, p[:, 1].min())),
               float(min(w, p[:, 0].max())), float(min(h, p[:, 1].max())), b.conf)


LENS_K_RANGE = (-0.5, 0.1)


def estimate_lens_k(img: np.ndarray, min_gain: float = 1.25) -> float:
    """The k that makes the liner's grid lines straightest (0 if there is no grid or no clear gain).

    Straight, evenly spaced lines give sharp peaks when the photo is projected along them, so the
    grid score from find_grid peaks at the right k. Channels are summed: the grid shows best in
    different channels under different light. Takes a few seconds; the detector caches it per liner.
    """
    f = min(1.0, 640 / max(img.shape[:2]))
    small = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA) if f < 1 else img
    chans = [small] if small.ndim == 2 else [small[..., c] for c in range(small.shape[2])]
    chans = [c for c in chans if (c >= 250).mean() <= 0.9 and np.median(c) >= 5]
    if not chans:
        return 0.0

    def score(k: float) -> float:
        return sum(_find_grid_1ch(undistort(c, k).astype(np.float32), 5.0).score for c in chans)

    lo, hi = LENS_K_RANGE
    tried = {round(float(k), 4): score(float(k)) for k in np.arange(lo, hi + 1e-9, 0.05)}
    best = max(tried, key=tried.get)
    for k in (round(best - 0.025, 4), round(best + 0.025, 4)):
        if lo <= k <= hi:
            tried[k] = score(k)
    best = max(tried, key=tried.get)
    base = tried.get(0.0, 0.0)
    if tried[best] <= 0 or (best != 0 and tried[best] < min_gain * base):
        return 0.0
    return best


class FlatbugDetector:  # pragma: no cover - needs the flatbug package + weights
    """Pretrained arthropod detector (github.com/darsa-group/flat-bug), which tiles large images itself.

    API as used in flat-bug's examples/tutorials/deploy.ipynb: Predictor(device, dtype), then
    calling the model on an image path returns predictions with .boxes (N×4, xyxy px) and .confs (N).
    Weights (flat_bug_M.pt) download automatically on first use.
    """

    def __init__(self, weights: str | Path = "flat_bug_M.pt"):
        from flat_bug.predictor import Predictor  # type: ignore

        # flat-bug compares device strings exactly: tensors report "mps:0", not "mps"
        self.model = Predictor(model=str(weights), device="mps:0" if _has_mps() else "cpu", dtype="float32")
        self.version = f"flatbug-{Path(weights).stem}"

    def detect(self, image_path: Path, key=None) -> list[Box]:
        pred = self.model(str(image_path))
        boxes = pred.boxes.cpu().tolist() if hasattr(pred.boxes, "cpu") else list(pred.boxes)
        confs = pred.confs.cpu().tolist() if hasattr(pred.confs, "cpu") else list(pred.confs)
        return [Box(float(b[0]), float(b[1]), float(b[2]), float(b[3]), float(c)) for b, c in zip(boxes, confs)]


def _has_mps() -> bool:
    try:
        import torch

        return torch.backends.mps.is_available()
    except Exception:
        return False


def make_detector(name: str):
    from ..settings import get_settings

    s = get_settings()
    if name == "baseline":
        return BaselineDetector(grid_mm=s.grid_mm, lens=s.lens_k)
    if name == "flatbug":
        models = s.data_dir / "models"
        models.mkdir(parents=True, exist_ok=True)
        return FlatbugDetector(models / "flat_bug_M.pt")  # downloaded there on first use
    raise ValueError(f"unknown detector {name!r}")
