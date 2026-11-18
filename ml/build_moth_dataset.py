"""The species head's dataset when the detector has already said "moth": training/classifier/moth_dataset.csv.

    python build_moth_dataset.py                  # then: python train_v1.py --dataset moth

The server's detector (train_yolo.py) sorts every box into moth, other_insect or debris; only a moth box goes to the
species head. So this head has four classes, CM, OFM, OBLR and other_moth (lookalike_RBLR, lookalike_LAW and the
rest fold into it, as in build_dataset.CLASS_OF), and nothing for bycatch or debris to learn.

Every row is a web photo in data/web_moth_photos/all_by_species/ (compile_species.py: one link per photo of our five
moths and the other moths, from every source, confirmed species only, already de-duplicated). Larvae, pupae, eggs
and damage photos are left out: the trap catches adults. A photo's group is its observation (record_url), and the
split is a hash of it, so photos of one moth stay together: train, val (where train_v1.py picks C and the
temperature) and a few in test, as a pipeline check (web test scores are never trap accuracy: BioCLIP 2 has likely
seen these photos).

No liner photo is used. Liner labels are moth / other_insect / debris only (decided Nov 18 2026): a liner's species
would be a guess from its lure, or a person's reading of a blurred moth. So nothing here says how the head does on
a real liner; that comes from our own trap's cards (`sentinel-server evaluate`).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from collections import Counter
from pathlib import Path

import paths
from build_dataset import CLASS_OF

CLASSES = ["CM", "OFM", "OBLR", "other_moth"]
ADULT = ("", "adult", "imago", "unknown")  # life_stage values kept (also "adult(s)"); larvae, pupae, eggs and
#                                              damage photos are not what the trap catches
FIELDS = ["path", "label", "class", "source", "group", "split", "license", "credit"]


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
                         "credit": r["attribution"] or r["record_url"]})
    return rows, left_out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path(paths.DATA))
    ap.add_argument("--val", type=float, default=0.15)
    ap.add_argument("--test", type=float, default=0.05, help="web photos kept as a pipeline check")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    rows, left_out = web_rows(args.data, args.seed, args.val, args.test)
    out = args.data / paths.MOTH_DATASET
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    table = Counter((r["class"], r["split"]) for r in rows)
    print(f"{'class':11} {'train':>6} {'val':>5} {'test':>5}")
    for c in CLASSES:
        print(f"{c:11} {table[(c, 'train')]:6} {table[(c, 'val')]:5} {table[(c, 'test')]:5}")
    print(f"Left out: {dict(left_out)}")
    print(f"Wrote {len(rows)} rows to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
