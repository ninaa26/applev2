"""Model v2 detector: train YOLO11 on the liner photos whose boxes were all checked by hand.

    python train_yolo.py                          # build data/training/detector/yolo_real/, train yolo11s, report on test
    python train_yolo.py --model yolo11n.pt       # smaller, a candidate for the Pi
    python train_yolo.py --build-only             # just write the tiles and data.yaml
    python train_yolo.py --synth 3000 --out data/training/detector/yolo_synth   # also paste AMI/iNat insects on
    python train_yolo.py --blank 'data/real_liners/our_trap_bench_tests/capture_2026-10-06/calibrated_*.jpg' --blank-ppm 15.3
                                                  # also train on blank-liner photos from the trap camera

Only photos where every box was looked at go in. Since Nov 15 2026 most come from the team labelling site
(every gridded liner set: grape-moth, ofm-ervins, cm-ervins, the Cornell field cards and the web liners), read from
the newest export fetched with `label_site/deploy.sh <pi> --fetch` (data/review/labelling_site/from_pi/exports/), or
--site-export: a photo goes in when every box on it has a `by` (someone, or Claude, checked it) and nobody tagged it
unusable, wrong scale or not gridded. Photos the site leaves out (its gold photos, or one with a box nobody checked)
fall back to their older hand-labelled folders, if they have one: the Cornell field cards (crop_field_cards.py +
label_field_cards.py) and the ofm-ervins liners with no box still unlabelled. --no-site uses only those folders,
as before. Every species label counts as `moth`; `skip` rows (not an insect / off the card) are background.
Classes are pass-1 labels: moth, other_insect, debris.

Each photo is shrunk to --ppm px/mm (what the trap camera sees; from the printed grid, the `ppm` column) and cut
into overlapping --tile px tiles, so moths are the size they'll be in the trap. The overlap is at least the longest
single moth (18 mm), so every insect is whole in some tile; a tile that holds less than --min-visible of an insect
shows that part unlabelled, which is why the server merges tiles by overlap with the smaller box (merge_tiles in
server/sentinel_server/pipeline/detect.py). Three splits, by card/liner (a liner's other days go with it: liners.json):
  test   data/training/held_out/field_cards.txt plus --test-photos (default: web_liners_detector.txt in the same
         folder). Scored once, after training; the number to report.
  val    --val-frac of the remaining photos, the same ones every run. Training stops early on them and keeps the
         epoch that does best on them, so their score flatters the model and is not reported as accuracy.
  train  the rest.
--synth N adds N training tiles with web-photo insects pasted on (AMI and iNaturalist, cut out by segment_moths.py,
so their species label is right and their box exact): a random training tile, keeping its own boxes, or a blank liner
from the trap-style version's blank_liners/, gets 2-12 cutouts at their species' real length (make_trap_style.LENGTH_MM), any angle, tinted by
the liner's light, with a contact shadow, then blurred and noised. Moths become `moth`, bycatch `other_insect`.
--imgsz trains and runs the tiles enlarged (e.g. 800 for 640 px tiles), which gave modest gains for small insects
elsewhere. --one-insect-class folds moth and other_insect into `insect` (a generic insect detector found 80% of
species it had never seen; the classifier names them afterwards); debris stays its own class.
After training, the box-merging threshold (NMS IoU) and the confidence cut are chosen on the val photos, by best
F1, and saved in summary.json as `predict`; the server uses them. Settings from other traps don't carry over: on the
Oct 2 run, IoU 0.9 (tuned for dense whitefly cards in Yolo-pest) scored moth F1 0.74 on val against 0.84 at 0.5.
--blank adds photos of a liner with nothing on it as training tiles with no boxes (hard negatives): the grid, glare,
the trap's walls and clips, which is where a detector trained only on other people's cards makes things up.
Cutouts of held-out photos' groups don't matter here (val and test are our liners, not web photos), and val and
test tiles never get pasted on. Writes data/training/detector/yolo_real/ (tiles + data.yaml) and
models/detector/yolo/<run>/ (weights/best.pt, results, summary.json, trained_on.json).
"""

from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import shutil
import statistics
import sys
from pathlib import Path
from typing import NamedTuple

import paths
import trained_on
from PIL import Image, ImageOps

HERE = Path(__file__).parent
CLASSES = ["moth", "other_insect", "debris"]
# pass 2 of label_field_cards.py replaces `moth` with one of these; the detector still calls them moth
SPECIES = {"CM", "OFM", "OBLR", "lookalike_RBLR", "lookalike_LAW", "other_tortricid", "other_moth"}
DATA = HERE / paths.DATA
SOURCES = [DATA / paths.FIELD, DATA / paths.WEB_LINERS / "label/ofm-ervins"]
SPLITS = ["train", "val", "test"]
BAD_PHOTO_TAGS = {"unusable", "wrong_scale", "not_gridded"}  # labelling-site photo tags that keep a photo out
MERGE: dict[str, str] = {}  # --one-insect-class: {"moth": "insect", "other_insect": "insect"}
NMS_IOUS = (0.5, 0.7, 0.9)


def one_insect_class() -> None:
    global CLASSES
    CLASSES = ["insect", "debris"]
    MERGE.update(moth="insect", other_insect="insect")


class Source(NamedTuple):
    """One set of liner photos whose boxes were all checked."""
    name: str                       # tile names start with it
    inbox: Path                     # where the photos are
    labelled: dict[str, list[dict]]  # photo -> its box rows (x1..y2, label, ppm)
    groups: list[set[str]]          # photos of one liner on several days
    listed_as: dict[str, str]       # photo -> the name the held-out lists use for it


def labelled_photos(data: Path) -> dict[str, list[dict]]:
    """Photo -> its rows, for photos with no box left unlabelled."""
    rows: dict[str, list[dict]] = {}
    with open(data / "labels.csv", newline="") as f:
        for r in csv.DictReader(f):
            rows.setdefault(r["photo"], []).append(r)
    return {p: rs for p, rs in rows.items() if all(r["label"] for r in rs)}


def liner_groups(data: Path) -> list[set[str]]:
    """Photos of the same liner on different days; they always stay on the same side of a split."""
    liners = data / "liners.json"
    return [set(g) for g in json.loads(liners.read_text())] if liners.exists() else []


def folder_source(data: Path, skip: set[str] = frozenset()) -> Source:
    """A label_field_cards.py folder: labels.csv, inbox/, liners.json. Photos in `skip` are left out."""
    labelled = {p: rs for p, rs in labelled_photos(data).items() if p not in skip}
    return Source(data.name, data / "inbox", labelled, liner_groups(data), {p: p for p in labelled})


def latest_site_export(data: Path = DATA) -> Path | None:
    """labels.csv of the newest labelling-site export fetched with `label_site/deploy.sh <pi> --fetch`."""
    found = sorted((data / paths.LABEL_SITE_EXPORTS).glob("*/labels.csv"))
    return found[-1] if found else None


def site_source(export: Path, data: Path = DATA) -> tuple[Source, dict]:
    """The team labelling site's photos (every gridded liner set), from a fetched export.

    A photo goes in only if every box on it was checked on the site (`by` filled in): the gold photos and the
    few with a box nobody looked at are left out. So are photos someone tagged unusable, wrong scale or not
    gridded. The site names a photo `<set>__<file>`; the held-out lists and liners.json use `<file>`."""
    rows = _site_rows(export)
    tagged = set()
    if (export.parent / "photo_tags.csv").exists():
        with open(export.parent / "photo_tags.csv", newline="") as f:
            tagged = {r["photo"] for r in csv.DictReader(f) if r["tag"] in BAD_PHOTO_TAGS}
    unchecked = {p for p, rs in rows.items() if not all(r["by"] and r["label"] for r in rs)}
    labelled = {p: rs for p, rs in rows.items() if p not in unchecked and p not in tagged}
    listed_as = {p: rs[0]["photo"] for p, rs in labelled.items()}
    groups = []
    for set_dir in sorted((data / paths.WEB_LINERS / "label").glob("*/liners.json")):
        prefix = f"{set_dir.parent.name}__"
        groups += [{prefix + p for p in g} for g in json.loads(set_dir.read_text())]
    site = data / paths.LABEL_SITE
    left_out = {"unchecked boxes": len(unchecked), "tagged": len(tagged - unchecked)}
    return Source("site", site / "inbox", labelled, groups, listed_as), left_out


def default_sources(export: Path | None = None, data: Path = DATA) -> tuple[list[Source], dict]:
    """The labelling site's fetched export when there is one, plus the photos of the old hand-labelled folders
    (field cards, ofm-ervins) that the site didn't supply; without an export, just those folders."""
    export = export or latest_site_export(data)
    if export is None:
        return [folder_source(d) for d in SOURCES], {"site_export": None}
    site, left_out = site_source(export, data)
    # A photo the site left out (gold, or a box nobody checked) keeps its older hand-checked labels, if it has any.
    rest = [folder_source(d, skip={site.listed_as[p] for p in site.labelled}) for d in SOURCES]
    info = {"site_export": str(export.relative_to(data.parent)) if export.is_relative_to(data.parent) else str(export),
            "site_photos": len(site.labelled), "site_left_out": left_out,
            "other_photos": {s.name: len(s.labelled) for s in rest}}
    return [site, *rest], info


def _site_rows(export: Path) -> dict[str, list[dict]]:
    rows: dict[str, list[dict]] = {}
    with open(export, newline="") as f:
        for r in csv.DictReader(f):
            rows.setdefault(r["site_photo"], []).append(r)
    return rows


def held_out(src: Source, test_photos: list[str]) -> set[str]:
    """Photos of `src` named (or name-prefixed) in `test_photos`, with their liner's other days."""
    out = {p for p in src.labelled if paths.is_listed(src.listed_as[p], test_photos)}
    for group in src.groups:
        if out & group:
            out |= group
    return out


def pick_val(groups: list[set[str]], photos: list[str], frac: float) -> set[str]:
    """About `frac` of `photos` (the ones not in test) for choosing the checkpoint: whole liners, and the same
    ones on every run, ordered by a hash of the name so adding a photo doesn't reshuffle the rest."""
    if frac <= 0 or len(photos) < 2:
        return set()
    left = set(photos)
    order = []
    for g in groups:
        if g & left:
            order.append(sorted(g & left))
            left -= g
    order += [[p] for p in left]
    order.sort(key=lambda g: hashlib.sha1(g[0].encode(), usedforsecurity=False).hexdigest())
    val: set[str] = set()
    for g in order[:-1]:  # always leave something to train on
        if len(val) >= frac * len(photos):
            break
        val |= set(g)
    return val


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


def build(out: Path, ppm: float, tile: int, overlap: int, test_photos: list[str], min_visible: float,
          val_frac: float = 0.15, sources: list[Source | Path] | None = None) -> dict:
    if out.exists():
        shutil.rmtree(out)
    stats = {s: {"photos": 0, "tiles": 0, "boxes": 0} for s in SPLITS}
    per_class = {s: {c: 0 for c in CLASSES} for s in stats}
    for d in ("images", "labels"):
        for s in SPLITS:
            (out / d / s).mkdir(parents=True, exist_ok=True)
    for src in sources if sources is not None else default_sources()[0]:
        src = folder_source(src) if isinstance(src, Path) else src
        test = held_out(src, test_photos)
        val = pick_val(src.groups, sorted(p for p in src.labelled if p not in test), val_frac)
        for photo, rows in sorted(src.labelled.items()):
            split = "test" if photo in test else "val" if photo in val else "train"
            pass1 = ((r, "moth" if r["label"] in SPECIES else r["label"]) for r in rows)
            boxes = [{**r, "label": c} for r, c0 in pass1 if (c := MERGE.get(c0, c0)) in CLASSES]
            ppms = [float(r["ppm"]) for r in rows if r.get("ppm")]
            scale = min(1.0, ppm / statistics.median(ppms)) if ppms else 1.0
            with Image.open(src.inbox / photo) as im:
                img = ImageOps.exif_transpose(im).convert("RGB")
            if scale < 1:
                img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
            stem = f"{src.name}__{Path(photo).stem}"
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
        f"path: {out.resolve()}\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n"
        + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES)))
    return {"splits": stats, "boxes_per_class": per_class, "ppm": ppm, "tile": tile, "overlap": overlap}


def default_overlap(ppm: float, longest_mm: float = 18.0) -> int:
    """Tile overlap in px that fits the longest single moth, rounded up to a multiple of 32."""
    return max(160, -(-int(longest_mm * ppm + 0.999) // 32) * 32)


def add_blanks(out: Path, patterns: list[str], blank_ppm: float, ppm: float, tile: int, overlap: int) -> dict:
    """Blank-liner photos (taken at `blank_ppm` px/mm) as training tiles with empty label files."""
    n_photos = n_tiles = 0
    for pattern in patterns:
        for path in sorted(map(Path, glob.glob(pattern))):
            with Image.open(path) as im:
                img = ImageOps.exif_transpose(im).convert("RGB")
            scale = min(1.0, ppm / blank_ppm)
            if scale < 1:
                img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
            n_photos += 1
            for tx, ty in tiles(img.width, img.height, tile, overlap):
                name = f"blank__{path.parent.name}__{path.stem}_{tx}_{ty}"
                img.crop((tx, ty, tx + min(tile, img.width), ty + min(tile, img.height))).save(
                    out / "images/train" / f"{name}.jpg", quality=95)
                (out / "labels/train" / f"{name}.txt").write_text("")
                n_tiles += 1
    return {"photos": n_photos, "tiles": n_tiles}


def best_conf(box) -> tuple[float, float]:
    """(confidence, F1) where F1 averaged over classes peaks, from an ultralytics val result's curves."""
    f1 = [sum(col) / len(col) for col in zip(*[list(c) for c in box.f1_curve])]
    k = max(range(len(f1)), key=f1.__getitem__)
    return round(float(box.px[k]), 3), round(float(f1[k]), 4)


def at_conf(box, conf: float) -> dict:
    """Precision, recall and F1 per class at one confidence cut: what the server will actually do."""
    k = min(range(len(box.px)), key=lambda i: abs(float(box.px[i]) - conf))
    return {CLASSES[c]: {"precision": round(float(box.p_curve[i][k]), 3), "recall": round(float(box.r_curve[i][k]), 3),
                         "f1": round(float(box.f1_curve[i][k]), 3)} for i, c in enumerate(box.ap_class_index)}


def web_class(label: str) -> str:
    return "other_insect" if label == "other_insect" or label.startswith("bycatch_") else "moth"


def synth(out: Path, n: int, ppm: float, tile: int, seed: int = 0) -> dict:
    """Paste AMI/iNat cutouts onto training tiles (or blank liners) and add them to the train split."""
    import random

    import numpy as np
    from make_trap_style import LENGTH_MM, degrade, load_liners
    from PIL import ImageFilter

    rng = random.Random(seed)
    with open(DATA / paths.CUTOUTS / "manifest.csv", newline="") as f:
        cut = [r for r in csv.DictReader(f) if r["status"] == "ok" and r["label"] in LENGTH_MM]
    by_cls: dict[str, list[dict]] = {}
    for r in cut:
        by_cls.setdefault(web_class(r["label"]), []).append(r)
    bases = sorted((out / "images/train").glob("*.jpg"))
    liners = load_liners(paths.trap_style(DATA) / "blank_liners")
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
            cls = MERGE.get(cls, cls)
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
    ap.add_argument("--model", default=str(HERE / paths.YOLO_START),
                    help="yolo11n/s/m.pt (COCO-pretrained, downloaded once into models/detector/pretrained/)")
    ap.add_argument("--ppm", type=float, default=12, help="shrink photos to this px/mm (webcam ~7, Camera Module 3 ~15)")
    ap.add_argument("--tile", type=int, default=640)
    ap.add_argument("--imgsz", type=int, default=None, help="network input size; default: --tile (800 enlarges 640 px tiles)")
    ap.add_argument("--one-insect-class", action="store_true", help="classes insect + debris instead of moth, other_insect, debris")
    ap.add_argument("--overlap", type=int, default=None, help="default: the longest single moth at --ppm (224 at 12 px/mm)")
    ap.add_argument("--blank", nargs="*", default=[], help="glob(s) of blank-liner photos to add as tiles with no boxes")
    ap.add_argument("--blank-ppm", type=float, default=15.3, help="px/mm of the --blank photos (IMX219 in the trap: 15.3)")
    ap.add_argument("--min-visible", type=float, default=0.4, help="keep a cut box if this much of it is in the tile")
    ap.add_argument("--test-photos", nargs="*", default=paths.held_out_list(DATA, paths.WEB_LINER_TEST_DETECTOR),
                    help="name prefixes of photos kept for the final score, on top of held_out/field_cards.txt "
                         "(default: held_out/web_liners_detector.txt)")
    ap.add_argument("--val-frac", type=float, default=0.15,
                    help="share of the other photos used to stop training and pick the best epoch")
    ap.add_argument("--epochs", type=int, default=150)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--out", type=Path, default=DATA / paths.DETECTOR / "yolo_real")
    ap.add_argument("--name", default=None, help="run name under models/detector/yolo/ (default: model + ppm)")
    ap.add_argument("--synth", type=int, default=0, help="add this many tiles with AMI/iNat cutouts pasted on")
    ap.add_argument("--site-export", type=Path, default=None,
                    help="labels.csv of a labelling-site export (default: the newest under "
                         f"data/{paths.LABEL_SITE_EXPORTS}/)")
    ap.add_argument("--no-site", action="store_true", help="only the old folders (field cards, ofm-ervins)")
    ap.add_argument("--build-only", action="store_true")
    args = ap.parse_args(argv)

    if args.overlap is None:
        args.overlap = default_overlap(args.ppm)
    if args.one_insect_class:
        one_insect_class()
    imgsz = args.imgsz or args.tile
    test_photos = paths.held_out_list(DATA, paths.FIELD_TEST) + args.test_photos
    if args.no_site:
        sources, src_info = [folder_source(d) for d in SOURCES], {"site_export": None}
    else:
        sources, src_info = default_sources(args.site_export)
    info = {**src_info, **build(args.out, args.ppm, args.tile, args.overlap, test_photos, args.min_visible,
                                args.val_frac, sources)}
    if args.blank:
        info["blank"] = add_blanks(args.out, args.blank, args.blank_ppm, args.ppm, args.tile, args.overlap)
    if args.synth:
        info["synth"] = synth(args.out, args.synth, args.ppm, args.tile)
    print(json.dumps(info, indent=1))
    if args.build_only:
        return 0

    from ultralytics import YOLO

    name = args.name or f"{Path(args.model).stem}-ppm{args.ppm:g}" + (f"-synth{args.synth}" if args.synth else "")
    model = YOLO(args.model)
    model.train(data=str(args.out / "data.yaml"), imgsz=imgsz, epochs=args.epochs, batch=args.batch,
                device=args.device, project=str(HERE / paths.YOLO_RUNS), name=name, exist_ok=True,
                patience=40, degrees=180, flipud=0.5, fliplr=0.5, mosaic=1.0, close_mosaic=15,
                scale=0.3, hsv_h=0.02, hsv_s=0.5, hsv_v=0.4, plots=True, seed=0)
    run = HERE / paths.YOLO_RUNS / name

    def val(split: str, iou: float, name: str):
        return YOLO(run / "weights/best.pt").val(data=str(args.out / "data.yaml"), split=split, imgsz=imgsz,
                                                 device=args.device, project=str(run), name=name, exist_ok=True,
                                                 iou=iou, max_det=1000)  # a full liner tile can pass the default cap of 300

    # Box merging (NMS IoU) and the confidence cut, chosen on val: the pair with the best F1 averaged over classes.
    predict = {"f1": -1.0}
    for iou in NMS_IOUS:
        conf, f1 = best_conf(val("val", iou, f"val-iou{iou:g}").box)
        if f1 > predict["f1"]:
            predict = {"iou": iou, "conf": conf, "f1": f1}

    def score(split: str) -> dict:
        m = val(split, predict["iou"], split)
        return {"mAP50": m.box.map50, "mAP50-95": m.box.map, "precision": m.box.mp, "recall": m.box.mr,
                "per_class_mAP50": dict(zip([CLASSES[i] for i in m.box.ap_class_index], map(float, m.box.ap50))),
                "at_predict_conf": at_conf(m.box, predict["conf"])}

    # "val" picked the checkpoint and the predict settings, so it flatters the model; "test" was never looked at.
    summary = {**info, "model": args.model, "imgsz": imgsz, "classes": CLASSES, "predict": predict,
               "val": score("val"), "test": score("test")}
    (run / "summary.json").write_text(json.dumps(summary, indent=1))
    trained_on.write(run, trained_on.summary(DATA, Path(args.model).name, test_photos=test_photos,
                                             sources=[str(s.inbox.parent.relative_to(HERE)) for s in sources],
                                             site_export=src_info["site_export"],
                                             blank=args.blank, synth_tiles=args.synth))
    print(json.dumps({"test": summary["test"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
