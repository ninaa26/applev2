"""Make "trap-style" training photos: web-photo moths pasted onto real liner photos, at trap resolution.

    python make_trap_style.py                       # after segment_moths.py; writes data/synth/
    python make_trap_style.py --preview 24          # contact sheet only: data/synth/preview.jpg

Why: the web photos are sharp, well lit and full size. In the trap a codling moth is ~70 px long
(webcam, ~7 px/mm), lit orange through the trap roof, slightly blurred and JPEG'd, on a gridded
liner. A model that has only seen web photos has never seen that. This script closes some of that
gap; it doesn't replace photos of real moths on real liners (see ml/README.md).

For each flatbug cutout (data/cutouts/, from segment_moths.py):
  1. scale it so the moth is its species' real length (LENGTH_MM) at a random px/mm (PPM),
     so a CM is ~50-160 px long and an OFM a bit over half that;
  2. rotate it to any angle (moths land on the glue at any angle) and maybe mirror it;
  3. tint it by the liner's own light (the median colour of the patch it lands on), with a small
     contact shadow, and paste it onto a random spot of a random liner photo (data/liners/*.jpg);
  4. crop a square around it the way the server does (classify.crop, pad 0.35) with a bit of
     box jitter, as the detector's boxes aren't exact;
  5. blur, add sensor noise and re-save as a low-quality JPEG.
Plus `debris` crops of bare liner (grid lines, crossings, glare, shadows) at random sizes.

Each synthetic photo inherits its source photo's group (so its split), which keeps a moth and its
pasted copies on the same side of the train/test line. Rare labels get more copies per cutout
(--per-label), capped at --max-copies. data/synth/manifest.csv lists everything.
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

# Resting length in mm (head to wing tips), from the NEWA / UC IPM / TortAI descriptions.
LENGTH_MM = {
    "CM": (9.0, 11.0),
    "OFM": (6.0, 7.5),
    "OBLR": (10.0, 14.0),
    "lookalike_LAW": (5.0, 6.5),
    "lookalike_RBLR": (7.0, 9.5),
    "other_tortricid": (6.0, 13.0),
    "other_moth": (6.0, 20.0),
    "other_insect": (3.0, 15.0),
}
PPM = (5.0, 16.0)  # px/mm: ~7 on the current webcam, ~15 expected with the Camera Module 3
PAD = 0.35  # server crop padding (server/sentinel_server/pipeline/classify.py: crop)
FIELDS = ["path", "label", "source_path", "liner", "ppm", "length_mm"]


def load_liners(folder: Path) -> list[np.ndarray]:
    liners = []
    for p in sorted(folder.glob("*.jpg")) + sorted(folder.glob("*.png")):
        with Image.open(p) as im:
            liners.append((p.name, np.asarray(im.convert("RGB"), dtype=np.float32)))
    if not liners:
        raise SystemExit(f"no liner photos in {folder}: add a few photos of a blank liner taken by the trap")
    return liners


def liner_patch(rng: random.Random, liners, side: int) -> tuple[str, np.ndarray]:
    """A side x side patch of a random liner, randomly rescaled, rotated by 90s and flipped."""
    name, a = rng.choice(liners)
    scale = rng.uniform(0.8, 1.3)
    h, w = a.shape[:2]
    need = int(np.ceil(side / scale)) + 2
    if need > min(h, w):  # huge moth at high px/mm: stretch the whole liner
        scale = side / (min(h, w) - 2)
        need = min(h, w) - 2
    y, x = rng.randrange(0, h - need + 1), rng.randrange(0, w - need + 1)
    patch = Image.fromarray(a[y:y + need, x:x + need].astype(np.uint8)).resize((side, side), Image.BILINEAR)
    patch = patch.rotate(90 * rng.randrange(4))
    if rng.random() < 0.5:
        patch = patch.transpose(Image.FLIP_LEFT_RIGHT)
    gain = rng.uniform(0.8, 1.2)  # exposure differs between photos and through the day
    return name, np.clip(np.asarray(patch, dtype=np.float32) * gain, 0, 255)


def degrade(rng: random.Random, a: np.ndarray) -> Image.Image:
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    sigma = rng.uniform(0.0, 1.2)
    if sigma > 0.2:
        im = im.filter(ImageFilter.GaussianBlur(sigma))
    a = np.asarray(im, dtype=np.float32)
    a = a + np.random.default_rng(rng.randrange(1 << 30)).normal(0, rng.uniform(1.5, 7.0), a.shape)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def paste_moth(rng: random.Random, cutout: Image.Image, label: str, liners) -> tuple[Image.Image, dict]:
    ppm = rng.uniform(*PPM)
    length_mm = rng.uniform(*LENGTH_MM[label])
    long_px = max(8, int(round(length_mm * ppm)))
    s = long_px / max(cutout.size)
    moth = cutout.resize((max(1, round(cutout.width * s)), max(1, round(cutout.height * s))), Image.LANCZOS)
    if rng.random() < 0.5:
        moth = moth.transpose(Image.FLIP_LEFT_RIGHT)
    moth = moth.rotate(rng.uniform(0, 360), resample=Image.BICUBIC, expand=True)
    mw, mh = moth.size
    # The detector's box is the moth's box; the crop is the server's padded square, with jitter
    # for sloppy boxes. The canvas is bigger so the jittered crop never runs off the edge.
    side = int(max(mw, mh) * (1 + 2 * PAD) * rng.uniform(0.85, 1.2))
    canvas = int(side * 1.5) + 4
    name, bg = liner_patch(rng, liners, canvas)
    ox, oy = (canvas - mw) // 2, (canvas - mh) // 2

    rgb = np.asarray(moth.convert("RGB"), dtype=np.float32)
    alpha = np.asarray(moth.getchannel("A").filter(ImageFilter.GaussianBlur(0.6)), dtype=np.float32)[..., None] / 255
    region = bg[oy:oy + mh, ox:ox + mw]
    light = np.median(bg.reshape(-1, 3), axis=0) / 255  # the liner is white, so its colour is the light's
    moth_lit = rgb * light / max(light.max(), 1e-3) * rng.uniform(0.7, 1.15)
    # contact shadow: the moth's silhouette, blurred and nudged, darkens the glue under it
    sh = Image.fromarray((alpha[..., 0] * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(max(1.0, long_px / 25)))
    shadow = np.asarray(sh, dtype=np.float32)[..., None] / 255 * rng.uniform(0.1, 0.3)
    region = region * (1 - shadow)
    bg[oy:oy + mh, ox:ox + mw] = region * (1 - alpha) + moth_lit * alpha

    jx, jy = (rng.uniform(-0.08, 0.08) * side for _ in range(2))
    cx, cy = canvas / 2 + jx, canvas / 2 + jy
    x0, y0 = int(cx - side / 2), int(cy - side / 2)
    out = degrade(rng, bg[y0:y0 + side, x0:x0 + side])
    return out, {"liner": name, "ppm": f"{ppm:.1f}", "length_mm": f"{length_mm:.1f}"}


def debris_crop(rng: random.Random, liners) -> tuple[Image.Image, dict]:
    """Bare liner: what a false detection on grid, glare or a shadow looks like to the classifier."""
    ppm = rng.uniform(*PPM)
    side = int(rng.uniform(3, 14) * ppm * (1 + 2 * PAD))
    name, bg = liner_patch(rng, liners, side)
    return degrade(rng, bg), {"liner": name, "ppm": f"{ppm:.1f}", "length_mm": ""}


def sheet(paths: list[Path], dest: Path, cell: int = 128) -> None:
    cols = 8
    out = Image.new("RGB", (cell * cols, cell * ((len(paths) + cols - 1) // cols)), "white")
    for k, p in enumerate(paths):
        with Image.open(p) as im:
            out.paste(im.convert("RGB").resize((cell, cell), Image.NEAREST), ((k % cols) * cell, (k // cols) * cell))
    out.save(dest, quality=90)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--per-label", type=int, default=2500, help="target photos per fine label")
    ap.add_argument("--max-copies", type=int, default=12, help="most copies of any one cutout")
    ap.add_argument("--debris", type=int, default=2000, help="bare-liner debris crops")
    ap.add_argument("--preview", type=int, default=0, help="only write a contact sheet of this many")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)
    rng = random.Random(args.seed)

    liners = load_liners(args.data / "liners")
    with open(args.data / "cutouts" / "manifest.csv", newline="") as f:
        cut = [r for r in csv.DictReader(f) if r["status"] == "ok" and r["label"] in LENGTH_MM]
    by_label = defaultdict(list)
    for r in cut:
        by_label[r["label"]].append(r)
    print(f"{len(cut)} cutouts, {len(liners)} liner photos")

    out = args.data / "synth"
    if args.preview:
        jobs = [(rng.choice(cut), 0) for _ in range(args.preview)]
        out = out / "preview"
    else:
        jobs = []
        for label, rows in sorted(by_label.items()):
            copies = min(args.max_copies, max(1, round(args.per_label / len(rows))))
            jobs += [(r, k) for r in rows for k in range(copies)]
            print(f"  {label:16} {len(rows):5} cutouts x {copies:2} = {len(rows) * copies}")
    out.mkdir(parents=True, exist_ok=True)

    manifest, written = [], []
    for n, (r, k) in enumerate(jobs, 1):
        with Image.open(r["cutout"]) as c:
            img, meta = paste_moth(rng, c.convert("RGBA"), r["label"], liners)
        dest = out / r["label"] / f"{Path(r['cutout']).stem}_{k}.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, quality=rng.randint(55, 90))
        manifest.append({"path": str(dest), "label": r["label"], "source_path": r["path"], **meta})
        written.append(dest)
        if n % 2000 == 0:
            print(f"  {n}/{len(jobs)}", flush=True)
    n_debris = 16 if args.preview else args.debris
    for k in range(n_debris):
        img, meta = debris_crop(rng, liners)
        dest = out / "debris" / f"liner_{k:05d}.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, quality=rng.randint(55, 90))
        manifest.append({"path": str(dest), "label": "debris", "source_path": "", **meta})
        written.append(dest)

    if args.preview:
        sheet(written, args.data / "synth" / "preview.jpg")
        print(f"Wrote {args.data / 'synth' / 'preview.jpg'}")
        return 0
    with open(out / "manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(manifest)
    print(f"Wrote {len(manifest)} trap-style photos to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
