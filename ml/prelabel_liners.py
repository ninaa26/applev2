"""Put the liner photos on the labelling site with the boxes and labels our own models give them, all unchecked.

    python check_liner_photos.py          # first: which photos are fit to label
    python prelabel_liners.py             # -> data/review/labelling_site/labels.csv and inbox/
    python prelabel_liners.py --sets cornell --grid-mm 20     # redo nothing, add only what's new; see below

Every photo check_liner_photos.py didn't exclude, and that isn't on the site yet, gets:
  boxes   our YOLO11 detector (models/detector/yolo/yolo11s-ppm12-cuda, the Oct 8 2026 run), run the way the
          server's YoloDetector runs it: shrunk to the run's px/mm, cut into overlapping tiles, merged with the
          server's merge_tiles, with the confidence and NMS settings chosen on its val photos (summary.json). The
          scale comes from check_liner_photos.py's grid reading, which is right on the close-ups where the server's
          whole-photo reading is not. source=yolo, conf and detector_label are YOLO's own;
  labels  the v1 species classifier (models/classifier/bioclip_head/current/head.npz: BioCLIP 2 + linear head
          with its temperature, as the server's BioClipLinear) on each server-style crop, shrunk to --trap-ppm like
          eval_field_cards.py. model_label/model_conf hold its top class; label holds the pass-1 version of it
          (moth / other_insect / debris). Species are pass 2's, so they stay a suggestion;
  sizes   px/mm around each insect (from the grid, nearest the photo's), length_mm / body_mm from a GrabCut
          outline in the box (field_lengths.py), and that outline as the cutout make_trap_style.py pastes;
  old_label the label an earlier pass or the uploader gave the box it overlaps (label_sets.earlier_boxes).
          Boxes from those that YOLO missed are added as source=missed-by-detector, because every insect needs a box.
Nothing is checked: `by` is empty, and the site shows every row as unchecked until a person confirms or changes
it. Rows already on the site are never touched, so re-running only adds new photos.

The YOLO run trained on most of the Cornell cards and the OFM liners (summary.json lists them), so its boxes look
best there; that says nothing about other photos. Needs the ml venv with torch, open_clip and ultralytics
(requirements-train.txt); runs on the Mac, not on the Pi.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import paths
from crop_field_cards import FIELDS, PATCH_SIDES, grabcut_mask, pick_px_per_mm, server_crop
from field_lengths import measure
from label_sets import BY_NAME, SETS, earlier_boxes
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from sentinel_server.pipeline.detect import (  # noqa: E402
    CARD_EDGE_MM,
    Box,
    card_outline,
    find_grid,
    merge_fragments,
    merge_tiles,
    on_card,
    tile_origins,
)

MOTHS = {"CM", "OFM", "OBLR", "other_moth"}
YOLO_RUN = f"{paths.YOLO_RUNS}/yolo11s-ppm12-cuda"


def pass1(label: str) -> str:
    return "moth" if label in MOTHS else label


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class Yolo:
    """The server's YoloDetector, with the photo's px/mm passed in instead of read off the whole photo."""

    def __init__(self, run: Path):
        from ultralytics import YOLO  # type: ignore

        self.model = YOLO(str(run / "weights" / "best.pt"))
        info = json.loads((run / "summary.json").read_text())
        self.ppm, self.tile, self.overlap = info.get("ppm", 12), info.get("tile", 640), info.get("overlap", 160)
        self.imgsz = info.get("imgsz", self.tile)
        self.conf, self.iou = info.get("predict", {}).get("conf", 0.25), info.get("predict", {}).get("iou", 0.7)
        import torch

        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.version = f"yolo-{run.name}"

    def detect(self, bgr: np.ndarray, ppm: float | None) -> list[tuple[Box, str]]:
        s = min(1.0, self.ppm / ppm) if ppm else 1.0
        small = cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else bgr
        h, w = small.shape[:2]
        origins = tile_origins(w, h, self.tile, self.overlap)
        found, tiles, cls = [], [], []
        for i in range(0, len(origins), 16):
            crops = [small[y:y + self.tile, x:x + self.tile] for x, y in origins[i:i + 16]]
            results = self.model.predict(crops, imgsz=self.imgsz, conf=self.conf, iou=self.iou, max_det=1000,
                                         device=self.device, verbose=False)
            for n, ((ox, oy), r) in enumerate(zip(origins[i:i + 16], results)):
                names = r.names
                for (x1, y1, x2, y2), c, k in zip(r.boxes.xyxy.cpu().tolist(), r.boxes.conf.cpu().tolist(),
                                                  r.boxes.cls.cpu().tolist()):
                    found.append(((x1 + ox) / s, (y1 + oy) / s, (x2 + ox) / s, (y2 + oy) / s, float(c)))
                    tiles.append(i + n)
                    cls.append(names[int(k)])
        keep = merge_tiles(found, tiles)
        outline = card_outline(bgr)
        boxes = on_card([Box(*found[i]) for i in keep], outline, CARD_EDGE_MM * (ppm or 0))
        merged = merge_fragments(boxes)
        label_of = {(round(found[i][0]), round(found[i][1])): cls[i] for i in keep}
        return [(b, label_of.get((round(b.x1), round(b.y1)), "")) for b in merged]


class V1Classifier:
    """BioCLIP 2 features and the linear head with its temperature: the server's BioClipLinear, on PIL crops."""

    def __init__(self, head: Path):
        from train_v1 import Embedder

        z = np.load(head)
        self.W, self.b, self.classes = z["W"], z["b"], [str(c) for c in z["classes"]]
        self.T = float(z["T"]) if "T" in z else 1.0
        self.emb = Embedder(str(z["model"]))
        self.version = f"bioclip2-v1:{head.parent.name}"

    def classify(self, crops: list[Image.Image]) -> list[dict[str, float]]:
        torch, out = self.emb.torch, []
        for i in range(0, len(crops), 64):
            batch = torch.stack([self.emb.preprocess(c.convert("RGB")) for c in crops[i:i + 64]]).to(self.emb.device)
            with torch.no_grad():
                f = torch.nn.functional.normalize(self.emb.model.encode_image(batch), dim=-1).float().cpu().numpy()
            logits = (f @ self.W.T + self.b) / self.T
            p = np.exp(logits - logits.max(axis=1, keepdims=True))
            p /= p.sum(axis=1, keepdims=True)
            out += [dict(zip(self.classes, row.tolist())) for row in p]
        return out


def insect_ppm(bgr: np.ndarray, box, grid_mm: float, photo_ppm: float | None) -> float | None:
    """The grid's px/mm around one insect, nearest the photo's, on patches holding two squares at least."""
    if not photo_ppm:
        return None
    h, w = bgr.shape[:2]
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    est = []
    for side in PATCH_SIDES:
        if side == 0 or side < 2 * photo_ppm * grid_mm or side > max(h, w):
            continue
        patch = bgr[max(0, int(cy - side / 2)):min(h, int(cy + side / 2)), max(0, int(cx - side / 2)):min(w, int(cx + side / 2))]
        g = find_grid(patch)
        if g.score >= 20:
            est.append((g.pitch_px / grid_mm, g.score))
    return pick_px_per_mm(est, photo_ppm)


def trap_res(crop: Image.Image, ppm: float | None, trap_ppm: float) -> Image.Image:
    if not ppm or ppm <= trap_ppm:
        return crop
    f = trap_ppm / ppm
    return crop.resize((max(8, round(crop.width * f)), max(8, round(crop.height * f))), Image.LANCZOS)


def write(rows: list[dict], path: Path) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, restval="", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=paths.DATA)
    ap.add_argument("--sets", nargs="*", default=[s.name for s in SETS], choices=[s.name for s in SETS])
    ap.add_argument("--head", type=Path, default=Path(paths.CLASSIFIER_HEAD))
    ap.add_argument("--yolo", type=Path, default=Path(YOLO_RUN))
    ap.add_argument("--grid-mm", type=float, default=25.0, help="the liners' printed grid spacing")
    ap.add_argument("--trap-ppm", type=float, default=15.0, help="px/mm crops are shrunk to (Camera Module 3 ~15)")
    ap.add_argument("--match-iou", type=float, default=0.3, help="overlap for carrying an earlier label over")
    ap.add_argument("--no-cutouts", action="store_true", help="skip GrabCut (no cutouts, box-based lengths): faster")
    args = ap.parse_args(argv)
    site = args.data / paths.LABEL_SITE
    checks_path = site / "photo_checks.csv"
    if not checks_path.exists():
        raise SystemExit(f"no {checks_path}: run check_liner_photos.py first")
    with open(checks_path, newline="") as f:
        checks = {r["photo"]: r for r in csv.DictReader(f) if r["set"] in args.sets}
    for d in ("inbox", "crops", "cutouts", "backups"):
        (site / d).mkdir(parents=True, exist_ok=True)
    labels_path = site / "labels.csv"
    rows: list[dict] = []
    if labels_path.exists():
        with open(labels_path, newline="") as f:
            rows = list(csv.DictReader(f))
        shutil.copy(labels_path, site / "backups" / f"labels-{time.strftime('%Y%m%d-%H%M%S')}-before-prelabel.csv")
    done = {r["photo"] for r in rows}
    todo = [p for p, c in checks.items() if c["decision"] != "exclude" and p not in done]
    print(f"{len(todo)} photos to add, {len(done)} already on the site, "
          f"{sum(c['decision'] == 'exclude' for c in checks.values())} excluded by the checks")
    if not todo:
        return 0

    earlier = {name: earlier_boxes(args.data, BY_NAME[name]) for name in args.sets}
    detector, classifier = Yolo(args.yolo), V1Classifier(args.head)
    print(f"detector {detector.version} (conf {detector.conf}, NMS IoU {detector.iou}), classifier {classifier.version}")
    t0 = time.time()
    for k, photo in enumerate(todo, 1):
        c = checks[photo]
        src = args.data / c["source"]
        link = site / "inbox" / photo
        if not link.is_symlink():
            link.symlink_to(os.path.relpath(src.resolve(), link.parent.resolve()))
        with Image.open(src) as im:
            img = ImageOps.exif_transpose(im).convert("RGB")
        bgr = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
        photo_ppm = float(c["px_per_mm"]) if c["px_per_mm"] else None
        stem = Path(photo).stem
        new, crops = [], []
        for b, ylab in detector.detect(bgr, photo_ppm):
            box = (max(0, int(b.x1)), max(0, int(b.y1)), min(img.width, int(round(b.x2))), min(img.height, int(round(b.y2))))
            if box[2] - box[0] < 4 or box[3] - box[1] < 4:
                continue
            n = len(new) + 1
            ppm = insect_ppm(bgr, box, args.grid_mm, photo_ppm)
            crop = server_crop(img, box)
            crop_path = site / "crops" / stem / f"{stem}_y{n:03d}.jpg"
            crop_path.parent.mkdir(parents=True, exist_ok=True)
            crop.save(crop_path, quality=90)
            mask = None if args.no_cutouts else grabcut_mask(img, box)
            cut = ""
            if mask is not None:
                rgba = img.crop(box)
                rgba.putalpha(Image.fromarray((mask * 255).astype(np.uint8)))
                cut = str(site / "cutouts" / f"{stem}_y{n:03d}.png")
                rgba.save(cut)
            r = {"photo": photo, "n": str(n), "label": "", "source": "yolo", "crop": str(crop_path), "cutout": cut,
                 "x1": box[0], "y1": box[1], "x2": box[2], "y2": box[3], "conf": f"{b.conf:.2f}",
                 "ppm": f"{ppm:.2f}" if ppm else "", "detector_label": ylab, "by": ""}
            r.update(measure(mask, box, ppm))
            new.append(r)
            crops.append(trap_res(crop, ppm, args.trap_ppm))
        for r, probs in zip(new, classifier.classify(crops) if crops else []):
            top = max(probs, key=probs.get)
            r.update(label=pass1(top), model_label=top, model_conf=f"{probs[top]:.2f}")
        missed = 0
        for e in earlier[c["set"]].get(c["file"], []):
            eb = (e["x1"], e["y1"], e["x2"], e["y2"])
            best = max(new, key=lambda r: iou(eb, tuple(float(r[q]) for q in ("x1", "y1", "x2", "y2"))), default=None)
            if best and iou(eb, tuple(float(best[q]) for q in ("x1", "y1", "x2", "y2"))) >= args.match_iou:
                best["old_label"] = e["old_label"]
                continue
            old = e["row"] or {}
            box = tuple(int(round(v)) for v in eb)
            new.append({"photo": photo, "n": str(len(new) + 1), "label": e["label"], "source": "missed-by-detector",
                        "crop": old.get("crop", ""), "cutout": old.get("cutout", ""),
                        "x1": box[0], "y1": box[1], "x2": box[2], "y2": box[3], "conf": "",
                        "ppm": old.get("ppm") or (f"{photo_ppm:.2f}" if photo_ppm else ""),
                        "length_mm": old.get("length_mm", ""), "body_mm": old.get("body_mm", ""),
                        "length_from": old.get("length_from", ""), "old_label": e["old_label"], "by": ""})
            missed += 1
        rows += new
        labs = {lab: sum(r["label"] == lab for r in new) for lab in ("moth", "other_insect", "debris")}
        eta = (time.time() - t0) / k * (len(todo) - k) / 60
        print(f"  [{k}/{len(todo)}, ~{eta:.0f} min left] {photo}: {len(new) - missed} boxes ({labs['moth']} moth, "
              f"{labs['other_insect']} insect, {labs['debris']} debris), {missed} added from earlier labels", flush=True)
        write(rows, labels_path)  # after every photo, so a crash loses one photo at most
    print(f"{len(rows)} boxes on {len({r['photo'] for r in rows})} photos -> {labels_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
