"""Crop every insect out of photos of real field cards, for labelling.

    python crop_field_cards.py                      # data/field/inbox/*.jpg -> data/field/; only new photos
    python crop_field_cards.py --grid-mm 25         # the card's printed grid spacing (default 25)
    python crop_field_cards.py --cutouts            # after labelling: outline the boxes that have none

The photos are phone shots of used liners (e.g. Trécé Pherocon VI delta cards), not trap-camera
photos, so they are kept apart from data/own/. What they add is real moths on real glue: worn,
flattened, tilted, touching. For each photo:
  1. flatbug finds every insect (it tiles the full-size photo itself);
  2. the server's grid finder (pipeline/detect.find_grid) measures px/mm from the printed grid in
     patches of several sizes around each insect, not the whole photo, because a card shot at an
     angle has smaller squares at the far end. The value most patches agree on is the photo's
     scale; each insect keeps its own estimate nearest that. That gives each insect's real length
     (blank when the photo shows no grid);
  3. each insect is saved as a server-style crop (pad 0.35, data/field/crops/) and as an RGBA
     cutout (data/field/cutouts/) that make_trap_style.py can paste onto our own liner;
  4. data/field/boxes/<photo>.jpg shows the photo with every insect numbered.

Label them with label_field_cards.py (or fill in the `label` column of data/field/labels.csv).
Re-runs only add new photos and never touch existing labels.

`--cutouts`, after labelling: boxes drawn by hand or resized have no flatbug outline, so flatbug is
run again on just that box's neighbourhood (enlarged when small) and the outline that best fills
the box becomes its cutout. Where flatbug sees nothing (debris isn't an arthropod; small or pale
insects), the object is separated from the white card by colour instead (contrast_mask). Stop
label_field_cards.py first: it holds labels.csv in memory.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from sentinel_server.pipeline.detect import find_grid, line_opening  # noqa: E402

PAD = 0.35  # server crop padding (server/sentinel_server/pipeline/classify.py: crop)
FIELDS = ["photo", "n", "label", "source", "crop", "cutout", "x1", "y1", "x2", "y2", "conf", "ppm", "length_mm"]


def server_crop(img: Image.Image, box) -> Image.Image:
    x1, y1, x2, y2 = box
    side = max(x2 - x1, y2 - y1) * (1 + 2 * PAD)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    return img.crop((int(cx - side / 2), int(cy - side / 2), int(cx + side / 2), int(cy + side / 2)))


PATCH_SIDES = (600, 1000, 1500, 2200, 0)  # px, 0 = whole photo; the right one depends on how close the photo was taken


def local_grid_estimates(bgr: np.ndarray, box, grid_mm: float) -> list[tuple[float, float]]:
    """(px/mm, score) from the grid in square patches of several sizes centred on the insect.

    A grid square (25 mm) is longer than any insect we count (a CM is ~10 mm), so a spacing shorter
    than the insect's box is glue texture or scales, not the grid, and is dropped."""
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    h, w = bgr.shape[:2]
    out = []
    for side in PATCH_SIDES:
        side = side or max(h, w) * 2
        patch = bgr[max(0, int(cy - side / 2)):min(h, int(cy + side / 2)), max(0, int(cx - side / 2)):min(w, int(cx + side / 2))]
        g = find_grid(patch)
        if g.pitch_px > max(x2 - x1, y2 - y1):
            out.append((g.pitch_px / grid_mm, g.score))
    return out


def photo_px_per_mm(estimates: list[float], tol: float = 0.12) -> float | None:
    """The px/mm most local estimates agree on. Wrong ones are mostly 2-5x too big (the finder
    locked onto every 2nd-5th line or the card's fold) and scatter, so the true one is the mode."""
    if not estimates:
        return None
    a = np.array(estimates)
    support = [(np.abs(np.log(a / v)) < tol).sum() for v in a]
    best = a[int(np.argmax(support))]
    return float(np.median(a[np.abs(np.log(a / best)) < tol]))


def pick_px_per_mm(local: list[tuple[float, float]], photo: float | None, tol: float = 0.35) -> float | None:
    """The insect's own estimate nearest the photo's (within ±35%: a tilted card's squares shrink
    with distance), else the photo's."""
    if photo is None:
        return None
    near = [(abs(np.log(v / photo)), v) for v, _ in local if abs(np.log(v / photo)) < np.log(1 + tol)]
    return min(near)[1] if near else photo


def detect(predictor, img: Image.Image, path: Path, min_conf: float) -> list[tuple[float, np.ndarray]]:
    """(confidence, contour as N×2 x,y pixels) for every insect, largest first."""
    import torch

    t = torch.from_numpy(np.asarray(img).copy()).permute(2, 0, 1)
    pred = predictor(t, path=str(path))
    found = []
    for conf, contour in zip(pred.confs.cpu().tolist(), pred.contours):
        c = contour.cpu().numpy().astype(np.float32)
        if conf >= min_conf and len(c) >= 3:
            found.append((conf, c))
    return sorted(found, key=lambda f: -cv2.contourArea(f[1]))


def cutout(img: Image.Image, contour: np.ndarray, box) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).polygon([(float(x), float(y)) for x, y in contour], fill=255)
    rgba = img.copy()
    rgba.putalpha(mask)
    return rgba.crop(box)


def contrast_mask(img: Image.Image, box, drop_lines: bool = True) -> np.ndarray | None:
    """Outline of whatever sits in the box on a pale card: pixels unlike the box's border colour,
    the blob nearest the centre. Box-sized bool mask, or None when nothing stands out.

    drop_lines removes the printed grid (thin straight runs across most of the box) first; a twig
    is also thin and straight, so callers fall back to drop_lines=False when nothing is left."""
    x1, y1, x2, y2 = box
    a = np.asarray(img.crop(box), dtype=np.float32)
    h, w = a.shape[:2]
    if h < 4 or w < 4:
        return None
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    diff = np.linalg.norm(a - np.median(border, axis=0), axis=2)
    diff = cv2.GaussianBlur(diff, (0, 0), max(1.0, min(h, w) / 100))
    t, _ = cv2.threshold(np.clip(diff, 0, 255).astype(np.uint8), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if t < 20:  # nothing clearly unlike the card
        return None
    m = (diff > t).astype(np.uint8)
    if drop_lines:  # an insect on a line is thicker than the line, so it stays
        run, thick = int(0.7 * max(h, w)), max(4, min(h, w) // 4)
        lines = np.zeros_like(m)
        for angle in np.arange(0, 180, 7.5):
            lines = np.maximum(lines, line_opening(m * 255, float(angle), run, thick))
        m[lines > 127] = 0
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    m = cv2.morphologyEx(cv2.morphologyEx(m, cv2.MORPH_CLOSE, k), cv2.MORPH_OPEN, k)
    n, lab, stats, cent = cv2.connectedComponentsWithStats(m)
    if n < 2:
        return None
    # biggest blobs near the centre win: area divided by distance from the centre
    score = [stats[i, cv2.CC_STAT_AREA] / (1 + np.hypot(*(cent[i] - (w / 2, h / 2)))) for i in range(1, n)]
    keep = lab == 1 + int(np.argmax(score))
    keep = cv2.morphologyEx(keep.astype(np.uint8), cv2.MORPH_CLOSE, k).astype(bool)
    frac = keep.mean()
    return keep if 0.03 < frac < 0.9 else None


def fill_cutouts(predictor, data: Path, rows: list[dict]) -> int:
    """Give every kept box without a cutout one: flatbug on the box's neighbourhood, best-matching outline."""
    import torch

    todo = [r for r in rows if r["label"] not in ("", "skip") and not r["cutout"]]
    print(f"{len(todo)} labelled boxes without a cutout")
    done = 0
    images: dict[str, Image.Image] = {}
    for r in todo:
        if r["photo"] not in images:
            with Image.open(data / "inbox" / r["photo"]) as im:
                images = {r["photo"]: ImageOps.exif_transpose(im).convert("RGB")}  # one photo in memory
        img = images[r["photo"]]
        x1, y1, x2, y2 = (int(r[k]) for k in ("x1", "y1", "x2", "y2"))
        m = max(x2 - x1, y2 - y1) // 2
        rx, ry = max(0, x1 - m), max(0, y1 - m)
        region = img.crop((rx, ry, min(img.width, x2 + m), min(img.height, y2 + m)))
        up = max(1.0, 640 / max(region.size))  # flatbug skips things under ~32 px
        if up > 1:
            region = region.resize((round(region.width * up), round(region.height * up)), Image.LANCZOS)
        t = torch.from_numpy(np.asarray(region).copy()).permute(2, 0, 1)
        pred = predictor(t, path=r["crop"], single_scale=True)
        best, best_iou = None, 0.25  # an outline must cover a fair part of the box to count
        for c in pred.contours:
            c = c.cpu().numpy().astype(np.float32) / up + (rx, ry)
            if len(c) < 3:
                continue
            bx1, by1 = c.min(axis=0)
            bx2, by2 = c.max(axis=0)
            inter = max(0, min(x2, bx2) - max(x1, bx1)) * max(0, min(y2, by2) - max(y1, by1))
            iou = inter / ((x2 - x1) * (y2 - y1) + (bx2 - bx1) * (by2 - by1) - inter)
            if iou > best_iou:
                best, best_iou = c, iou
        dest = data / "cutouts" / f"{Path(r['photo']).stem}_{r['n']}{'m' if r['source'] == 'manual' else 'e'}.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if best is not None:
            box = tuple(int(v) for v in (*best.min(axis=0), *(best.max(axis=0) + 1)))
            cutout(img, best, box).save(dest)
        else:
            m = contrast_mask(img, (x1, y1, x2, y2))
            if m is None:
                m = contrast_mask(img, (x1, y1, x2, y2), drop_lines=False)
            if m is None:
                print(f"  {r['photo']} #{r['n']} ({r['label']}): nothing stands out from the card, no cutout")
                continue
            ys, xs = np.nonzero(m)
            rgba = img.crop((x1, y1, x2, y2))
            rgba.putalpha(Image.fromarray(m.astype(np.uint8) * 255))
            rgba.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)).save(dest)
        r["cutout"] = str(dest)
        done += 1
    return done


def draw_boxes(img: Image.Image, rows: list[dict], dest: Path) -> None:
    im = img.copy()
    d = ImageDraw.Draw(im)
    size = max(18, img.width // 60)
    try:
        font = ImageFont.truetype("Helvetica.ttc", size)
    except OSError:
        font = ImageFont.load_default()
    for r in rows:
        box = [int(r[k]) for k in ("x1", "y1", "x2", "y2")]
        d.rectangle(box, outline=(255, 0, 255), width=max(2, size // 8))
        d.text((box[0], box[1] - size - 2), r["n"], fill=(255, 0, 255), font=font, stroke_width=2, stroke_fill="white")
    im.save(dest, quality=85)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data/field"))
    ap.add_argument("--weights", default="flat_bug_M.pt")
    ap.add_argument("--grid-mm", type=float, default=25.0, help="printed grid spacing on the card")
    ap.add_argument("--min-conf", type=float, default=0.3, help="low on purpose: a miss is worse than a skip")
    ap.add_argument("--cutouts", action="store_true", help="outline labelled boxes that have no cutout, then stop")
    args = ap.parse_args(argv)

    labels = args.data / "labels.csv"
    old = list(csv.DictReader(open(labels, newline=""))) if labels.exists() else []
    if args.cutouts:
        import torch
        from flat_bug.predictor import Predictor

        predictor = Predictor(model=args.weights, device="mps:0" if torch.backends.mps.is_available() else "cpu",
                              dtype="float32")
        n = fill_cutouts(predictor, args.data, old)
        with open(labels, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS, restval="")
            w.writeheader()
            w.writerows(old)
        print(f"Wrote {n} cutouts")
        return 0
    done = {r["photo"] for r in old}
    photos = [p for p in sorted((args.data / "inbox").iterdir())
              if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".heic") and p.name not in done]
    print(f"{len(done)} photos already cropped, {len(photos)} new")
    if not photos:
        return 0

    import torch
    from flat_bug.predictor import Predictor

    # flat-bug compares device strings exactly: tensors report "mps:0", not "mps"
    device = "mps:0" if torch.backends.mps.is_available() else "cpu"
    predictor = Predictor(model=args.weights, device=device, dtype="float32")

    new = []
    for p in photos:
        with Image.open(p) as im:
            img = ImageOps.exif_transpose(im).convert("RGB")
        bgr = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
        found = detect(predictor, img, p, args.min_conf)
        boxes = [(int(c[:, 0].min()), int(c[:, 1].min()), int(c[:, 0].max()) + 1, int(c[:, 1].max()) + 1)
                 for _, c in found]
        local = [local_grid_estimates(bgr, b, args.grid_mm) for b in boxes]
        photo_ppm = photo_px_per_mm([v for est in local for v, _ in est])
        rows = []
        for n, ((conf, c), box, est) in enumerate(zip(found, boxes, local), 1):
            ppm = pick_px_per_mm(est, photo_ppm)
            name = f"{p.stem}_{n:02d}"
            crop_path = args.data / "crops" / p.stem / f"{name}.jpg"
            cut_path = args.data / "cutouts" / f"{name}.png"
            crop_path.parent.mkdir(parents=True, exist_ok=True)
            cut_path.parent.mkdir(parents=True, exist_ok=True)
            server_crop(img, box).save(crop_path, quality=92)
            cutout(img, c, box).save(cut_path)
            long_px = max(cv2.minAreaRect(c)[1])
            rows.append({"photo": p.name, "n": str(n), "label": "", "source": "flatbug", "crop": str(crop_path), "cutout": str(cut_path),
                         "x1": box[0], "y1": box[1], "x2": box[2], "y2": box[3], "conf": f"{conf:.2f}",
                         "ppm": f"{ppm:.2f}" if ppm else "", "length_mm": f"{long_px / ppm:.1f}" if ppm else ""})
        (args.data / "boxes").mkdir(parents=True, exist_ok=True)
        draw_boxes(img, rows, args.data / "boxes" / f"{p.stem}.jpg")
        ppms = sorted(float(r["ppm"]) for r in rows if r["ppm"])
        scale = f"{photo_ppm:.1f} px/mm (insects {ppms[0]:.1f}-{ppms[-1]:.1f})" if ppms else "no grid found"
        print(f"  {p.name}: {len(rows)} insects, {scale}", flush=True)
        new += rows
        # after every photo, so a stopped run keeps what it did (full-size photos take minutes each)
        with open(labels, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(old + new)

    print(f"Wrote {len(new)} crops; label them in {labels} (see data/field/boxes/ for the numbers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
