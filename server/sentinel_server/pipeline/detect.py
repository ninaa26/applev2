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


class BaselineDetector:
    version = "baseline-cv-0.1"

    def __init__(self, min_len_frac: float = 0.008, max_area_frac: float = 0.02):
        # Smallest insect we care about, as a fraction of image width (OFM ≈ 0.02 at our geometry).
        self.min_len_frac = min_len_frac
        self.max_area_frac = max_area_frac

    def detect(self, image_path: Path) -> list[Box]:
        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"cannot read image {image_path}")
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        block = max(31, (w // 40) | 1)
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, block, 25)
        k = max(3, int(w * 0.002) | 1)  # removes printed grid lines, keeps bodies
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

        n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        min_len = self.min_len_frac * w
        boxes = []
        bg = float(np.median(gray))
        for i in range(1, n):
            x, y, bw, bh, area = stats[i]
            if max(bw, bh) < min_len or area > self.max_area_frac * w * h:
                continue
            region = gray[y : y + bh, x : x + bw][labels[y : y + bh, x : x + bw] == i]
            contrast = (bg - float(region.mean())) / max(bg, 1.0)
            conf = float(np.clip(contrast * 2.0, 0.05, 0.99))
            pad = 0.15
            boxes.append(
                Box(
                    max(0, x - pad * bw), max(0, y - pad * bh),
                    min(w, x + bw * (1 + pad)), min(h, y + bh * (1 + pad)), conf,
                )
            )
        return boxes


class FlatbugDetector:  # pragma: no cover - needs the flatbug package + weights
    """Pretrained arthropod detector (github.com/darsa-group/flat-bug), which tiles large images itself.

    API as used in flat-bug's examples/tutorials/deploy.ipynb: Predictor(device, dtype), then
    calling the model on an image path returns predictions with .boxes (N×4, xyxy px) and .confs (N).
    Weights (flat_bug_M.pt) download automatically on first use.
    """

    def __init__(self, weights: str = "flat_bug_M.pt"):
        from flat_bug.predictor import Predictor  # type: ignore

        self.model = Predictor(model=weights, device="mps" if _has_mps() else "cpu", dtype="float32")
        self.version = f"flatbug-{Path(weights).stem}"

    def detect(self, image_path: Path) -> list[Box]:
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
    if name == "baseline":
        return BaselineDetector()
    if name == "flatbug":
        return FlatbugDetector()
    raise ValueError(f"unknown detector {name!r}")
