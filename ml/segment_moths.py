"""Cut the moth out of every web photo with flatbug, for pasting onto liner photos (make_trap_style.py).

    python segment_moths.py                 # all web photos in data/dataset.csv; resumable
    python segment_moths.py --limit 50      # quick look

flatbug (github.com/darsa-group/flat-bug, MIT) is a pretrained arthropod instance segmenter.
Each photo is shrunk to 640 px, the most confident insect is kept if it is confident enough and
not a sliver or the whole frame, and saved as an RGBA PNG cropped to the insect:
data/cutouts/<label>/<name>.png. data/cutouts/manifest.csv lists every photo tried (also the
misses), so a re-run only does new photos.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

FIELDS = ["path", "label", "cutout", "conf", "area_frac", "status"]


def load_done(manifest: Path) -> dict[str, dict]:
    if not manifest.exists():
        return {}
    with open(manifest, newline="") as f:
        return {r["path"]: r for r in csv.DictReader(f)}


def cut(predictor, path: str, size: int, min_conf: float) -> tuple[Image.Image | None, float, float, str]:
    import torch

    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
    im.thumbnail((size, size))
    t = torch.from_numpy(np.asarray(im).copy()).permute(2, 0, 1)
    pred = predictor(t, path=path, single_scale=True)
    if not len(pred):
        return None, 0.0, 0.0, "no insect"
    k = int(torch.argmax(pred.confs))
    conf = float(pred.confs[k])
    poly = [(int(x), int(y)) for x, y in pred.contours[k].cpu().numpy()]  # (x, y) image pixels
    mask = Image.new("L", im.size, 0)
    if len(poly) >= 3:
        ImageDraw.Draw(mask).polygon(poly, fill=255)
    m = np.asarray(mask) > 0
    frac = float(m.mean())
    if conf < min_conf:
        return None, conf, frac, "low confidence"
    if frac < 0.01 or frac > 0.85:
        return None, conf, frac, "bad mask size"
    ys, xs = np.nonzero(m)
    box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    rgba = im.copy()
    rgba.putalpha(mask)
    return rgba.crop(box), conf, frac, "ok"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--weights", default="flat_bug_M.pt", help="downloaded to the working dir on first use")
    ap.add_argument("--size", type=int, default=640)
    ap.add_argument("--min-conf", type=float, default=0.5)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    import torch
    from flat_bug.predictor import Predictor

    with open(args.data / "dataset.csv", newline="") as f:
        rows = [r for r in csv.DictReader(f) if r["source"] in ("inat", "ami")]
    out = args.data / "cutouts"
    manifest = out / "manifest.csv"
    done = load_done(manifest)
    todo = [r for r in rows if r["path"] not in done]
    if args.limit:
        todo = todo[:args.limit]
    print(f"{len(rows)} web photos, {len(done)} already tried, {len(todo)} to do")
    if not todo:
        return 0

    # flat-bug compares device strings exactly: tensors report "mps:0", not "mps"
    device = "mps:0" if torch.backends.mps.is_available() else "cuda:0" if torch.cuda.is_available() else "cpu"
    predictor = Predictor(model=args.weights, device=device, dtype="float32")

    out.mkdir(parents=True, exist_ok=True)
    new = not manifest.exists()
    t0 = time.time()
    with open(manifest, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        for n, r in enumerate(todo, 1):
            name = f"{r['source']}_{Path(r['path']).stem}.png"
            dest = out / r["label"] / name
            try:
                img, conf, frac, status = cut(predictor, r["path"], args.size, args.min_conf)
            except Exception as e:  # a corrupt photo shouldn't stop an hour-long run
                img, conf, frac, status = None, 0.0, 0.0, f"error: {e}"[:120]
            if img is not None:
                dest.parent.mkdir(parents=True, exist_ok=True)
                img.save(dest)
            w.writerow({"path": r["path"], "label": r["label"], "cutout": str(dest) if img else "",
                        "conf": f"{conf:.3f}", "area_frac": f"{frac:.3f}", "status": status})
            if n % 200 == 0 or n == len(todo):
                f.flush()
                rate = n / (time.time() - t0)
                print(f"  {n}/{len(todo)}  {rate:.1f}/s  ~{(len(todo) - n) / rate / 60:.0f} min left", flush=True)

    done = load_done(manifest)
    ok = sum(1 for r in done.values() if r["status"] == "ok")
    print(f"Cutouts: {ok}/{len(done)} photos ({ok / max(len(done), 1):.0%}) in {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
