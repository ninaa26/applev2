"""Copy labels between photos of the same liner taken on different days (trap-camera time series).

    python carry_liner_labels.py --data data/web_liners/label/ofm-ervins            # dry run: counts only
    python carry_liner_labels.py --data data/web_liners/label/ofm-ervins --write    # stop the labeller first

<data>/liners.json lists which photos show the same liner (photo names, any order). Moths stay where
they stuck, so an unlabelled box in one photo that sits where a labelled insect sits in another photo
of the same liner gets that label. The camera shifts a little between days, so each pair of photos is
aligned first (ORB features, similarity transform). A box takes a label only when every labelled box
it overlaps (IoU ≥ --iou after alignment) agrees; disagreements stay unlabelled. Carried labels keep
their source and gain " carried" in it, so they can be found and checked in the labeller.

Stop label_field_cards.py before --write: it holds labels.csv in memory and its next save would
overwrite the carried labels. A backup of labels.csv is written next to it first.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

from crop_field_cards import FIELDS


def features(path: Path, orb) -> tuple[np.ndarray, np.ndarray]:
    k, d = orb.detectAndCompute(cv2.imread(str(path), cv2.IMREAD_GRAYSCALE), None)
    return np.float32([p.pt for p in k]), d


def affine(fa, fb, bf) -> np.ndarray | None:
    """2×3 transform taking points in photo a to photo b, or None when they don't match."""
    (pa, da), (pb, db) = fa, fb
    good = [m for m, n in (p for p in bf.knnMatch(da, db, k=2) if len(p) == 2) if m.distance < 0.75 * n.distance]
    if len(good) < 30:
        return None
    M, mask = cv2.estimateAffinePartial2D(pa[[g.queryIdx for g in good]], pb[[g.trainIdx for g in good]],
                                          method=cv2.RANSAC, ransacReprojThreshold=4)
    return M if M is not None and mask.sum() >= 30 else None


def moved(box, M) -> list[float]:
    x1, y1, x2, y2 = box
    q = np.array([[x1, y1], [x2, y2], [x1, y2], [x2, y1]]) @ M[:, :2].T + M[:, 2]
    return [q[:, 0].min(), q[:, 1].min(), q[:, 0].max(), q[:, 1].max()]


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    return i / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i + 1e-9)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--iou", type=float, default=0.4)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)

    labels = args.data / "labels.csv"
    rows = list(csv.DictReader(open(labels, newline="")))
    by = defaultdict(list)
    for r in rows:
        by[r["photo"]].append(r)
    box = lambda r: [float(r[k]) for k in ("x1", "y1", "x2", "y2")]
    orb, bf = cv2.ORB_create(4000), cv2.BFMatcher(cv2.NORM_HAMMING)

    filled = ambiguous = left = 0
    for group in json.load(open(args.data / "liners.json")):
        feats = {p: features(args.data / "inbox" / p, orb) for p in group}
        for b in group:
            todo = [r for r in by[b] if not r["label"]]
            if not todo:
                continue
            others = []
            for a in group:
                M = affine(feats[a], feats[b], bf) if a != b else None
                if M is not None:
                    others += [(moved(box(r), M), r["label"]) for r in by[a] if r["label"] and r["label"] != "skip"]
            for r in todo:
                labs = {lab for bx, lab in others if iou(bx, box(r)) >= args.iou}
                if len(labs) == 1:
                    r["label"] = labs.pop()
                    r["source"] = f"{r['source']} carried"
                    filled += 1
                else:
                    ambiguous += len(labs) > 1
                    left += 1
    print(f"filled {filled} boxes from other days; {ambiguous} disagree and {left} have no match (left unlabelled)")
    if args.write and filled:
        backup = labels.with_name(f"labels.backup-{time.strftime('%H%M%S')}.csv")
        shutil.copy(labels, backup)
        with open(labels, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, restval="")
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {labels} (backup: {backup.name})")
    elif filled:
        print("dry run: add --write (with the labeller stopped) to save")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
