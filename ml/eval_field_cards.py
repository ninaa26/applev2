"""Score the v1 head on labelled crops from photos of used field cards.

    python eval_field_cards.py                       # models/v1/head.npz on data/field/labels.csv
    python eval_field_cards.py --head models/v1/head.npz --trap-ppm 8
    python eval_field_cards.py --mask-neighbours     # grey out the other boxes inside each crop

Pass 1 labels (label_field_cards.py) are coarse: moth / other_insect / debris. The head's moth
classes (CM, OFM, OBLR, other_moth) all count as "moth" here, so this scores whether it tells a
moth from bycatch from debris, not the species; boxes with species from pass 2 are scored both ways.
Each crop is scored twice: as photographed (a sharp phone close-up), and shrunk to the trap
camera's resolution (--trap-ppm px/mm, from the card's grid), which is what the trap will see.

Crops whose cutout was pasted into the training set (make_trap_style.py --field, listed in
data/synth/manifest.csv) are reported apart as "seen in training". That assumes the head was
trained on the current manifest: re-run train_v1.py after make_trap_style.py --field.
--mask-neighbours fills every other box inside a crop with the card's colour first, so a crop
around a bit of debris next to a moth shows only the debris (the server's square, padded crop
otherwise takes in neighbours). Writes data/field/eval.md and predictions.csv (eval-masked.md and
predictions-masked.csv with --mask-neighbours).
"""

from __future__ import annotations

import argparse
import csv
import sys
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from build_dataset import CLASS_OF
from crop_field_cards import PAD
from train_v1 import Embedder

MOTH_CLASSES = {"CM", "OFM", "OBLR", "other_moth"}
COARSE = ["moth", "other_insect", "debris"]


def coarse(label: str) -> str:
    return "moth" if label == "moth" or CLASS_OF.get(label) in MOTH_CLASSES else label


def trap_res(src: str, ppm: float, trap_ppm: float, dest: Path) -> str:
    """The crop as the trap camera would see it: shrunk to trap_ppm px/mm (never enlarged)."""
    with Image.open(src) as im:
        im = im.convert("RGB")
        s = trap_ppm / ppm
        if s < 1:
            im = im.resize((max(8, round(im.width * s)), max(8, round(im.height * s))), Image.LANCZOS)
        im.save(dest, quality=85)
    return str(dest)


def masked_crop(photo: Image.Image, box: tuple, others: list[tuple], dest: Path) -> str:
    """The server's padded square crop, with every other box in it filled with the card's colour."""
    x1, y1, x2, y2 = box
    side = max(x2 - x1, y2 - y1) * (1 + 2 * PAD)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    ox, oy = int(cx - side / 2), int(cy - side / 2)
    c = photo.crop((ox, oy, ox + int(side), oy + int(side)))
    a = np.asarray(c).copy()
    free = np.ones(a.shape[:2], bool)
    for bx1, by1, bx2, by2 in [box] + others:
        free[max(0, by1 - oy):max(0, by2 - oy), max(0, bx1 - ox):max(0, bx2 - ox)] = False
    fill = np.median(a[free], axis=0) if free.any() else np.median(a.reshape(-1, 3), axis=0)
    for bx1, by1, bx2, by2 in others:
        a[max(0, by1 - oy):max(0, by2 - oy), max(0, bx1 - ox):max(0, bx2 - ox)] = fill
    own = np.asarray(c)[max(0, y1 - oy):max(0, y2 - oy), max(0, x1 - ox):max(0, x2 - ox)]
    a[max(0, y1 - oy):max(0, y2 - oy), max(0, x1 - ox):max(0, x2 - ox)] = own  # its own box stays whole
    Image.fromarray(a).save(dest, quality=92)
    return str(dest)


def table(title: str, truth: list[str], pred: list[str], labels: list[str]) -> list[str]:
    n = len(truth)
    if not n:
        return [f"### {title}", "", "(none)", ""]
    acc = sum(t == p for t, p in zip(truth, pred)) / n
    rec = [sum(1 for t, p in zip(truth, pred) if t == p == c) / max(1, truth.count(c)) for c in labels if c in truth]
    out = [f"### {title}", "", f"{n} crops · accuracy {acc:.2f} · balanced accuracy {np.mean(rec):.2f}", "",
           "| true \\ predicted | " + " | ".join(labels) + " | recall |", "|---" * (len(labels) + 2) + "|"]
    for c in labels:
        if c not in truth:
            continue
        row = [sum(1 for t, p in zip(truth, pred) if t == c and p == d) for d in labels]
        out.append(f"| **{c}** | " + " | ".join(map(str, row)) + f" | {row[labels.index(c)] / sum(row):.2f} |")
    return out + [""]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data/field"))
    ap.add_argument("--head", type=Path, default=Path("models/v1/head.npz"))
    ap.add_argument("--trap-ppm", type=float, default=8.0, help="trap camera px/mm (webcam ~7, Camera Module 3 ~15)")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--mask-neighbours", action="store_true", help="grey out the other boxes inside each crop")
    args = ap.parse_args(argv)
    suffix = "-masked" if args.mask_neighbours else ""

    head = np.load(args.head)
    classes = [str(c) for c in head["classes"]]
    manifest = args.data.parent / "synth" / "manifest.csv"
    trained = set()
    if manifest.exists():
        with open(manifest, newline="") as f:
            trained = {Path(r["path"]).stem.removeprefix("field_").rsplit("_", 1)[0]
                       for r in csv.DictReader(f) if Path(r["path"]).name.startswith("field_")}
    with open(args.data / "labels.csv", newline="") as f:
        everything = list(csv.DictReader(f))
    rows = [r for r in everything if r["label"] not in ("", "skip")]
    box = lambda r: tuple(int(r[k]) for k in ("x1", "y1", "x2", "y2"))  # noqa: E731
    print(f"{len(rows)} labelled crops; head classes {classes}")

    emb = Embedder(str(head["model"]), args.device)
    preds = {}
    with tempfile.TemporaryDirectory() as tmp:
        crops = [r["crop"] for r in rows]
        if args.mask_neighbours:  # every box flatbug or a person drew is a detection the server would mask
            for photo in sorted({r["photo"] for r in rows}):
                with Image.open(args.data / "inbox" / photo) as im:
                    img = ImageOps.exif_transpose(im).convert("RGB")
                boxes = [(r, box(r)) for r in everything if r["photo"] == photo]
                for k, r in enumerate(rows):
                    if r["photo"] == photo:
                        crops[k] = masked_crop(img, box(r), [b for o, b in boxes if o is not r], Path(tmp) / f"m{k}.jpg")
        small = [trap_res(c, float(r["ppm"]), args.trap_ppm, Path(tmp) / f"{k}.jpg") if r["ppm"] else c
                 for k, (r, c) in enumerate(zip(rows, crops))]
        for name, paths in (("phone", crops), ("trap", small)):
            X = emb.images(paths, 16)
            logits = (X @ head["W"].T + head["b"]) / (float(head["T"]) if "T" in head else 1.0)  # as the server does
            p = np.exp(logits - logits.max(1, keepdims=True))
            p /= p.sum(1, keepdims=True)
            preds[name] = [(classes[i], float(p[k, i])) for k, i in enumerate(p.argmax(1))]

    for r, ph, tr in zip(rows, preds["phone"], preds["trap"]):
        r["seen"] = bool(r["cutout"]) and Path(r["cutout"]).stem in trained
        r["pred_phone"], r["p_phone"] = ph
        r["pred_trap"], r["p_trap"] = tr

    md = [f"# Field cards · {args.head}{' · neighbours masked' if args.mask_neighbours else ''}", "",
          f"{len(rows)} labelled crops from {len({r['photo'] for r in rows})} photos of used field cards "
          f"(phone, daylight, Trécé liners). Model classes folded to moth / other_insect / debris. "
          f"'trap' = shrunk to {args.trap_ppm:g} px/mm. Insects and debris pasted into training are reported apart.", ""]
    for name in ("trap", "phone"):
        unseen = [r for r in rows if not r["seen"]]
        md += table(f"{name} resolution · not in training", [coarse(r["label"]) for r in unseen],
                    [coarse(r[f"pred_{name}"]) for r in unseen], COARSE)
        seen = [r for r in rows if r["seen"]]
        md += table(f"{name} resolution · seen in training (optimistic)", [coarse(r["label"]) for r in seen],
                    [coarse(r[f"pred_{name}"]) for r in seen], COARSE)
    moths = [r for r in rows if coarse(r["label"]) == "moth"]
    md += ["### What the moths were called (trap resolution)", "",
           "| photo | moths | " + " | ".join(classes) + " |", "|---" * (len(classes) + 2) + "|"]
    for photo in sorted({r["photo"] for r in moths}):
        c = Counter(r["pred_trap"] for r in moths if r["photo"] == photo)
        md.append(f"| {photo.replace('.RAW-01.COVER', '')} | {sum(c.values())} | " + " | ".join(str(c[k]) for k in classes) + " |")
    md.append("")
    (args.data / f"eval{suffix}.md").write_text("\n".join(md))
    fields = ["photo", "n", "label", "source", "seen", "pred_trap", "p_trap", "pred_phone", "p_phone", "length_mm", "crop"]
    with open(args.data / f"predictions{suffix}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
