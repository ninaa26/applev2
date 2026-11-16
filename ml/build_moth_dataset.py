"""The species head's dataset when the detector has already said "moth": training/classifier/moth_dataset.csv.

    python build_moth_dataset.py                  # then: python train_v1.py --dataset moth
    python build_moth_dataset.py --trap-ppm 15 10 --site-export data/review/labelling_site/from_pi/exports/<time>/labels.csv

The server's detector (train_yolo.py) sorts every box into moth, other_insect or debris; only a moth box goes to the
species head. So this head has four classes, CM, OFM, OBLR and other_moth (lookalike_RBLR, lookalike_LAW and the
rest fold into it, as in build_dataset.CLASS_OF), and nothing for bycatch or debris to learn.

Train and val are the web photos in data/web_moth_photos/all_by_species/ (compile_species.py: one link per photo of
our five moths and the other moths, from every source, confirmed species only, already de-duplicated). Larvae and
pupae are left out: the trap catches adults. A photo's group is its observation (record_url), and the split is a
hash of it, so photos of one moth stay together; a few go to `test` as a pipeline check (web test scores are never
trap accuracy: BioCLIP 2 has likely seen these photos).

Real moths on real liners never train this head. They are the labelling site's moth boxes with a species, checked
by someone (or Claude) and not marked unsure, from the newest fetched export (`label_site/deploy.sh <pi> --fetch`),
cropped like the server crops them and shrunk to each --trap-ppm (from the photo's grid; never enlarged; the
few photos whose grid wasn't read are kept as photographed, under native/):
  tune   C and the temperature are picked on these (train_v1.py), so the confidence means something on a liner
  test   the photos in the classifier's held-out lists (field_cards.txt, field_cards_classifier_only.txt,
         web_liners_classifier.txt) and the site's own held-out photos, with their liner's other days: the
         real-liner number to quote.
Crops go to data/real_liners/site_species/<px/mm>/<set>/.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

import paths
from build_dataset import CLASS_OF
from liner_crops import resolutions
from PIL import Image, ImageOps

CLASSES = ["CM", "OFM", "OBLR", "other_moth"]
ADULT = ("", "adult", "imago", "unknown")  # life_stage values kept (also "adult(s)"); larvae, pupae, eggs and
#                                              damage photos are not what the trap catches
FIELDS = ["path", "label", "class", "source", "group", "split", "license", "credit", "ppm"]
SITE_CROPS = "real_liners/site_species"
PAD = 0.35  # as the server crops for the classifier (server/sentinel_server/pipeline/classify.py: crop)


def server_crop(img: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    x1, y1, x2, y2 = box
    side = max(x2 - x1, y2 - y1) * (1 + 2 * PAD)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    return img.crop((int(cx - side / 2), int(cy - side / 2), int(cx + side / 2), int(cy + side / 2)))


def split_of(group: str, seed: int, val: float, test: float) -> str:
    u = int(hashlib.sha1(f"{seed}:{group}".encode(), usedforsecurity=False).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "test" if u < test else "val" if u < test + val else "train"


def web_rows(data: Path, seed: int, val: float, test: float) -> tuple[list[dict], Counter]:
    root = data / paths.ALL_SPECIES
    rows, left_out = [], Counter()
    with open(root / "manifest.csv", newline="") as f:
        for r in csv.DictReader(f):
            if r["label"] not in CLASS_OF or CLASS_OF[r["label"]] not in CLASSES:
                left_out[f"label {r['label']}"] += 1
                continue
            stage = r["life_stage"].strip().lower()
            if not (stage in ADULT or stage.startswith(("adult", "imago"))):
                left_out[f"life stage {r['life_stage']}"] += 1
                continue
            group = r["record_url"] or r["file"]
            rows.append({"path": f"{paths.DATA}/{paths.ALL_SPECIES}/{r['file']}", "label": r["label"],
                         "class": CLASS_OF[r["label"]], "source": f"web:{r['source']}", "group": group,
                         "split": split_of(group, seed, val, test), "license": r["license"],
                         "credit": r["attribution"] or r["record_url"], "ppm": ""})
    return rows, left_out


def latest_site_export(data: Path) -> Path | None:
    found = sorted((data / paths.LABEL_SITE_EXPORTS).glob("*/labels.csv"))
    return found[-1] if found else None


def liner_groups(data: Path) -> dict[str, str]:
    """Site photo name -> its liner (photos of one liner on several days), from each web set's liners.json."""
    out = {}
    for f in sorted((data / paths.WEB_LINERS / "label").glob("*/liners.json")):
        for g in json.loads(f.read_text()):
            for p in g:
                out[f"{f.parent.name}__{p}"] = f"{f.parent.name}__{sorted(g)[0]}"
    return out


def site_rows(data: Path, export: Path, trap_ppm: list[float], held: list[str]) -> tuple[list[dict], Counter]:
    by_photo: dict[str, list[dict]] = {}
    with open(export, newline="") as f:
        for r in csv.DictReader(f):
            by_photo.setdefault(r["site_photo"], []).append(r)
    groups = liner_groups(data)
    test_groups = {groups.get(p, p) for p, rs in by_photo.items() if paths.is_listed(rs[0]["photo"], held)}
    inbox = data / paths.LABEL_SITE / "inbox"
    rows, skipped = [], Counter()
    for photo, boxes in sorted(by_photo.items()):
        wanted = []
        for b in boxes:
            if b["label"] not in CLASS_OF or CLASS_OF[b["label"]] not in CLASSES:
                continue  # moth with no species yet, bycatch, debris, skip
            if not b["by"]:
                skipped["not checked"] += 1
            elif "unsure" in b["attrs"].split(","):
                skipped["marked unsure"] += 1
            else:
                wanted.append(b)
        if not wanted:
            continue
        ppms = [float(b["ppm"]) for b in boxes if b["ppm"]]
        src_ppm = statistics.median(ppms) if ppms else None  # no grid read: kept as photographed, once
        if src_ppm is None:
            skipped["kept as photographed (no px/mm)"] += len(wanted)
        group = groups.get(photo, photo)
        split = "test" if group in test_groups else "tune"
        with Image.open(inbox / photo) as im:
            img = ImageOps.exif_transpose(im).convert("RGB")
        set_name = photo.split("__")[0]
        for b in wanted:
            crop = server_crop(img, tuple(float(b[k]) for k in ("x1", "y1", "x2", "y2")))
            for ppm in resolutions(src_ppm, trap_ppm) if src_ppm else [0.0]:
                s = ppm / src_ppm if src_ppm else 1.0
                c = crop.resize((max(8, round(crop.width * s)), max(8, round(crop.height * s))), Image.LANCZOS) \
                    if s < 1 else crop
                dest = data / SITE_CROPS / (f"{ppm:g}" if ppm else "native") / set_name / f"{Path(photo).stem}_{b['n']}.jpg"
                dest.parent.mkdir(parents=True, exist_ok=True)
                c.save(dest, quality=90)
                rows.append({"path": str(dest), "label": b["label"], "class": CLASS_OF[b["label"]],
                             "source": "liner", "group": f"liner:{group}", "split": split,
                             "license": f"see data/{paths.WEB_LINERS}/README.md", "credit": f"{photo} #{b['n']}",
                             "ppm": f"{min(ppm, src_ppm):.1f}" if src_ppm else ""})
    return rows, skipped


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path(paths.DATA))
    ap.add_argument("--val", type=float, default=0.15)
    ap.add_argument("--test", type=float, default=0.05, help="web photos kept as a pipeline check")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--trap-ppm", type=float, nargs="+", default=[15.0, 10.0])
    ap.add_argument("--site-export", type=Path, default=None,
                    help=f"default: the newest data/{paths.LABEL_SITE_EXPORTS}/<time>/labels.csv")
    args = ap.parse_args(argv)

    web, left_out = web_rows(args.data, args.seed, args.val, args.test)
    export = args.site_export or latest_site_export(args.data)
    liner, skipped = [], Counter()
    if export:
        held = sum((paths.held_out_list(args.data, n) for n in
                    (paths.FIELD_TEST, paths.FIELD_TEST_CLASSIFIER, paths.WEB_LINER_TEST_CLASSIFIER)), [])
        liner, skipped = site_rows(args.data, export, args.trap_ppm, held)
    else:
        print("No labelling-site export: no real-liner crops to tune or test on", file=sys.stderr)
    rows = web + liner
    out = args.data / paths.MOTH_DATASET
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    table = Counter((r["class"], "web" if r["source"] != "liner" else "real liner", r["split"]) for r in rows)
    print(f"{'class':11} {'kind':10} {'train':>6} {'val':>5} {'tune':>5} {'test':>5}")
    for c in CLASSES:
        for kind in ("web", "real liner"):
            n = [table[(c, kind, s)] for s in ("train", "val", "tune", "test")]
            if any(n):
                print(f"{c:11} {kind:10} {n[0]:6} {n[1]:5} {n[2]:5} {n[3]:5}")
    print(f"Left out of the web photos: {dict(left_out)}")
    if export:
        print(f"Real-liner crops from {export}; notes: {dict(skipped)}")
    print(f"Wrote {len(rows)} rows to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
