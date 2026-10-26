"""The photo sets that go on the team labelling site: every set of real insects on a gridded sticky liner.

check_liner_photos.py checks them and prelabel_liners.py puts them on the site. On the site a photo is
named <set>__<file name>, so names from different sets can't collide; photo_checks.csv keeps each one's source
path. Left out on purpose: the liners without a grid (from_the_web/nongrid/, README there) and our own trap's
photos, which are reviewed on the dashboard instead.

Also left out: the matogen liners (see SETS) and anything listed only in the folder README.

Each set may carry earlier labels: a person's pass 1 (labels.csv of a label_field_cards.py folder) or the
uploader's boxes (Roboflow COCO). The site shows them as `old_label` on the box they overlap, and adds the ones
our detector missed, because every insect on a liner needs a box.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import paths

WEB = paths.WEB_LINERS
EXT = (".jpg", ".jpeg", ".png")
SEP = "__"


@dataclass(frozen=True)
class LabelSet:
    name: str
    folder: str  # under data/, holding the photos (or *_annotations.coco.json splits, for coco)
    earlier: str = ""  # labels.csv (a label_field_cards.py folder) or coco (the uploader's boxes beside the photos)
    earlier_path: str = ""
    originals: bool = False  # full-size phone originals expected: a small or recompressed one is a copy
    held_out: str = ""  # held-out list this set's cards are added to (only our own Cornell cards)
    note: str = ""


SETS = [
    LabelSet("cornell", f"{paths.FIELD}/inbox", "labels.csv", f"{paths.FIELD}/labels.csv", originals=True,
             held_out=paths.FIELD_TEST, note="phone photos of used Trécé cards, Cornell orchard"),
    LabelSet("web-inat", f"{WEB}/inat", note="iNaturalist, white gridded liners; licences in sources.csv"),
    LabelSet("web-manual", f"{WEB}/manual", note="found by hand; mostly all rights reserved: team use only"),
    LabelSet("web-commons", f"{WEB}/commons", note="Wikimedia Commons"),
    LabelSet("ofm-ervins", f"{WEB}/label/ofm-ervins/inbox", "labels.csv", f"{WEB}/label/ofm-ervins/labels.csv",
             note="OFM trap-camera liners (Roboflow); pass 1 of 14 of 31 photos done"),
    LabelSet("cm-ervins", f"{WEB}/roboflow_full/codling-moth-ervins", "coco",
             note="Trécé CM cards (Roboflow), each card shot several times; only codling moths boxed"),
    # Left out (Oct 26 2026): the matogen Insect Science liners (moth-counting-matogen, 87 photos). Hundreds of
    # boxes per photo (~300 on average) and too blurry to label well by hand; they were taken off the site.
    LabelSet("grape-moth", f"{WEB}/roboflow_recovered/grape-moth-nsect", "coco",
             note="trap-camera delta liner, grape moth; moths boxed"),
]
BY_NAME = {s.name: s for s in SETS}

# The uploader's class names -> the closest pass-1 label (their boxes are claims, so shown as unchecked).
COCO_LABELS = {"codling-moth": ("moth", "CM"), "Count-moths": ("moth", "moth"),
               "Count-other": ("other_insect", "other"), "0": ("moth", "grape moth")}


def site_name(s: LabelSet, file: str) -> str:
    return f"{s.name}{SEP}{file}"


def photos(data: Path, s: LabelSet) -> list[Path]:
    root = data / s.folder
    if s.earlier == "coco":
        found = [p for j in sorted(root.glob("*/_annotations.coco.json")) for p in sorted(j.parent.iterdir())
                 if p.suffix.lower() in EXT]
    else:
        found = sorted(p for p in root.iterdir() if p.suffix.lower() in EXT) if root.exists() else []
    return found


def earlier_boxes(data: Path, s: LabelSet) -> dict[str, list[dict]]:
    """File name -> [{x1, y1, x2, y2, label (pass 1), old_label (as given), row (the labels.csv row, if any)}]."""
    out: dict[str, list[dict]] = {}
    if s.earlier == "labels.csv" and (data / s.earlier_path).exists():
        with open(data / s.earlier_path, newline="") as f:
            for r in csv.DictReader(f):
                if r.get("label") in ("", "skip", None):
                    continue
                out.setdefault(r["photo"], []).append({**{k: float(r[k]) for k in ("x1", "y1", "x2", "y2")},
                                                       "label": r["label"], "old_label": r["label"], "row": r})
    elif s.earlier == "coco":
        for j in sorted((data / s.folder).glob("*/_annotations.coco.json")):
            coco = json.loads(j.read_text())
            cats = {c["id"]: c["name"] for c in coco["categories"]}
            files = {im["id"]: im["file_name"] for im in coco["images"]}
            for a in coco["annotations"]:
                x, y, w, h = a["bbox"]
                label, said = COCO_LABELS.get(cats.get(a["category_id"], ""), ("", cats.get(a["category_id"], "?")))
                out.setdefault(files[a["image_id"]], []).append(
                    {"x1": x, "y1": y, "x2": x + w, "y2": y + h, "label": label, "old_label": f"{said} (uploader)", "row": None})
    return out
