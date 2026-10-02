"""Put the boxes from Roboflow's stretched/augmented exports back onto the original uploads.

    python recover_roboflow_originals.py

Roboflow exports were resized to a square (640² or 416², "Stretch") and some were augmented
(rotations, noise, flips: copies of each photo). The original uploads are in
data/web_liners/roboflow_orig/<set>/<id>.jpg (fetched from source.roboflow.com/<workspace>/<id>/original.jpg).
For each export image this finds its original by comparing them at the export's size; a stretch is
a per-axis scale, so the boxes map back exactly. An export image whose closest original is not a
near-exact match is an augmented copy (rotated, noised) and is skipped, so every original appears
once. Writes data/web_liners/roboflow_recovered/<set>/_annotations.coco.json next to symlinks of
the originals, in the layout eval_detector_roboflow.py reads.

Already run (2026-10-02). The exports it reads were deleted afterwards and the outputs were pruned of
duplicates, so re-running it needs the export zips from ~/Downloads unpacked into roboflow_full/ first,
and would bring the duplicates back.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

SETS = ["moth-counting-matogen", "grape-moth-nsect"]  # moth-project-5/6 turned out to be codling-moth-ervins again
THUMB = 64     # compared at this size, grey
MAX_DIFF = 6.0  # mean abs grey difference (0-255) for "same photo"; augmented copies score ~15+


def thumb(img: np.ndarray) -> np.ndarray:
    return cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), (THUMB, THUMB), interpolation=cv2.INTER_AREA).astype(np.float32)


def main() -> int:
    root = Path("data/web_liners")
    for s in SETS:
        origs = sorted((root / "roboflow_orig" / s).glob("*.jpg"))
        o_img = {p: cv2.imread(str(p)) for p in origs}
        o_thumb = {p: thumb(im) for p, im in o_img.items()}
        out_dir = root / "roboflow_recovered" / s / "all"
        out_dir.mkdir(parents=True, exist_ok=True)
        images, anns, cats, taken = [], [], None, {}
        n_exp = n_aug = 0
        for j in sorted((root / "roboflow_full" / s).glob("*/_annotations.coco.json")):
            coco = json.load(open(j))
            cats = cats or coco["categories"]
            by_img: dict[int, list] = {}
            for a in coco["annotations"]:
                by_img.setdefault(a["image_id"], []).append(a)
            for im in coco["images"]:
                n_exp += 1
                e = cv2.imread(str(j.parent / im["file_name"]))
                et = thumb(e)
                best, d = min(((p, float(np.abs(t - et).mean())) for p, t in o_thumb.items()), key=lambda x: x[1])
                if d > MAX_DIFF:
                    n_aug += 1
                    continue
                if best in taken:  # an unaugmented copy already used (Roboflow may keep two)
                    continue
                h, w = o_img[best].shape[:2]
                sx, sy = w / im["width"], h / im["height"]
                iid = len(images)
                taken[best] = iid
                link = out_dir / best.name
                if not link.exists():
                    link.symlink_to(best.resolve())
                images.append({"id": iid, "file_name": best.name, "width": w, "height": h, "export": im["file_name"]})
                for a in by_img.get(im["id"], []):
                    x, y, bw, bh = a["bbox"]
                    anns.append({"id": len(anns), "image_id": iid, "category_id": a["category_id"],
                                 "bbox": [x * sx, y * sy, bw * sx, bh * sy], "area": bw * bh * sx * sy, "iscrowd": 0})
        json.dump({"images": images, "annotations": anns, "categories": cats},
                  open(out_dir / "_annotations.coco.json", "w"))
        print(f"{s}: {n_exp} export images -> {len(images)} originals with {len(anns)} boxes "
              f"({n_aug} augmented copies skipped; {len(origs) - len(images)} originals had no export)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
