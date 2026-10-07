"""Score a species head on real insects on real liners, the way the server would treat each one.

    python eval_liner_species.py                                  # models/v1/head.npz
    python eval_liner_species.py --head models/v1/head.npz models/v1-no-liner/head.npz

Reads the real-liner crops in data/dataset.csv (source "liner": liner_crops.py, then build_dataset.py). The
web-photo and trap-style tests in train_v1.py are photos BioCLIP 2 has probably seen and paste-ups of them;
these are moths that sat on glue, photographed on the liner. The species is the uploader's claim and the
liner, camera and light are not ours, so this is a development check for choosing between heads and settings;
the report's numbers come from our own locked cards.

Recall comes with a 95% Wilson interval, because the held-out sets are small (4 debris crops say nothing).
After the tables, recall by crop size (the crop's long side in px, as the classifier receives it): a head that
is fine on 200 px crops and poor on 80 px ones is poor at the card's edges.

One table per head, split and resolution (the px/mm each crop was shrunk to): what the true class was called,
and what the server does with it (pipeline/track.py: confidence >= 0.80 is counted automatically, 0.50-0.80
goes to review, below is "unknown"). "Auto & wrong" is the costly error: a count nobody looks at.
  held out          liners and cards no head trains on (liner_crops.TEST_GROUPS): the score to quote.
  used in training  the other liners: only a fair test for a head trained without them.
A head's temperature (train_v1.py) is applied, as the server applies it. Embeddings come from the same cache
as train_v1.py. Writes data/web_liners/species/report.md and predictions.csv.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

import numpy as np

from train_v1 import embeddings, load_rows, softmax

AUTO, REVIEW = 0.80, 0.50  # server/sentinel_server/pipeline/track.py
MOTHS = {"CM", "OFM", "OBLR", "other_moth"}


def head_probs(head, X: np.ndarray) -> tuple[list[str], np.ndarray]:
    """Class probabilities the way the server computes them (classify.linear_head_probs)."""
    T = float(head["T"]) if "T" in head else 1.0
    return [str(c) for c in head["classes"]], softmax((X @ head["W"].T + head["b"]) / T)


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% interval for a proportion from k of n."""
    if n == 0:
        return 0.0, 1.0
    p, d = k / n, 1 + z * z / n
    c, h = (p + z * z / (2 * n)) / d, z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return max(0.0, c - h), min(1.0, c + h)


SIZES = [(0, 80), (80, 120), (120, 180), (180, 10_000)]  # crop long side, px


def by_size(title: str, rows: list[dict], classes: list[str], p: np.ndarray, side: list[int]) -> list[str]:
    pred = p.argmax(1)
    md = [f"### {title} · recall by crop size (held out, all resolutions)", "",
          "| true | " + " | ".join(f"{a}–{b} px" if b < 10_000 else f"{a}+ px" for a, b in SIZES) + " |",
          "|---" * (len(SIZES) + 1) + "|"]
    for truth in sorted({r["class"] for r in rows}):
        cells = []
        for a, b in SIZES:
            idx = [k for k, r in enumerate(rows) if r["class"] == truth and a <= side[k] < b]
            cells.append(f"{sum(classes[pred[k]] == truth for k in idx)}/{len(idx)}" if idx else "–")
        md.append(f"| {truth} | " + " | ".join(cells) + " |")
    return md + [""]


def table(title: str, rows: list[dict], classes: list[str], p: np.ndarray) -> list[str]:
    if not rows:
        return []
    pred, conf = p.argmax(1), p.max(1)
    md = [f"### {title}", "", "| set | true | crops | " + " | ".join(classes)
          + " | recall | as moth | auto & right | auto & wrong | review | unknown |", "|---" * (len(classes) + 9) + "|"]
    for name, truth in sorted({(r["set"], r["class"]) for r in rows}):
        idx = [k for k, r in enumerate(rows) if r["set"] == name and r["class"] == truth]
        called = Counter(classes[pred[k]] for k in idx)
        right = np.array([classes[pred[k]] == truth for k in idx])
        auto = conf[idx] >= AUTO
        md.append(f"| {name} | {truth} | {len(idx)} | " + " | ".join(str(called[c]) for c in classes)
                  + " | {:.2f} ({:.2f}–{:.2f})".format(right.mean(), *wilson(int(right.sum()), len(idx)))
                  + f" | {sum(called[c] for c in MOTHS) / len(idx):.2f}"
                  f" | {(auto & right).mean():.2f} | {(auto & ~right).mean():.2f}"
                  f" | {((conf[idx] >= REVIEW) & ~auto).mean():.2f} | {(conf[idx] < REVIEW).mean():.2f} |")
    return md + [""]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--head", type=Path, nargs="+", default=[Path("models/v1/head.npz")])
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args(argv)

    out = args.data / "web_liners" / "species"
    with open(out / "manifest.csv", newline="") as f:
        meta = {r["path"]: r for r in csv.DictReader(f)}
    rows = [{**r, "set": meta[r["path"]]["set"], "ppm": meta[r["path"]]["ppm"]}
            for r in load_rows(args.data) if r["source"] == "liner" and r["path"] in meta]
    if not rows:
        raise SystemExit("no real-liner crops in dataset.csv: run liner_crops.py, then build_dataset.py")
    heads = {str(h): np.load(h, allow_pickle=False) for h in args.head}
    models = {str(h["model"]) for h in heads.values()}
    if len(models) != 1:
        raise SystemExit(f"heads use different feature models: {models}")
    model = models.pop()
    slug = model.split("/")[-1].replace(":", "_")
    X, _ = embeddings(rows, args.data / "embeddings" / f"{slug}.npz", model, args.batch, args.device)

    from PIL import Image

    side = []
    for r in rows:
        with Image.open(r["path"]) as im:
            side.append(max(im.size))
    bucket = lambda r: max((p for p in (15.0, 10.0) if float(r["ppm"]) >= p - 0.5), default=10.0)  # noqa: E731
    md = ["# Species on real liners (uploader's species; a development check, not trap accuracy)", "",
          f"{len(rows)} crops of {len({(r['path'].rsplit('/', 1)[-1]) for r in rows})} insects from "
          f"{len({r['group'] for r in rows})} liners and cards. Auto = confidence ≥ {AUTO:.2f} (counted with no one "
          f"looking), review = {REVIEW:.2f}–{AUTO:.2f}, unknown = below.", ""]
    preds = [dict(path=r["path"], set=r["set"], truth=r["class"], split=r["split"], ppm=r["ppm"]) for r in rows]
    for name, head in heads.items():
        classes, p = head_probs(head, X)
        T = f" · T={float(head['T']):.2f}" if "T" in head else ""
        for split, what in (("test", "held out"), ("", "used in training")):
            for ppm in (15.0, 10.0):
                keep = [k for k, r in enumerate(rows) if (r["split"] == "test") == (split == "test") and bucket(r) == ppm]
                md += table(f"{name}{T} · {what} · {ppm:g} px/mm", [rows[k] for k in keep], classes, p[keep])
        held = [k for k, r in enumerate(rows) if r["split"] == "test"]
        md += by_size(f"{name}{T}", [rows[k] for k in held], classes, p[held], [side[k] for k in held])
        for r, k, c in zip(preds, p.argmax(1), p.max(1)):
            r[f"pred {name}"], r[f"conf {name}"] = classes[k], f"{c:.3f}"
    (out / "report.md").write_text("\n".join(md))
    with open(out / "predictions.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(preds[0]))
        w.writeheader()
        w.writerows(preds)
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
