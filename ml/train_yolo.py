"""Model v2 detector: train YOLO11 on the liner photos whose boxes were all checked by hand.

    python train_yolo.py                          # build data/yolo/, train yolo11s, report on the held-out photos
    python train_yolo.py --model yolo11n.pt       # smaller, a candidate for the Pi
    python train_yolo.py --build-only             # just write the tiles and data.yaml
    python train_yolo.py --synth 3000 --out data/yolo-synth   # also paste AMI/iNat insects onto training tiles

Only photos where every box was looked at go in: all of data/field/ (crop_field_cards.py + label_field_cards.py)
and the ofm-ervins liner photos with no box still unlabelled. The other Roboflow sets are left out, since only the
target moth was boxed there, so their bycatch would teach the model that insects are background. `skip` rows
(not an insect / off the card) are background too. Classes are pass-1 labels: moth, other_insect, debris.

Each photo is shrunk to --ppm px/mm (what the trap camera sees; from the printed grid, the `ppm` column) and cut
into overlapping --tile px tiles, so moths are the size they'll be in the trap. Held out, split by card/liner:
data/field/test_cards.txt plus --val-photos (a liner's other days never train either: liners.json).
--synth N adds N training tiles with web-photo insects pasted on (AMI and iNaturalist, cut out by segment_moths.py,
so their species label is right and their box exact): a random training tile, keeping its own boxes, or a blank liner
from data/liners/, gets 2-12 cutouts at their species' real length (make_trap_style.LENGTH_MM), any angle, tinted by
the liner's light, with a contact shadow, then blurred and noised. Moths become `moth`, bycatch `other_insect`.
Cutouts of held-out photos' groups don't matter here (the held-out set is our liners, not web photos), and the
held-out tiles never get pasted on. Writes data/yolo/ (tiles + data.yaml) and models/yolo11/<run>/ (weights/best.pt, results).
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import statistics
import sys
from pathlib import Path

from PIL import Image, ImageOps

HERE = Path(__file__).parent
CLASSES = ["moth", "other_insect", "debris"]
SOURCES = [HERE / "data/field", HERE / "data/web_liners/label/ofm-ervins"]
VAL_PHOTOS = ["om20180514_121032_1", "ap20210804_115441_3"]  # standalone OFM liners, fully labelled


def labelled_photos(data: Path) -> dict[str, list[dict]]:
    """Photo -> its rows, for photos with no box left unlabelled."""
    rows: dict[str, list[dict]] = {}
    with open(data / "labels.csv", newline="") as f:
        for r in csv.DictReader(f):
            rows.setdefault(r["photo"], []).append(r)
    return {p: rs for p, rs in rows.items() if all(r["label"] for r in rs)}


def held_out(data: Path, val_photos: list[str]) -> set[str]:
    out = set()
    test = data / "test_cards.txt"
    if test.exists():
        out |= {ln.strip() for ln in test.read_text().splitlines() if ln.strip() and not ln.startswith("#")}
    names = [p.name for p in (data / "inbox").iterdir()]
    out |= {n for n in names if any(n.startswith(v) for v in val_photos)}
    liners = data / "liners.json"
    if liners.exists():  # the same liner on other days stays on the same side
        for group in json.loads(liners.read_text()):
            if out & set(group):
                out |= set(group)
    return out


def tiles(w: int, h: int, tile: int, overlap: int):
    step = tile - overlap
    xs = list(range(0, max(w - tile, 0) + 1, step)) or [0]
    ys = list(range(0, max(h - tile, 0) + 1, step)) or [0]
    if xs[-1] + tile < w:
        xs.append(w - tile)
    if ys[-1] + tile < h:
        ys.append(h - tile)
    for y in ys:
        for x in xs:
            yield x, y


def build(out: Path, ppm: float, tile: int, overlap: int, val_photos: list[str], min_visible: float) -> dict:
    if out.exists():
        shutil.rmtree(out)
    stats = {"train": {"photos": 0, "tiles": 0, "boxes": 0}, "val": {"photos": 0, "tiles": 0, "boxes": 0}}
    per_class = {s: {c: 0 for c in CLASSES} for s in stats}
    for data in SOURCES:
        val = held_out(data, val_photos)
        for photo, rows in sorted(labelled_photos(data).items()):
            split = "val" if photo in val else "train"
            boxes = [r for r in rows if r["label"] in CLASSES]
            ppms = [float(r["ppm"]) for r in rows if r.get("ppm")]
            scale = min(1.0, ppm / statistics.median(ppms)) if ppms else 1.0
            with Image.open(data / "inbox" / photo) as im:
                img = ImageOps.exif_transpose(im).convert("RGB")
            if scale < 1:
                img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
            stem = f"{data.name}__{Path(photo).stem}"
            for d in ("images", "labels"):
                (out / d / split).mkdir(parents=True, exist_ok=True)
            stats[split]["photos"] += 1
            for tx, ty in tiles(img.width, img.height, tile, overlap):
                tw, th = min(tile, img.width), min(tile, img.height)
                lines = []
                for r in boxes:
                    x1, y1, x2, y2 = (float(r[k]) * scale for k in ("x1", "y1", "x2", "y2"))
                    cx1, cy1, cx2, cy2 = max(x1, tx), max(y1, ty), min(x2, tx + tw), min(y2, ty + th)
                    if cx2 <= cx1 or cy2 <= cy1:
                        continue
                    if (cx2 - cx1) * (cy2 - cy1) < min_visible * (x2 - x1) * (y2 - y1):
                        continue  # mostly in the next tile, which has it whole
                    lines.append(f"{CLASSES.index(r['label'])} {((cx1 + cx2) / 2 - tx) / tw:.6f} "
                                 f"{((cy1 + cy2) / 2 - ty) / th:.6f} {(cx2 - cx1) / tw:.6f} {(cy2 - cy1) / th:.6f}")
                    per_class[split][r["label"]] += 1
                name = f"{stem}_{tx}_{ty}"
                img.crop((tx, ty, tx + tw, ty + th)).save(out / "images" / split / f"{name}.jpg", quality=95)
                (out / "labels" / split / f"{name}.txt").write_text("\n".join(lines))
                stats[split]["tiles"] += 1
                stats[split]["boxes"] += len(lines)
    (out / "data.yaml").write_text(
        f"path: {out.resolve()}\ntrain: images/train\nval: images/val\nnames:\n"
        + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES)))
    return {"splits": stats, "boxes_per_class": per_class, "ppm": ppm, "tile": tile, "overlap": overlap}


def web_class(label: str) -> str:
    return "other_insect" if label == "other_insect" or label.startswith("bycatch_") else "moth"


def synth(out: Path, n: int, ppm: float, tile: int, seed: int = 0) -> dict:
    """Paste AMI/iNat cutouts onto training tiles (or blank liners) and add them to the train split."""
    import random

    import numpy as np
    from PIL import ImageFilter

    from make_trap_style import LENGTH_MM, degrade, load_liners

    rng = random.Random(seed)
    with open(HERE / "data/cutouts/manifest.csv", newline="") as f:
        cut = [r for r in csv.DictReader(f) if r["status"] == "ok" and r["label"] in LENGTH_MM]
    by_cls: dict[str, list[dict]] = {}
    for r in cut:
        by_cls.setdefault(web_class(r["label"]), []).append(r)
    bases = sorted((out / "images/train").glob("*.jpg"))
    liners = load_liners(HERE / "data/liners")
    counts = {c: 0 for c in CLASSES}
    for k in range(n):
        if rng.random() < 0.8:
            base = rng.choice(bases)
            with Image.open(base) as im:
                bg = np.asarray(im.convert("RGB"), dtype=np.float32).copy()
            lines = (out / "labels/train" / f"{base.stem}.txt").read_text().splitlines()
        else:  # a blank webcam liner, at a random scale
            _, a = rng.choice(liners)
            s = rng.uniform(1.0, 2.0)
            im = Image.fromarray(a.astype(np.uint8))
            im = im.resize((round(im.width * s), round(im.height * s)), Image.BILINEAR)
            x, y = rng.randrange(0, max(1, im.width - tile)), rng.randrange(0, max(1, im.height - tile))
            bg = np.asarray(im.crop((x, y, x + tile, y + tile)).rotate(90 * rng.randrange(4)), dtype=np.float32).copy()
            bg = bg * rng.uniform(0.8, 1.2)
            lines = []
        h, w = bg.shape[:2]
        taken = [((float(c[1]) - float(c[3]) / 2) * w, (float(c[2]) - float(c[4]) / 2) * h,
                  (float(c[1]) + float(c[3]) / 2) * w, (float(c[2]) + float(c[4]) / 2) * h)
                 for c in (ln.split() for ln in lines)]
        light = np.median(bg.reshape(-1, 3), axis=0) / 255
        for _ in range(rng.randint(2, 12)):
            cls = "moth" if rng.random() < 0.6 else "other_insect"
            r = rng.choice(by_cls[cls])
            long_px = max(8, round(rng.uniform(*LENGTH_MM[r["label"]]) * ppm * rng.uniform(0.85, 1.15)))
            with Image.open(HERE / r["cutout"]) as c:
                c = c.convert("RGBA")
                bb = c.getchannel("A").point(lambda v: 255 if v > 64 else 0).getbbox()
                if not bb:
                    continue
                c = c.crop(bb)
                s = long_px / max(c.size)
                c = c.resize((max(1, round(c.width * s)), max(1, round(c.height * s))), Image.LANCZOS)
            if rng.random() < 0.5:
                c = c.transpose(Image.FLIP_LEFT_RIGHT)
            c = c.rotate(rng.uniform(0, 360), resample=Image.BICUBIC, expand=True)
            bb = c.getchannel("A").point(lambda v: 255 if v > 64 else 0).getbbox()
            if not bb or c.width >= w or c.height >= h:
                continue
            c = c.crop(bb)
            mw, mh = c.size
            for _try in range(20):
                x, y = rng.randrange(0, w - mw), rng.randrange(0, h - mh)
                if not any(x < t[2] and x + mw > t[0] and y < t[3] and y + mh > t[1] for t in taken):
                    break
            else:
                continue
            rgb = np.asarray(c.convert("RGB"), dtype=np.float32)
            alpha = np.asarray(c.getchannel("A").filter(ImageFilter.GaussianBlur(0.6)), dtype=np.float32)[..., None] / 255
            lit = rgb * light / max(light.max(), 1e-3) * rng.uniform(0.7, 1.15)
            sh = Image.fromarray((alpha[..., 0] * 255).astype(np.uint8)).filter(
                ImageFilter.GaussianBlur(max(1.0, long_px / 25)))
            shadow = np.asarray(sh, dtype=np.float32)[..., None] / 255 * rng.uniform(0.1, 0.3)
            region = bg[y:y + mh, x:x + mw] * (1 - shadow)
            bg[y:y + mh, x:x + mw] = region * (1 - alpha) + lit * alpha
            taken.append((x, y, x + mw, y + mh))
            lines.append(f"{CLASSES.index(cls)} {(x + mw / 2) / w:.6f} {(y + mh / 2) / h:.6f} {mw / w:.6f} {mh / h:.6f}")
            counts[cls] += 1
        img = degrade(rng, bg)
        name = f"synth_{k:05d}"
        img.save(out / "images/train" / f"{name}.jpg", quality=rng.randint(60, 92))
        (out / "labels/train" / f"{name}.txt").write_text("\n".join(lines))
    return {"tiles": n, "pasted": counts}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="yolo11s.pt", help="yolo11n/s/m.pt (COCO-pretrained, downloaded once)")
    ap.add_argument("--ppm", type=float, default=12, help="shrink photos to this px/mm (webcam ~7, Camera Module 3 ~15)")
    ap.add_argument("--tile", type=int, default=640)
    ap.add_argument("--overlap", type=int, default=160)
    ap.add_argument("--min-visible", type=float, default=0.4, help="keep a cut box if this much of it is in the tile")
    ap.add_argument("--val-photos", nargs="*", default=VAL_PHOTOS)
    ap.add_argument("--epochs", type=int, default=150)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--out", type=Path, default=HERE / "data/yolo")
    ap.add_argument("--name", default=None, help="run name under models/yolo11/ (default: model + ppm)")
    ap.add_argument("--synth", type=int, default=0, help="add this many tiles with AMI/iNat cutouts pasted on")
    ap.add_argument("--build-only", action="store_true")
    args = ap.parse_args(argv)

    info = build(args.out, args.ppm, args.tile, args.overlap, args.val_photos, args.min_visible)
    if args.synth:
        info["synth"] = synth(args.out, args.synth, args.ppm, args.tile)
    print(json.dumps(info, indent=1))
    if args.build_only:
        return 0

    from ultralytics import YOLO

    name = args.name or f"{Path(args.model).stem}-ppm{args.ppm:g}" + (f"-synth{args.synth}" if args.synth else "")
    model = YOLO(args.model)
    model.train(data=str(args.out / "data.yaml"), imgsz=args.tile, epochs=args.epochs, batch=args.batch,
                device=args.device, project=str(HERE / "models/yolo11"), name=name, exist_ok=True,
                patience=40, degrees=180, flipud=0.5, fliplr=0.5, mosaic=1.0, close_mosaic=15,
                scale=0.3, hsv_h=0.02, hsv_s=0.5, hsv_v=0.4, plots=True, seed=0)
    run = HERE / "models/yolo11" / name
    metrics = YOLO(run / "weights/best.pt").val(data=str(args.out / "data.yaml"), imgsz=args.tile,
                                                 device=args.device, project=str(run), name="val", exist_ok=True)
    summary = {**info, "model": args.model,
               "val": {"mAP50": metrics.box.map50, "mAP50-95": metrics.box.map, "precision": metrics.box.mp,
                       "recall": metrics.box.mr,
                       "per_class_mAP50": dict(zip([CLASSES[i] for i in metrics.box.ap_class_index],
                                                   map(float, metrics.box.ap50)))}}
    (run / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary["val"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
