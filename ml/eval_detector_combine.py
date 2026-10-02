"""Try combining the two detectors, and trimming the baseline's junk, on the Roboflow liner photos.

    python eval_detector_roboflow.py --trap-ppm 8     # first: fills the detection caches this reads
    python eval_detector_combine.py                    # then: re-scores from the caches, in seconds

Each row adds one step, so the table shows what every step costs in moths and buys in junk:
  baseline         the server's default detector as is
  + shape          drop strips and slivers: short side under --min-short-mm, or long/short over --max-aspect
                   (grid lines the line removal left behind, bits of glue edge)
  + flatbug        add flatbug's detections (conf ≥ --fb-conf); where a flatbug and a baseline box
                   overlap, the flatbug box is kept
  conf (alt)       baseline + shape, also dropping baseline detections under --base-conf
  on card (alt)    baseline, dropping detections off the liner (phone photos only: the trap sees only liner)
Tried and not kept: the conf filter loses 7-14% of moths; the card mask fails when the card label or a
pale background touches the card, and off-card junk doesn't exist in trap photos anyway.
Junk/photo = detections that matched no boxed moth, per photo: bycatch is in there too, so it can't
reach zero. Writes data/web_liners/detector_eval/combine.md and overlays of the final step.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from eval_detector_roboflow import GROUPS, centre, dataset_dir, grid_px_per_mm, inside, iou, load_coco, match, overlay


def card_mask(img: np.ndarray) -> tuple[np.ndarray, float]:
    """(mask at 1/f scale, f): the liner as the largest bright region, holes filled, convex hull.

    Everything counts as card when there's no clearly darker surround (a trap-camera close-up is
    all liner), so this never throws away a photo's worth of detections.
    """
    f = min(1.0, 800 / max(img.shape[:2]))
    small = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    v = cv2.GaussianBlur(small.max(axis=2), (9, 9), 0)
    t, bright = cv2.threshold(v, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bright = cv2.morphologyEx(bright, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(bright)
    full = np.full(v.shape, 255, np.uint8)
    if n < 2:
        return full, f
    big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    pts = cv2.findNonZero((lab == big).astype(np.uint8))
    mask = np.zeros(v.shape, np.uint8)
    cv2.fillConvexPoly(mask, cv2.convexHull(pts), 255)
    inside_v, outside_v = v[mask > 0].mean(), v[mask == 0].mean() if (mask == 0).any() else 255
    if (mask > 0).mean() > 0.92 or inside_v - outside_v < 40:
        return full, f
    return mask, f


def on_card(d, mask, f) -> bool:
    x, y = centre(d)
    yi, xi = int(y * f), int(x * f)
    return 0 <= yi < mask.shape[0] and 0 <= xi < mask.shape[1] and mask[yi, xi] > 0


def good_shape(d, ppm, min_short, max_aspect) -> bool:
    w, h = (d[2] - d[0]) / ppm, (d[3] - d[1]) / ppm
    return min(w, h) >= min_short and max(w, h) / max(min(w, h), 1e-6) <= max_aspect


def union(fb, base):
    """Flatbug's boxes, plus baseline boxes that don't overlap one (a baseline clump keeps its n)."""
    out = list(fb)
    for b in base:
        if not any(iou(b, a) >= 0.3 or inside(centre(a), b) and inside(centre(b), a) for a in fb):
            out.append(b)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data/web_liners"))
    ap.add_argument("--grid-mm", type=float, default=25.0)
    ap.add_argument("--min-short-mm", type=float, default=2.5)
    ap.add_argument("--max-aspect", type=float, default=3.5)
    ap.add_argument("--base-conf", type=float, default=0.7)
    ap.add_argument("--fb-conf", type=float, default=0.3)
    ap.add_argument("--iou", type=float, default=0.3)
    args = ap.parse_args(argv)

    ev = args.data / "detector_eval"
    (ev / "overlays_combined").mkdir(parents=True, exist_ok=True)
    steps = ["baseline", "+ shape", "+ flatbug", "flatbug alone", "conf (alt)", "on card (alt)"]
    lines = ["# Combining the detectors (Roboflow liner photos)", "",
             f"Shape: short side ≥ {args.min_short_mm:g} mm, long/short ≤ {args.max_aspect:g}; baseline conf ≥ "
             f"{args.base_conf:g}; flatbug conf ≥ {args.fb_conf:g}. Junk/photo = detections matching no boxed moth "
             "(includes real bycatch).", "",
             "| Group | Resolution | Step | Recall | Moths vs baseline | Junk/photo |", "|---|---|---|---|---|---|"]
    for ds in dict.fromkeys(g[0] for g in GROUPS):
        images = load_coco(dataset_dir(args.data, ds))
        for tag in ["native", "8ppm"]:
            caches = {n: ev / "cache" / f"{ds}__{n}__{tag}.json" for n in ("baseline", "flatbug")}
            if not all(c.exists() for c in caches.values()):
                continue
            base_c, fb_c = (json.load(open(c)) for c in caches.values())
            for gds, group, keep in GROUPS:
                if gds != ds or group.startswith("640"):
                    continue  # 640² uploads: ~2.4 px/mm, flatbug can't see the moths at all
                sub = [im for im in images if keep(im) and "skip" not in base_c.get(im["path"].name, {"skip": 1})
                       and "skip" not in fb_c.get(im["path"].name, {"skip": 1})]
                if not sub:
                    continue
                tot = {s: [0, 0] for s in steps}  # found, junk
                n_gt = sum(len(im["gt"]) for im in sub)
                for im in sub:
                    img = cv2.imread(str(im["path"]))
                    ppm = grid_px_per_mm(img, args.grid_mm) or 10.0
                    mask, f = card_mask(img)
                    b = base_c[im["path"].name]["dets"]
                    fb = [d for d in fb_c[im["path"].name]["dets"] if d[4] >= args.fb_conf]
                    s1 = [d for d in b if on_card(d, mask, f)]
                    s2 = [d for d in b if good_shape(d, ppm, args.min_short_mm, args.max_aspect)]
                    s3 = [d for d in s2 if d[4] >= args.base_conf]
                    s4 = union(fb, s2)
                    for s, dets in zip(steps, [b, s2, s4, fb, s3, s1]):
                        found, used = match(im["gt"], dets, args.iou)
                        tot[s][0] += sum(found)
                        tot[s][1] += sum(1 for u in used if not u)
                    if tag == "native":
                        found, used = match(im["gt"], s4, args.iou)
                        overlay(im, s4, found, used, ev / "overlays_combined" / f"{ds}__{im['path'].stem[:40]}.jpg")
                for s in steps:
                    lost = tot[s][0] - tot["baseline"][0]
                    lines.append(f"| {ds} · {group} ({len(sub)} photos, {n_gt} moths) | {tag} | {s} | "
                                 f"**{tot[s][0] / n_gt:.0%}** | {lost:+d} | {tot[s][1] / len(sub):.1f} |"
                                 .replace("| +0 |", "| 0 |"))
    (ev / "combine.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
