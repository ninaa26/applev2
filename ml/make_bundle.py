"""Pack everything a training run needs into one folder (and a .zip) to carry to a machine with a CUDA GPU.

    python make_bundle.py                         # -> data/bundle/orchard-train/ and data/bundle/orchard-train.zip
    python make_bundle.py --max-side 384 --no-zip
    python make_bundle.py --what yolo             # -> data/bundle/orchard-yolo.zip: the detector run alone
    python make_bundle.py --what head             # -> data/bundle/orchard-head.zip: the moth-only species head

--what yolo and --what head each carry one run and a CLAUDE.md (from bundle_guides/) at the bundle's top, so
Claude Code on the training PC can be asked to "do what CLAUDE.md says": set up, check the GPU, train, and zip
the results to bring back. yolo: what train_yolo.py reads (the labelling site's newest fetched export and its
photos, the hand-labelled folders it falls back to, the blank liners, yolo11s.pt). head: moth_dataset.csv from
build_moth_dataset.py and every image it lists (web photos shrunk to --max-side), and the deployed head to
compare with.

data/ and models/ are not in git, so a clone of the repo cannot train anything. The bundle is a small copy
of ml/ that can: the scripts, data/training/classifier/dataset.csv, every image it lists, the cached BioCLIP 2
features, the held-out lists, the current head, and what train_yolo.py reads (the fully labelled field cards and
OFM liners, the blank liners).
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

import paths
from PIL import Image, ImageOps

HERE = Path(__file__).parent
D = paths.DATA
EXTRA = ["requirements-train.txt", "RUN_ON_CUDA.md", "README.md", paths.YOLO_START, f"{D}/README.md"]
OFM_LINERS = f"{D}/{paths.WEB_LINERS}/label/ofm-ervins"
DETECTOR = [f"{D}/{paths.FIELD}/labels.csv", f"{D}/{paths.FIELD}/species.csv",
            f"{OFM_LINERS}/labels.csv", f"{OFM_LINERS}/liners.json",
            f"{D}/{paths.WEB_LINERS}/species/manifest.csv", f"{D}/{paths.EXCLUDE}"]
DETECTOR_GLOBS = [f"{D}/{paths.FIELD}/inbox/*", f"{OFM_LINERS}/inbox/*", f"{D}/{paths.HELD_OUT}/*",
                  f"{D}/{paths.TRAP_STYLE}/*/blank_liners/*",
                  f"{D}/{paths.BENCH}/capture_2026-10-06/calibrated_*.jpg",
                  f"{Path(paths.CLASSIFIER_HEAD).parent}/*"]


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


GUIDES = HERE / "bundle_guides"  # <what>.md: the CLAUDE.md each one-run bundle carries


def yolo_files() -> list[Path]:
    """Everything train_yolo.py reads, relative to ml/: the same sources it would pick here."""
    import train_yolo

    sources, info = train_yolo.default_sources()
    files = [Path(D) / paths.HELD_OUT / p.name for p in (HERE / D / paths.HELD_OUT).iterdir()]
    if info["site_export"]:
        export = train_yolo.latest_site_export()
        files += [p.relative_to(HERE) for p in export.parent.iterdir() if p.suffix == ".csv"]
        files += [p.relative_to(HERE) for p in (HERE / D / paths.WEB_LINERS / "label").glob("*/liners.json")]
    for s in sources:
        files += [(s.inbox / photo).relative_to(HERE) for photo in s.labelled]
        for name in ("labels.csv", "liners.json"):
            if s.name != "site" and (s.inbox.parent / name).exists():
                files.append((s.inbox.parent / name).relative_to(HERE))
    for pattern in (f"{D}/{paths.BENCH}/capture_2026-10-06/calibrated_*.jpg", paths.YOLO_START):
        files += [p.relative_to(HERE) for p in sorted(HERE.glob(pattern))]
    return files


def one_run(what: str, out: Path, max_side: int, zip_it: bool) -> int:
    ml = out / "ml"
    for f in HERE.glob("*.py"):
        put(f, ml / f.name)
    for e in ["requirements-train.txt", "RUN_ON_CUDA.md", "README.md", f"{D}/README.md"]:
        put(HERE / e, ml / e)
    put(GUIDES / f"{what}.md", out / "CLAUDE.md")
    n = 0
    if what == "yolo":
        for rel in yolo_files():
            put(HERE / rel, ml / rel)
            n += 1
    else:
        with open(HERE / D / paths.MOTH_DATASET, newline="") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            src = HERE / r["path"]
            r["path"] = relative(r["path"])
            put(src, ml / r["path"], max_side if r["source"].startswith("web:") else 0)
            n += 1
            if n % 5000 == 0:
                print(f"  {n}/{len(rows)} images", flush=True)
        (ml / D / paths.MOTH_DATASET).parent.mkdir(parents=True, exist_ok=True)
        with open(ml / D / paths.MOTH_DATASET, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        for p in [*(HERE / D / paths.HELD_OUT).iterdir(), *(HERE / Path(paths.CLASSIFIER_HEAD).parent).glob("*")]:
            if p.is_file():
                put(p, ml / p.relative_to(HERE))
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1e9
    print(f"{what}: {n} files for the run, {size:.2f} GB in {out}")
    if zip_it:
        dest = out.with_suffix(".zip")
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_STORED) as z:  # no compression: it is nearly all JPEG
            for f in sorted(out.rglob("*")):
                if f.is_file():
                    z.write(f, Path(out.name) / f.relative_to(out))
        print(f"Wrote {dest} ({dest.stat().st_size / 1e9:.2f} GB)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--what", choices=["all", "yolo", "head"], default="all",
                    help="all: everything RUN_ON_CUDA.md runs; yolo or head: one run, with its CLAUDE.md")
    ap.add_argument("--out", type=Path, default=None,
                    help="default: data/bundle/orchard-train (all), orchard-yolo or orchard-head")
    ap.add_argument("--max-side", type=int, default=512, help="web photos are saved no larger than this")
    ap.add_argument("--no-zip", action="store_true")
    args = ap.parse_args(argv)
    if args.what != "all":
        out = args.out or HERE / D / f"bundle/orchard-{args.what}"
        if out.exists():
            shutil.rmtree(out)
        return one_run(args.what, out, args.max_side, not args.no_zip)
    args.out = args.out or HERE / D / "bundle/orchard-train"

    ml = args.out / "ml"
    for f in HERE.glob("*.py"):
        put(f, ml / f.name)
    for e in EXTRA:
        if (HERE / e).exists():
            put(HERE / e, ml / e)
    with open(HERE / D / paths.DATASET, newline="") as f:
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
    (ml / D / paths.DATASET).parent.mkdir(parents=True, exist_ok=True)
    with open(ml / D / paths.DATASET, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    import numpy as np

    for cache in (HERE / D / paths.EMBEDDINGS).glob("*.npz"):  # same photos, same features, bundle paths
        z = np.load(cache, allow_pickle=False)
        (ml / D / paths.EMBEDDINGS).mkdir(parents=True, exist_ok=True)
        np.savez(ml / D / paths.EMBEDDINGS / cache.name, paths=np.array([relative(k) for k in z["paths"].tolist()]),
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
