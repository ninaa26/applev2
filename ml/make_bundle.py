"""Pack everything a training run needs into one folder (and a .zip) to carry to a machine with a CUDA GPU.

    python make_bundle.py                         # -> data/bundle/orchard-train/ and data/bundle/orchard-train.zip
    python make_bundle.py --max-side 384 --no-zip

data/ and models/ are not in git, so a clone of the repo cannot train anything. The bundle is a small copy
of ml/ that can: the scripts, data/dataset.csv, every image it lists, the cached BioCLIP 2 features, the
current head, and what train_yolo.py reads (the fully labelled field cards and OFM liners, the blank liners).
Paths inside are the same as here, so the scripts run unchanged from the bundle's ml/ folder. RUN_ON_CUDA.md
(copied in) has the commands.

Web photos are saved no larger than --max-side px (they are up to 2048 px and the CNN reads them at 224), which
takes the bundle from ~5 GB to about 1 GB. Crops, trap-style photos and the detector's photos are copied as
they are. The cached features were computed from the full-size photos; that makes no difference to
train_v1.py, which only looks photos up by path. Some rows of dataset.csv hold absolute paths (photos fetched
with --out given in full); the bundle's dataset.csv and feature cache get them rewritten relative to ml/, or
they would point at this Mac.
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
import zipfile
from pathlib import Path

from PIL import Image, ImageOps

HERE = Path(__file__).parent
EXTRA = ["requirements-train.txt", "RUN_ON_CUDA.md", "README.md", "yolo11s.pt"]
DETECTOR = ["data/field/labels.csv", "data/field/test_cards.txt", "data/field/species.csv",
            "data/web_liners/label/ofm-ervins/labels.csv", "data/web_liners/label/ofm-ervins/liners.json",
            "data/web_liners/species/manifest.csv", "data/exclude.csv"]
DETECTOR_GLOBS = ["data/field/inbox/*", "data/web_liners/label/ofm-ervins/inbox/*", "data/liners/*",
                  "data/trap_camera/capture_2026-10-06/calibrated_*.jpg", "models/v1/*"]


def relative(path: str) -> str:
    """A dataset path as it will be inside the bundle: relative to ml/, forward slashes."""
    q = Path(path)
    if q.is_absolute():
        q = q.resolve().relative_to(HERE.resolve())
    return q.as_posix()


def put(src: Path, dest: Path, max_side: int = 0) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    if max_side:
        with Image.open(src) as im:
            if max(im.size) > max_side:
                im = ImageOps.exif_transpose(im).convert("RGB")
                im.thumbnail((max_side, max_side), Image.LANCZOS)
                im.save(dest, quality=90)
                return
    shutil.copyfile(src, dest)  # follows links: the labeller's inbox is links into other folders


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=HERE / "data/bundle/orchard-train")
    ap.add_argument("--max-side", type=int, default=512, help="web photos are saved no larger than this")
    ap.add_argument("--no-zip", action="store_true")
    args = ap.parse_args(argv)

    ml = args.out / "ml"
    for f in list(HERE.glob("*.py")) + [HERE / e for e in EXTRA]:
        if f.exists():
            put(f, ml / f.name)
    with open(HERE / "data/dataset.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    missing = 0
    for n, r in enumerate(rows, 1):
        src = HERE / r["path"]  # an absolute r["path"] stays as it is
        r["path"] = relative(r["path"])
        if not src.exists():
            missing += 1
            continue
        put(src, ml / r["path"], args.max_side if r["source"] in ("inat", "ami") else 0)
        if n % 5000 == 0:
            print(f"  {n}/{len(rows)} images", flush=True)
    (ml / "data").mkdir(parents=True, exist_ok=True)
    with open(ml / "data/dataset.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    import numpy as np

    for cache in (HERE / "data/embeddings").glob("*.npz"):  # same photos, same features, bundle paths
        z = np.load(cache, allow_pickle=False)
        (ml / "data/embeddings").mkdir(parents=True, exist_ok=True)
        np.savez(ml / "data/embeddings" / cache.name, paths=np.array([relative(k) for k in z["paths"].tolist()]),
                 feats=z["feats"])
    extra = 0
    for rel in DETECTOR:
        if (HERE / rel).exists():
            put(HERE / rel, ml / rel)
    for pattern in DETECTOR_GLOBS:
        for src in sorted(HERE.glob(pattern)):
            if src.is_file():
                put(src, ml / src.relative_to(HERE))
                extra += 1
    size = sum(p.stat().st_size for p in args.out.rglob("*") if p.is_file()) / 1e9
    print(f"{len(rows) - missing} dataset images ({missing} missing), {extra} other files, {size:.2f} GB in {args.out}")
    if not args.no_zip:
        dest = args.out.with_suffix(".zip")
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_STORED) as z:  # no compression: it is nearly all JPEG
            for f in sorted(args.out.rglob("*")):
                if f.is_file():
                    z.write(f, Path(args.out.name) / f.relative_to(args.out))
        print(f"Wrote {dest} ({dest.stat().st_size / 1e9:.2f} GB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
