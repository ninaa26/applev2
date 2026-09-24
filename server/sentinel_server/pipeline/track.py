"""Follow each insect across photos of the same liner, so it is counted once.

The camera and liner don't move, so an insect stays in (nearly) the same place.
A new detection that matches no existing track starts a *candidate*; it becomes
a *confirmed* catch once it appears in a second photo. Candidates that never
reappear (raindrops, a fly walking across, detector noise) are dropped.
Confirmed tracks are kept even if the detector misses them later.
"""

from __future__ import annotations

from dataclasses import dataclass

AUTO_THRESHOLD = 0.80   # at or above: counted automatically
REVIEW_THRESHOLD = 0.50  # between: goes to the review queue; below: "unknown"
CONFIRM_AFTER = 2        # photos an insect must appear in to count
DROP_CANDIDATE_AFTER = 2  # consecutive misses before a candidate is discarded


@dataclass
class Rect:
    x1: float
    y1: float
    x2: float
    y2: float


def iou(a: Rect, b: Rect) -> float:
    ix = max(0.0, min(a.x2, b.x2) - max(a.x1, b.x1))
    iy = max(0.0, min(a.y2, b.y2) - max(a.y1, b.y1))
    inter = ix * iy
    union = (a.x2 - a.x1) * (a.y2 - a.y1) + (b.x2 - b.x1) * (b.y2 - b.y1) - inter
    return inter / union if union > 0 else 0.0


def centre_close(a: Rect, b: Rect, frac: float = 0.5) -> bool:
    size = max(a.x2 - a.x1, a.y2 - a.y1, b.x2 - b.x1, b.y2 - b.y1)
    dx = (a.x1 + a.x2) / 2 - (b.x1 + b.x2) / 2
    dy = (a.y1 + a.y2) / 2 - (b.y1 + b.y2) / 2
    return (dx * dx + dy * dy) ** 0.5 <= frac * size


def match(tracks: list[Rect], dets: list[Rect], min_iou: float = 0.3) -> dict[int, int]:
    """Greedy one-to-one matching. Returns {det_index: track_index}."""
    pairs = []
    for ti, t in enumerate(tracks):
        for di, d in enumerate(dets):
            score = iou(t, d)
            if score >= min_iou or centre_close(t, d):
                pairs.append((score, ti, di))
    pairs.sort(reverse=True)
    used_t, used_d, out = set(), set(), {}
    for _, ti, di in pairs:
        if ti not in used_t and di not in used_d:
            used_t.add(ti)
            used_d.add(di)
            out[di] = ti
    return out


def consensus(prob_sum: dict[str, float], n: int) -> tuple[str, float, str]:
    """(species, confidence, review_status) from summed class probabilities over n photos."""
    if n == 0 or not prob_sum:
        return "unclassified", 0.0, "review"
    species, total = max(prob_sum.items(), key=lambda kv: kv[1])
    conf = total / n
    if conf >= AUTO_THRESHOLD:
        status = "auto"
    elif conf >= REVIEW_THRESHOLD:
        status = "review"
    else:
        status = "unknown"
    return species, conf, status
