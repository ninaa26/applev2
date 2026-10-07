"""Find web photos that should not train the species head: not a usable photo of the adult, or mislabelled.

    python clean_dataset.py                 # -> data/clean/suspects.csv and a contact sheet per check and label

iNaturalist and GBIF photos are other people's labels. The AMI pipeline cleaned its GBIF photos of larvae,
thumbnails and placeholders before training, and suspected label errors behind some of its confusions.
fetch_inat.py skips observations annotated as egg, larva or pupa, but most observations carry no annotation,
and fetch_ami.py trusts GBIF's lifeStage. Two checks, both on the BioCLIP 2 features train_v1.py already cached:

  odd       the photo sits far from the other photos of its label (robust z-score of its similarity to the
            label's mean feature, below -Z). The far end is where the specimen-label cards, blank frames,
            moths that are a dot in the distance, pinned and spread museum specimens and empty pupal cases are
            (Oct 7 2026, checked by eye on CM), mixed with good photos on odd backgrounds.
  label     the head, trained on the other folds (photos grouped by observation), calls it another class
            at >= --min-prob.

Neither list is safe to delete from blindly: the head being sure is not proof, and a good photo on a
strange background is also "odd". Look at the sheets (most suspect first) and copy the rows that really are
junk into data/exclude.csv (columns path, why); build_dataset.py leaves those out, and their trap-style
copies go with them. Tiny images are already dropped by build_dataset.py (MIN_SIDE), duplicates by its hash
check, and photos flatbug finds no insect in never get a trap-style copy (segment_moths.py).

Tried and dropped (Oct 7 2026): asking BioCLIP 2 zero-shot whether a photo shows a caterpillar, pupa or eggs
rather than an adult. Of its 508 picks at >= 0.9, the 120 looked at were ordinary adult moths.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

from train_v1 import MODEL, embeddings, load_rows

def odd_ones(X: np.ndarray, labels: np.ndarray, z: float) -> list[tuple[int, float]]:
    """(row, robust z) for photos far from their label's other photos, most suspect first."""
    out = []
    for lab in sorted(set(labels)):
        idx = np.where(labels == lab)[0]
        if len(idx) < 30:
            continue
        mu = X[idx].mean(0)
        sim = X[idx] @ (mu / np.linalg.norm(mu))
        med = np.median(sim)
        zs = (sim - med) / (1.4826 * np.median(np.abs(sim - med)) + 1e-9)
        out += [(int(idx[k]), float(zs[k])) for k in np.where(zs < -z)[0]]
    return sorted(out, key=lambda t: t[1])


def out_of_fold(X: np.ndarray, y: np.ndarray, groups: np.ndarray, folds: int = 4) -> np.ndarray:
    """Class probabilities for every row from a head that never saw its group."""
    from sklearn.linear_model import LogisticRegression

    import hashlib

    fold = np.array([int(hashlib.sha1(g.encode()).hexdigest()[:8], 16) % folds for g in groups])
    classes = sorted(set(y))
    P = np.zeros((len(y), len(classes)), np.float32)
    for k in range(folds):
        clf = LogisticRegression(C=1.0, class_weight="balanced", max_iter=1000).fit(X[fold != k], y[fold != k])
        P[np.ix_(fold == k, [classes.index(c) for c in clf.classes_])] = clf.predict_proba(X[fold == k])
        print(f"  fold {k + 1}/{folds}", flush=True)
    return P


def sheet(paths: list[str], captions: list[str], dest: Path, cell: int = 160, cols: int = 10) -> None:
    from PIL import Image, ImageDraw

    if not paths:
        return
    out = Image.new("RGB", (cell * cols, cell * ((len(paths) + cols - 1) // cols)), "white")
    for k, (p, c) in enumerate(zip(paths, captions)):
        with Image.open(p) as im:
            im = im.convert("RGB")
            im.thumbnail((cell, cell))
            out.paste(im, ((k % cols) * cell, (k // cols) * cell))
        ImageDraw.Draw(out).text(((k % cols) * cell + 3, (k // cols) * cell + 3), c, fill=(255, 0, 0))
    out.save(dest, quality=85)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--min-prob", type=float, default=0.9)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--z", type=float, default=8.0, help="how far from its label's photos counts as odd")
    args = ap.parse_args(argv)

    rows = [r for r in load_rows(args.data) if r["source"] in ("inat", "ami")]
    slug = MODEL.split("/")[-1].replace(":", "_")
    X, _ = embeddings(rows, args.data / "embeddings" / f"{slug}.npz", MODEL, 16, args.device)
    labels = np.array([r["label"] for r in rows])
    suspects = [{"path": rows[k]["path"], "label": rows[k]["label"], "check": "odd", "says": "", "prob": f"{zs:.1f}"}
                for k, zs in odd_ones(X, labels, args.z)]
    n_odd = len(suspects)
    y = np.array([r["class"] for r in rows])
    classes = sorted(set(y))
    P = out_of_fold(X, y, np.array([r["group"] for r in rows]))
    gone = {s["path"] for s in suspects}
    for k, r in enumerate(rows):
        j = int(P[k].argmax())
        if classes[j] != r["class"] and P[k, j] >= args.min_prob and r["path"] not in gone:
            suspects.append({"path": r["path"], "label": r["label"], "check": "label", "says": classes[j],
                             "prob": f"{P[k, j]:.2f}"})

    out = args.data / "clean"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "suspects.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["path", "label", "check", "says", "prob"])
        w.writeheader()
        w.writerows(suspects)
    for check in ("odd", "label"):
        for label in sorted({s["label"] for s in suspects if s["check"] == check}):
            some = [s for s in suspects if s["check"] == check and s["label"] == label][:150]
            sheet([s["path"] for s in some], [f"{s['says'][:10]} {s['prob']}" for s in some], out / f"{check}_{label}.jpg")
    by = {}
    for s in suspects:
        by.setdefault((s["check"], s["label"]), []).append(s)
    for (check, label), v in sorted(by.items()):
        print(f"  {check:9} {label:16} {len(v):4}")
    print(f"{n_odd} odd photos and {len(suspects) - n_odd} possible label errors of {len(rows)} web photos "
          f"-> {out / 'suspects.csv'} and the sheets beside it. Nothing was excluded: see the docstring.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
