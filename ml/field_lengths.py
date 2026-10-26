"""Insect lengths on field-card photos, from a mask of the insect (numpy only, so tests need no cv2).

Two lengths per insect, both in mm at the insect's px/mm:
  length_mm  the long side of the smallest rotated rectangle around the whole outline (legs, antennae
             and spread wings included). It is what make_trap_style.py scales the cutout by.
  body_mm    the same insect with the thin parts trimmed off along its long axis (legs, antennae, a
             grid line the outline ran into): closer to the resting length in LENGTH_MM.
`length_from` says where length_mm came from: `outline`, or `box` when no usable outline was found
and the length is the box's long side (short for a slim diagonal insect, down to 0.71x at 45 degrees;
long for a wide one or a loosely drawn box).
"""

from __future__ import annotations

import numpy as np

BODY_FRAC = 0.25  # a slice along the long axis narrower than this fraction of the widest is a leg or antenna
MIN_FILL = 0.15  # an outline covering less of its box than this is a fragment, not the insect
MIN_SPAN = 0.6  # ... and so is one shorter than this fraction of the box's long side
SCALE_MM = (6.0, 25.0)  # median length of a photo's larger half of insects; outside it the grid scale is suspect


def _hull(pts: np.ndarray) -> np.ndarray:
    """Convex hull (Andrew's monotone chain) of N×2 points, counter-clockwise."""
    pts = np.unique(pts, axis=0)
    if len(pts) < 3:
        return pts

    def turn(o, a, b) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def half(p):
        out: list = []
        for q in p:
            while len(out) >= 2 and turn(out[-2], out[-1], q) <= 0:
                out.pop()
            out.append(q)
        return out[:-1]

    return np.array(half(pts) + half(pts[::-1]))


def _edge_pixels(mask: np.ndarray) -> np.ndarray:
    """x,y of the leftmost and rightmost pixel of every row: every hull corner is one of them."""
    rows = np.nonzero(mask.any(axis=1))[0]
    left = mask[rows].argmax(axis=1)
    right = mask.shape[1] - 1 - mask[rows, ::-1].argmax(axis=1)
    return np.concatenate([np.stack([left, rows], 1), np.stack([right, rows], 1)]).astype(np.float64)


def long_side_px(mask: np.ndarray) -> float:
    """Long side of the smallest rotated rectangle around the mask's pixels (pixel edges, not centres)."""
    if not mask.any():
        return 0.0
    h = _hull(_edge_pixels(mask))
    if len(h) < 3:
        return float(np.ptp(h, axis=0).max()) + 1
    best = None
    for a, b in zip(h, np.roll(h, -1, axis=0)):
        d = (b - a) / max(np.hypot(*(b - a)), 1e-9)
        u, v = h @ d, h @ np.array([-d[1], d[0]])
        sides = (np.ptp(u) + 1, np.ptp(v) + 1)
        if best is None or sides[0] * sides[1] < best[0] * best[1]:
            best = sides
    return float(max(best))


def body_px(mask: np.ndarray, frac: float = BODY_FRAC) -> float:
    """Length along the mask's main axis of the slices at least `frac` as wide as the widest one."""
    ys, xs = np.nonzero(mask)
    if len(xs) < 3:
        return float(len(xs))
    p = np.stack([xs, ys], 1).astype(np.float64)
    p -= p.mean(axis=0)
    axis = np.linalg.eigh(p.T @ p)[1][:, -1]  # legs and antennae are few pixels, so the body sets the axis
    t = np.floor(p @ axis).astype(int)
    width = np.bincount(t - t.min())
    wide = np.nonzero(width >= frac * width.max())[0]
    return float(wide[-1] - wide[0] + 1)


def measure(mask: np.ndarray | None, box, ppm: float | None) -> dict:
    """{length_mm, body_mm, length_from} for an insect in `box` (x1, y1, x2, y2), given its outline
    as a mask the size of the box (or None). Blank lengths when the photo has no grid (ppm None)."""
    x1, y1, x2, y2 = box
    box_long = max(x2 - x1, y2 - y1)
    if mask is not None and mask.mean() >= MIN_FILL:
        long = long_side_px(mask)
        if long >= MIN_SPAN * box_long:
            if not ppm:
                return {"length_mm": "", "body_mm": "", "length_from": "outline"}
            return {"length_mm": f"{long / ppm:.1f}", "body_mm": f"{body_px(mask) / ppm:.1f}", "length_from": "outline"}
    return {"length_mm": f"{box_long / ppm:.1f}" if ppm else "", "body_mm": "", "length_from": "box"}


def scale_warning(lengths_mm: list[float]) -> str | None:
    """A warning when a photo's insects are implausibly small or big for the scale its grid gave: the
    grid finder locked onto every 2nd-5th line, or the card's grid isn't --grid-mm. Uses the larger
    half (mostly moths; the small half is flies and debris). Catches a 2x error on a card of small
    moths but not one of big moths: the band is wide because the cards hold 6-14 mm species."""
    v = sorted(x for x in lengths_mm if x > 0)
    if len(v) < 3:
        return None
    med = float(np.median(v[len(v) // 2:]))
    lo, hi = SCALE_MM
    if med < lo or med > hi:
        return f"larger insects measure {med:.1f} mm in the median (expected {lo:g}-{hi:g}): check the grid scale"
    return None
