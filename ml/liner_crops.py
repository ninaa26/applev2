"""Collect crops of real insects on real liners, at trap resolution, for training and scoring the species head.

    python liner_crops.py                      # -> data/real_liners/from_the_web/species/<px/mm>/..., manifest.csv
    python liner_crops.py --trap-ppm 15 10 6

Web photos and their trap-style paste-ups are not moths that sat on glue. On other people's trap photos the
gap is large (AMI: 8-16 points; Gardiner et al. 2025: labelling 5% of the target photos gave +13-15 points),
and it is the same here (ml/README.md). Until our own trap has reviewed photos (data/real_liners/our_trap/), these are the
nearest thing:
  OFM liners   data/real_liners/from_the_web/label/ofm-ervins/labels.csv: the uploader's boxes (source roboflow:OFM, trap
               camera, ~26 px/mm) are OFM unless pass 2 gave them another species; boxes labelled other_insect
               or debris in pass 1 count as that. `skip` and unlabelled boxes are left out.
  CM cards     the full-size phone photos of codling-moth-ervins (~10 px/mm), every box CM, cropped like the
               server crops (crop_field_cards.server_crop).
  PTM liners   moth-counting-matogen (Insect Science delta liners, South Africa): boxes of class "Count-moths",
               potato tuber moth and Tuta, are `other_moth`. They are the only real moths on glue we have
               that are none of our three, so they are what stops "a moth on a real liner" from meaning
               OFM. Phone photos at ~6-8 px/mm whose grid often reads wrongly, so crops are kept as
               photographed, only boxes 45-140 px long (a moth the size the trap sees at its edges), at most
               --per-photo from each photo. The set's "Count-other" boxes are not used: other is not a label.
  Field cards  data/real_liners/cornell_field_cards (phone photos of used Trécé cards from the orchard): moths with a species, from pass 2
               in labels.csv or, until someone has done pass 2, from data/real_liners/cornell_field_cards/species.csv (photo, n, species,
               by, note; Oct 7 2026: Claude's reading of the full-size crops, to be checked: 35 OBLR, 20 OFM,
               13 CM, 2 others, 24 left blank as unsure). The only real-liner OBLR there is, and a second
               source of OFM and CM. Held out: the cards in held_out/field_cards.txt (CM) plus
               held_out/field_cards_classifier_only.txt, the April 2025 OFM card and the June 2024 OBLR photos, so
               each target has field moths the head never saw.
The species is the uploader's claim (a pheromone trap's target), not an expert's ID of each moth, and the
liner, camera and light are not ours.

Each crop is shrunk to each --trap-ppm (from its photo's printed grid; never enlarged), so one insect gives one
row per resolution its photo is sharp enough for (the CM cards, at ~10 px/mm, only give the lower one). `group` is the liner (liners.json: a liner photographed on several days shows the same
moths) or the card; build_dataset.py keeps a group on one side of every split. Groups whose photo names start
with one of the prefixes in data/training/held_out/web_liners_classifier.txt are marked `test`: never trained
on, and the only real-liner score to quote. The list is in git, includes train_yolo.py's test liners, and is
about a third of the moths. The PTM liners are 86
photos, so there a fixed quarter is held out by a hash of the photo's name.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import paths
from build_dataset import CLASS_OF
from PIL import Image

FIELDS = ["path", "label", "set", "photo", "group", "split", "ppm", "length_mm"]


def ofm_liner_rows(data: Path) -> list[dict]:
    folder = data / "label" / "ofm-ervins"
    if not (folder / "labels.csv").exists():
        return []
    liners = json.loads((folder / "liners.json").read_text()) if (folder / "liners.json").exists() else []
    liner_of = {p: sorted(g)[0] for g in liners for p in g}
    out = []
    with open(folder / "labels.csv", newline="") as f:
        for r in csv.DictReader(f):
            claimed = r["source"].removeprefix("roboflow:") if r["source"].startswith("roboflow:") else ""
            label = claimed if r["label"] == "moth" and claimed else r["label"]
            if label in CLASS_OF and r["ppm"]:
                out.append({"set": "ofm-liners", "photo": r["photo"], "crop": r["crop"], "label": label,
                            "group": Path(liner_of.get(r["photo"], r["photo"])).stem, "src_ppm": float(r["ppm"]),
                            "length_mm": r["length_mm"]})
    return out


def cm_card_rows(data: Path, grid_mm: float) -> list[dict]:
    """Crop the boxed codling moths out of the full-size card photos (once; later runs reuse the crops)."""
    root = data / "roboflow_full" / "codling-moth-ervins"
    if not root.exists():
        return []
    import cv2
    from crop_field_cards import server_crop
    from eval_detector_roboflow import grid_px_per_mm, load_coco

    out = []
    for im in load_coco(root):
        if im["w"] <= 640 or not im["gt"]:  # the 640² uploads are ~2.4 px/mm: a moth is 25 px, nothing to classify
            continue
        ppm = grid_px_per_mm(cv2.imread(str(im["path"])), grid_mm)
        if not ppm:
            continue
        stem = im["path"].stem
        img = None
        for n, b in enumerate(im["gt"], 1):
            dest = data / "species" / "native" / "cm-cards" / f"{stem}_{n:02d}.jpg"
            if not dest.exists():
                img = img or Image.open(im["path"]).convert("RGB")
                dest.parent.mkdir(parents=True, exist_ok=True)
                server_crop(img, [int(round(v)) for v in b]).save(dest, quality=92)
            out.append({"set": "cm-cards", "photo": im["path"].name, "crop": str(dest), "label": "CM", "group": stem,
                        "src_ppm": ppm, "length_mm": f"{max(b[2] - b[0], b[3] - b[1]) / ppm:.1f}"})
    return out


def field_card_rows(field: Path, held: list[str]) -> list[dict]:
    """`held`: photo names or prefixes kept out of the classifier (held_out/field_cards*.txt)."""
    if not (field / "labels.csv").exists():
        return []
    species = {}
    if (field / "species.csv").exists():
        with open(field / "species.csv", newline="") as f:
            species = {(r["photo"], r["n"]): r["species"] for r in csv.DictReader(f) if r["species"]}
    out = []
    with open(field / "labels.csv", newline="") as f:
        for r in csv.DictReader(f):
            label = r["label"] if r["label"] in CLASS_OF and CLASS_OF[r["label"]] not in ("other_insect", "debris") \
                else species.get((r["photo"], r["n"]), "") if r["label"] == "moth" else ""
            if label in CLASS_OF and r["ppm"]:
                out.append({"set": "field-cards", "photo": r["photo"], "crop": r["crop"], "label": label,
                            "group": Path(r["photo"]).stem, "src_ppm": float(r["ppm"]), "length_mm": r["length_mm"],
                            "held_out": paths.is_listed(r["photo"], held)})
    return out


PTM_PX = (45, 140)  # box long side kept, px


def ptm_liner_rows(data: Path, per_photo: int) -> list[dict]:
    root = data / "roboflow_recovered" / "moth-counting-matogen" / "all"
    if not (root / "_annotations.coco.json").exists():
        return []
    import random

    from crop_field_cards import server_crop

    coco = json.loads((root / "_annotations.coco.json").read_text())
    moth = {c["id"] for c in coco["categories"] if c["name"] == "Count-moths"}
    boxes: dict[int, list] = {}
    for a in coco["annotations"]:
        if a["category_id"] in moth and PTM_PX[0] <= max(a["bbox"][2:]) <= PTM_PX[1]:
            boxes.setdefault(a["image_id"], []).append(a["bbox"])
    out = []
    for im in sorted(coco["images"], key=lambda i: i["file_name"]):
        stem = Path(im["file_name"]).stem
        picks = sorted(boxes.get(im["id"], []))
        random.Random(stem).shuffle(picks)  # the same boxes on every run
        img = None
        for n, (x, y, w, h) in enumerate(picks[:per_photo], 1):
            dest = data / "species" / "native" / "ptm-liners" / f"{stem}_{n:02d}.jpg"
            if not dest.exists():
                img = img or Image.open(root / im["file_name"]).convert("RGB")
                dest.parent.mkdir(parents=True, exist_ok=True)
                server_crop(img, [int(x), int(y), int(x + w), int(y + h)]).save(dest, quality=92)
            out.append({"set": "ptm-liners", "photo": im["file_name"], "crop": str(dest), "label": "other_moth",
                        "group": stem, "src_ppm": 7.0, "length_mm": "",  # the set's median; per-photo grids misread
                        "held_out": int(hashlib.sha1(stem.encode(), usedforsecurity=False).hexdigest()[:8], 16) % 4 == 0})
    return out


def at_trap_resolution(src: str, src_ppm: float, ppm: float, dest: Path) -> None:
    with Image.open(src) as im:
        im = im.convert("RGB")
        s = ppm / src_ppm
        if s < 1:
            im = im.resize((max(8, round(im.width * s)), max(8, round(im.height * s))), Image.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest, quality=85)


def resolutions(src_ppm: float, wanted: list[float]) -> list[float]:
    """The wanted px/mm this photo can be shrunk to (within 10%); if none, the lowest, left as photographed."""
    return [p for p in wanted if src_ppm >= 0.9 * p] or [min(wanted)]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=paths.DATA, help="data/: the field cards and held-out lists")
    ap.add_argument("--data", type=Path, default=None, help="the web liners (default: <root>/real_liners/from_the_web)")
    ap.add_argument("--trap-ppm", type=float, nargs="+", default=[15.0, 10.0],
                    help="px/mm to write (IMX219 trap camera: ~15 in the centre, 10-11 at the edges)")
    ap.add_argument("--grid-mm", type=float, default=25.0)
    ap.add_argument("--per-photo", type=int, default=12, help="most moths taken from one PTM liner photo")
    args = ap.parse_args(argv)
    args.data = args.data or args.root / paths.WEB_LINERS

    field_held = (paths.held_out_list(args.root, paths.FIELD_TEST)
                  + paths.held_out_list(args.root, paths.FIELD_TEST_CLASSIFIER))
    test_groups = paths.held_out_list(args.root, paths.WEB_LINER_TEST_CLASSIFIER)
    if not test_groups:
        raise SystemExit(f"no {paths.WEB_LINER_TEST_CLASSIFIER} in {args.root / paths.HELD_OUT}: every liner would train")
    rows = (ofm_liner_rows(args.data) + cm_card_rows(args.data, args.grid_mm) + ptm_liner_rows(args.data, args.per_photo)
            + field_card_rows(args.root / paths.FIELD, field_held))
    for r in rows:
        r.setdefault("held_out", paths.is_listed(r["group"], test_groups))
    if not rows:
        raise SystemExit(f"no labelled liner crops under {args.data}")
    manifest = []
    for r in rows:
        split = "test" if r["held_out"] else ""
        for ppm in resolutions(r["src_ppm"], args.trap_ppm):
            dest = args.data / "species" / f"{ppm:g}" / r["set"] / Path(r["crop"]).name
            at_trap_resolution(r["crop"], r["src_ppm"], ppm, dest)
            manifest.append({"path": str(dest), "label": r["label"], "set": r["set"], "photo": r["photo"],
                             "group": r["group"], "split": split, "ppm": f"{min(ppm, r['src_ppm']):.1f}",
                             "length_mm": r["length_mm"]})
    with open(args.data / "species" / "manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(manifest)
    n = Counter((r["set"], r["label"], "held out" if r["held_out"] else "to train")
                for r in rows)
    for k in sorted(n):
        print(f"  {k[0]:11} {k[1]:13} {k[2]:9} {n[k]:4} insects")
    print(f"Wrote {len(manifest)} crops ({len(rows)} insects at up to {len(args.trap_ppm)} resolutions, "
          f"{len({r['group'] for r in rows})} liners/cards) and {args.data / 'species' / 'manifest.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
