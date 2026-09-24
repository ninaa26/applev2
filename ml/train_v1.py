"""Model v0 and v1 species ID: BioCLIP 2 image features, zero-shot (v0) and with a trained linear head (v1).

    python train_v1.py                    # embed new photos, train, report on the test split
    python train_v1.py --final            # also report on our locked test cards (do this once, at the end)

Reads data/dataset.csv from build_dataset.py. Embeddings are cached in data/embeddings/, so
re-running after adding photos only embeds the new ones and then takes seconds.

v1 is a logistic regression on the (normalised) BioCLIP 2 image embedding, with class weights
balanced so the few OFM photos count as much as the many OBLR ones. The regularisation
strength is picked on the val split, then the head is refit on train + val.

Writes models/v1/head.npz (classes, weights, bias, model name), which the server's
`bioclip-v1` classifier loads, plus metrics.json and report.md.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

MODEL = "hf-hub:imageomics/bioclip-2"
# Same prompts as the server's zero-shot classifier (server/sentinel_server/pipeline/classify.py).
PROMPTS = {
    "CM": "a photo of Cydia pomonella, codling moth",
    "OFM": "a photo of Grapholita molesta, oriental fruit moth",
    "OBLR": "a photo of Choristoneura rosaceana, obliquebanded leafroller",
    "other_moth": "a photo of a small moth",
    "debris": "a photo of dirt, a leaf fragment or debris on sticky paper",
}


def load_rows(data: Path) -> list[dict]:
    with open(data / "dataset.csv", newline="") as f:
        return list(csv.DictReader(f))


class Embedder:
    def __init__(self, model_name: str):
        import open_clip
        import torch

        self.torch = torch
        self.device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(model_name)
        self.model = self.model.to(self.device).eval()
        self.tokenizer = open_clip.get_tokenizer(model_name)

    def images(self, paths: list[str], batch: int) -> np.ndarray:
        from PIL import Image

        torch, out = self.torch, []
        for start in range(0, len(paths), batch):
            ims = []
            for p in paths[start:start + batch]:
                with Image.open(p) as im:
                    ims.append(self.preprocess(im.convert("RGB")))
            with torch.no_grad():
                f = self.model.encode_image(torch.stack(ims).to(self.device))
            out.append(torch.nn.functional.normalize(f, dim=-1).float().cpu().numpy())
            done = min(start + batch, len(paths))
            if done % (batch * 10) == 0 or done == len(paths):
                print(f"  embedded {done}/{len(paths)}", flush=True)
        return np.concatenate(out) if out else np.zeros((0, 0), np.float32)

    def texts(self, prompts: list[str]) -> np.ndarray:
        torch = self.torch
        with torch.no_grad():
            f = self.model.encode_text(self.tokenizer(prompts).to(self.device))
        return torch.nn.functional.normalize(f, dim=-1).float().cpu().numpy()


def embeddings(rows: list[dict], cache: Path, model_name: str, batch: int) -> tuple[np.ndarray, Embedder | None]:
    """Row-aligned embedding matrix, computing only paths not already cached."""
    cached: dict[str, np.ndarray] = {}
    if cache.exists():
        z = np.load(cache, allow_pickle=False)
        cached = dict(zip(z["paths"].tolist(), z["feats"]))
    missing = sorted({r["path"] for r in rows} - cached.keys())
    embedder = None
    if missing:
        print(f"Embedding {len(missing)} new photos with {model_name} (cached: {len(cached)})")
        embedder = Embedder(model_name)
        cached.update(zip(missing, embedder.images(missing, batch)))
        cache.parent.mkdir(parents=True, exist_ok=True)
        paths = sorted(cached)
        np.savez(cache, paths=np.array(paths), feats=np.stack([cached[p] for p in paths]).astype(np.float16))
    return np.stack([cached[r["path"]] for r in rows]).astype(np.float32), embedder


def report(y_true: np.ndarray, y_pred: np.ndarray, classes: list[str]) -> dict:
    cm = np.zeros((len(classes), len(classes)), int)
    for t, p in zip(y_true, y_pred):
        cm[t, p] += 1
    per = {}
    for k, c in enumerate(classes):
        tp, support, predicted = cm[k, k], cm[k].sum(), cm[:, k].sum()
        prec = tp / predicted if predicted else 0.0
        rec = tp / support if support else 0.0
        per[c] = {"precision": prec, "recall": rec, "f1": 2 * prec * rec / (prec + rec) if prec + rec else 0.0,
                  "support": int(support)}
    recalls = [per[c]["recall"] for c in classes if per[c]["support"]]
    return {"accuracy": float((y_true == y_pred).mean()) if len(y_true) else 0.0,
            "balanced_accuracy": float(np.mean(recalls)) if recalls else 0.0,
            "per_class": per, "confusion": cm.tolist(), "classes": classes}


def format_report(name: str, r: dict) -> str:
    lines = [f"### {name}", "",
             f"Accuracy {r['accuracy']:.3f} · balanced accuracy (mean recall) {r['balanced_accuracy']:.3f}", "",
             "| class | precision | recall | F1 | photos |", "|---|---|---|---|---|"]
    for c, m in r["per_class"].items():
        lines.append(f"| {c} | {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f} | {m['support']} |")
    lines += ["", "Confusion matrix (rows = true, columns = predicted):", "",
              "| | " + " | ".join(r["classes"]) + " |", "|---" * (len(r["classes"]) + 1) + "|"]
    for c, row in zip(r["classes"], r["confusion"]):
        lines.append(f"| **{c}** | " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--out", type=Path, default=Path("models/v1"))
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--final", action="store_true", help="also evaluate on the locked test cards")
    args = ap.parse_args(argv)

    from sklearn.linear_model import LogisticRegression

    rows = [r for r in load_rows(args.data) if r["split"] != "locked" or args.final]
    slug = args.model.split("/")[-1].replace(":", "_")
    X, embedder = embeddings(rows, args.data / "embeddings" / f"{slug}.npz", args.model, args.batch)

    classes = sorted({r["class"] for r in rows if r["split"] == "train"})
    idx = {c: k for k, c in enumerate(classes)}
    keep = np.array([r["class"] in idx for r in rows])
    rows, X = [r for r, k in zip(rows, keep) if k], X[keep]
    y = np.array([idx[r["class"]] for r in rows])
    split = np.array([r["split"] for r in rows])
    tr, va, te, lk = (split == s for s in ("train", "val", "test", "locked"))
    synth = np.array([r["source"] == "synth" for r in rows])
    tests = {"test · web photos": te & ~synth, "test · trap-style": te & synth}
    tests = {k: m for k, m in tests.items() if m.any()}
    print(f"Classes {classes}; train {tr.sum()}, val {va.sum()}, test {te.sum()} "
          f"({(te & synth).sum()} trap-style), locked {lk.sum()}")

    results = {}
    # v0: zero-shot, text prompts only.
    embedder = embedder or Embedder(args.model)
    T = embedder.texts([PROMPTS[c] for c in classes])
    for name, m in tests.items():
        results[f"v0 zero-shot · {name}"] = report(y[m], (X[m] @ T.T).argmax(1), classes)

    # v1: pick C on val, then refit on train + val.
    best = None
    for C in (0.3, 1, 3, 10, 30, 100):
        clf = LogisticRegression(C=C, class_weight="balanced", max_iter=3000).fit(X[tr], y[tr])
        score = report(y[va], clf.predict(X[va]), classes)["balanced_accuracy"]
        print(f"  C={C:<5} val balanced accuracy {score:.3f}")
        if best is None or score > best[1]:
            best = (C, score)
    C = best[0]
    trva = tr | va
    clf = LogisticRegression(C=C, class_weight="balanced", max_iter=3000).fit(X[trva], y[trva])
    for name, m in tests.items():
        results[f"v1 linear head (C={C}) · {name}"] = report(y[m], clf.predict(X[m]), classes)
    if args.final and lk.any():
        results["v0 zero-shot · LOCKED own cards"] = report(y[lk], (X[lk] @ T.T).argmax(1), classes)
        results[f"v1 linear head · LOCKED own cards"] = report(y[lk], clf.predict(X[lk]), classes)

    args.out.mkdir(parents=True, exist_ok=True)
    np.savez(args.out / "head.npz", classes=np.array(classes), W=clf.coef_.astype(np.float32),
             b=clf.intercept_.astype(np.float32), model=np.array(args.model))
    (args.out / "metrics.json").write_text(json.dumps(results, indent=2))
    by_source = {s: int(sum(1 for r in rows if r["source"] == s and r["split"] == "train"))
                 for s in ("inat", "ami", "own", "synth")}
    md = ["# Species ID v0 / v1", "",
          f"BioCLIP 2 image features. Training photos by source: {by_source}.",
          "Test = held-out **web photos** (grouped by observation), and their **trap-style** copies (the same",
          "moths cut out and pasted onto our liner photos at trap resolution, make_trap_style.py). Neither is",
          "a real moth on a real liner, so treat both as sanity checks; the report's numbers come from `--final`",
          "on our own locked cards.",
          "BioCLIP 2 was itself trained on iNaturalist/GBIF photos (TreeOfLife-200M), so it has likely seen",
          "many of these test photos with their species names. Web-photo scores are optimistic for that reason too.", ""]
    md += [format_report(k, v) for k, v in results.items()]
    (args.out / "report.md").write_text("\n".join(md))
    for k, v in results.items():
        print("\n" + format_report(k, v))
    print(f"Saved {args.out / 'head.npz'}, metrics.json, report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
