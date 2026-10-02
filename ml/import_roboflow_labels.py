"""Turn a Roboflow COCO export into a label_field_cards.py folder, so its boxes can be checked by hand.

    python import_roboflow_labels.py ofm-ervins            # -> data/web_liners/label/ofm-ervins/
    python label_field_cards.py --data data/web_liners/label/ofm-ervins

The uploader's boxes come in pre-labelled (pass 1: `moth`; the species they claim is kept in the
`source` column, e.g. roboflow:OFM). Only the target moth was boxed, so the other insects on the liner
are added as unlabelled boxes from both detectors (cached by eval_detector_roboflow.py): flatbug at
conf ≥ 0.3, plus baseline boxes that pass the shape filter (eval_detector_combine.py) and don't overlap
a flatbug box. A detector box overlapping an uploader's box is dropped. Label those 1/2/3 (moth /
other_insect / debris) in pass 1; Delete marks an uploader's or detector's box `skip`.

Crops are cut exactly like crop_field_cards.py does, and the photo scale comes from the printed grid
(--grid-mm), so each box gets a length in mm. Photos are linked into inbox/, not copied. Re-running
keeps rows that already have a label and only adds photos that are new.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import cv2
from PIL import Image

from crop_field_cards import FIELDS, server_crop
from eval_detector_combine import good_shape, union
from eval_detector_roboflow import centre, dataset_dir, grid_px_per_mm, inside, iou, load_coco

# what the uploader's class means, per dataset (ofm-ervins named its OFM class "codling_moth")
CLAIMED = {"ofm-ervins": "OFM", "codling-moth-ervins": "CM", "grape-moth-nsect": "other_tortricid",
           "moth-counting-matogen": "other_moth"}


def overlaps(a, b) -> bool:
    return iou(a, b) >= 0.3 or (inside(centre(a), b) and inside(centre(b), a))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dataset", choices=sorted(CLAIMED))
    ap.add_argument("--data", type=Path, default=Path("data/web_liners"))
    ap.add_argument("--grid-mm", type=float, default=25.0)
    ap.add_argument("--fb-conf", type=float, default=0.3)
    args = ap.parse_args(argv)

    out = args.data / "label" / args.dataset
    (out / "inbox").mkdir(parents=True, exist_ok=True)
    labels = out / "labels.csv"
    old = list(csv.DictReader(open(labels, newline=""))) if labels.exists() else []
    done = {r["photo"] for r in old}
    cache = args.data / "detector_eval" / "cache"
    base_c = json.load(open(cache / f"{args.dataset}__baseline__native.json"))
    fb_c = json.load(open(cache / f"{args.dataset}__flatbug__native.json"))

    new = []
    for im in load_coco(dataset_dir(args.data, args.dataset)):
        name = im["path"].name
        link = out / "inbox" / name
        if not link.exists():
            link.symlink_to(im["path"].resolve())
        if name in done:
            continue
        img = Image.open(im["path"]).convert("RGB")
        ppm = grid_px_per_mm(cv2.imread(str(im["path"])), args.grid_mm)
        fb = [d for d in fb_c.get(name, {}).get("dets", []) if d[4] >= args.fb_conf]
        base = [d for d in base_c.get(name, {}).get("dets", []) if good_shape(d, ppm or 10.0, 2.5, 3.5)]
        dets = [d for d in union(fb, base) if not any(overlaps(d, g) for g in im["gt"])]
        boxes = [(g, "moth", f"roboflow:{CLAIMED[args.dataset]}", "") for g in im["gt"]]
        boxes += [(d[:4], "", "flatbug" if d in fb else "baseline", f"{d[4]:.2f}") for d in dets]
        stem = Path(name).stem
        for n, (b, label, source, conf) in enumerate(boxes, 1):
            box = [int(round(v)) for v in b]
            crop = out / "crops" / stem / f"{stem}_{n:02d}.jpg"
            crop.parent.mkdir(parents=True, exist_ok=True)
            server_crop(img, box).save(crop, quality=92)
            long_px = max(box[2] - box[0], box[3] - box[1])
            new.append({"photo": name, "n": str(n), "label": label, "source": source, "crop": str(crop), "cutout": "",
                        "x1": box[0], "y1": box[1], "x2": box[2], "y2": box[3], "conf": conf,
                        "ppm": f"{ppm:.2f}" if ppm else "", "length_mm": f"{long_px / ppm:.1f}" if ppm else ""})
        print(f"  {name[:40]}: {len(im['gt'])} uploader boxes + {len(dets)} for you to label", flush=True)
    with open(labels, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, restval="")
        w.writeheader()
        w.writerows(old + new)
    todo = sum(1 for r in old + new if not r["label"])
    print(f"{len(old + new)} boxes in {labels}; {todo} still unlabelled. "
          f"Label them: python label_field_cards.py --data {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
