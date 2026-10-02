"""Score the insect detectors against hand-drawn boxes on other people's liner photos (Roboflow).

    python eval_detector_roboflow.py                          # both detectors, both datasets
    python eval_detector_roboflow.py --detector baseline      # the server's default only (fast)
    python eval_detector_roboflow.py --trap-ppm 8             # also shrink each photo to the trap camera's px/mm

The datasets are COCO exports in data/web_liners/roboflow_full/, or their boxes moved back onto the
original uploads in roboflow_recovered/ (see the README there): codling-moth-ervins (Trécé cards, phone photos, CM boxed) and ofm-ervins (trap-camera
close-ups of a gridded liner, OFM boxed, class mislabelled `codling_moth`). Only the target moth
was boxed, so a detection that matches no box may be real bycatch: precision here is a lower bound.
Recall is the number that matters: how many of the moths a person boxed did the detector find.

Matching is one-to-one, highest confidence first. A detection takes a box when their IoU is at least
--iou, or when each one's centre lies inside the other (detectors draw looser or tighter boxes than
people do). A baseline box with n > 1 (touching insects it couldn't split) may take up to n boxes
whose centres it contains, which is how the tracker counts it.

"trap" resolution: the photo is shrunk so the card's printed grid (--grid-mm) comes out at
--trap-ppm px/mm, which is what the trap camera would see. Photos where the grid isn't found are
left out of that pass. Detections are cached in data/web_liners/detector_eval/cache/, so changing
--iou or --min-conf re-scores without re-running the detectors. Writes
data/web_liners/detector_eval/report.md, per_image.csv and an overlay of the worst photos per run.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from sentinel_server.pipeline.detect import BaselineDetector, find_grid  # noqa: E402

# (export folder, group shown in the report, which photos): most of the CM set was uploaded as 640×640
# (~2.4 px/mm, a third of what the trap sees), so it's scored apart from the few full-size phone photos
GROUPS = [("codling-moth-ervins", "640² uploads", lambda im: im["w"] <= 640),
          ("codling-moth-ervins", "full-size", lambda im: im["w"] > 640),
          ("ofm-ervins", "all", lambda im: True),
          # boxes moved back onto the original uploads (recover_roboflow_originals.py); the moth-project
          # sets are the same cards as codling-moth-ervins, boxed again, so they're left out
          ("moth-counting-matogen", "originals", lambda im: True),
          ("grape-moth-nsect", "originals", lambda im: True)]


def dataset_dir(data: Path, ds: str) -> Path:
    """The un-stretched copy when there is one (roboflow_recovered/), else the export (roboflow_full/)."""
    rec = data / "roboflow_recovered" / ds
    return rec if rec.exists() else data / "roboflow_full" / ds
CONFS = [0.2, 0.3, 0.4, 0.5]  # flatbug thresholds reported (crop_field_cards uses 0.3)


def load_coco(root: Path) -> list[dict]:
    """[{path, w, h, gt: [(x1, y1, x2, y2)]}] over every split of one export."""
    out = []
    for j in sorted(root.glob("*/_annotations.coco.json")):
        coco = json.load(open(j))
        boxes: dict[int, list] = {}
        for a in coco["annotations"]:
            x, y, w, h = a["bbox"]
            boxes.setdefault(a["image_id"], []).append((x, y, x + w, y + h))
        for im in coco["images"]:
            out.append({"path": j.parent / im["file_name"], "w": im["width"], "h": im["height"],
                        "gt": boxes.get(im["id"], [])})
    return out


def grid_px_per_mm(img: np.ndarray, grid_mm: float) -> float | None:
    f = min(1.0, 1600 / max(img.shape[:2]))
    small = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA) if f < 1 else img
    g = find_grid(small)
    return g.pitch_px / f / grid_mm if g.score > 0 and g.pitch_px > 0 else None


class Flatbug:
    def __init__(self, weights: str):
        import torch
        from flat_bug.predictor import Predictor

        # flat-bug compares device strings exactly: tensors report "mps:0", not "mps"
        self.model = Predictor(model=weights, device="mps:0" if torch.backends.mps.is_available() else "cpu",
                               dtype="float32")

    def __call__(self, img: np.ndarray, path: Path) -> list[list[float]]:
        import torch

        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        pred = self.model(torch.from_numpy(rgb.copy()).permute(2, 0, 1), path=str(path))
        return [[*map(float, b), float(c), 1] for b, c in zip(pred.boxes.cpu().tolist(), pred.confs.cpu().tolist())]


class Baseline:
    def __init__(self, grid_mm: float):
        self.det = BaselineDetector(grid_mm=grid_mm, lens=0.0)  # phone photos: no trap lens to undo

    def __call__(self, img: np.ndarray, path: Path) -> list[list[float]]:
        return [[b.x1, b.y1, b.x2, b.y2, b.conf, b.n] for b in self.det.detect_array(img)]


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter + 1e-9)


def inside(pt, box) -> bool:
    return box[0] <= pt[0] <= box[2] and box[1] <= pt[1] <= box[3]


def centre(b):
    return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2)


def match(gt: list, dets: list, min_iou: float) -> tuple[list[bool], list[int]]:
    """found[i] for each gt box; used[j] = how many gt boxes detection j took."""
    found = [False] * len(gt)
    used = [0] * len(dets)
    for j in sorted(range(len(dets)), key=lambda j: -dets[j][4]):
        d = dets[j]
        cap = max(1, int(d[5]))
        cands = []
        for i, g in enumerate(gt):
            if found[i]:
                continue
            o = iou(g, d)
            mutual = inside(centre(g), d) and inside(centre(d), g)
            many = cap > 1 and inside(centre(g), d)
            if o >= min_iou or mutual or many:
                cands.append((-o, i))
        for _, i in sorted(cands)[:cap]:
            found[i] = True
            used[j] += 1
    return found, used


def detect_all(name: str, detector, images: list[dict], cache: Path, trap_ppm: float | None,
               grid_mm: float) -> list[dict]:
    """Run (or load) one detector over one dataset at native or trap resolution."""
    cache.parent.mkdir(parents=True, exist_ok=True)
    done = json.load(open(cache)) if cache.exists() else {}
    for k, im in enumerate(images, 1):
        key = im["path"].name
        if key in done:
            continue
        img = cv2.imread(str(im["path"]))
        scale = 1.0
        if trap_ppm:
            ppm = grid_px_per_mm(img, grid_mm)
            if ppm is None or ppm <= trap_ppm:
                done[key] = {"skip": "no grid" if ppm is None else f"already {ppm:.1f} px/mm"}
                continue
            scale = trap_ppm / ppm
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        dets = detector(img, im["path"]) if detector else []
        done[key] = {"scale": scale, "dets": [[x1 / scale, y1 / scale, x2 / scale, y2 / scale, c, n]
                                              for x1, y1, x2, y2, c, n in dets]}
        print(f"  {name}: {k}/{len(images)} {key[:40]} {len(dets)} found", flush=True)
        json.dump(done, open(cache, "w"))  # after every photo: flatbug on a full-size photo takes a while
    return [done[im["path"].name] for im in images]


def overlay(im: dict, dets: list, found: list[bool], used: list[int], dest: Path) -> None:
    img = cv2.imread(str(im["path"]))
    t = max(2, int(max(img.shape[:2]) / 600))
    for d, u in zip(dets, used):
        cv2.rectangle(img, (int(d[0]), int(d[1])), (int(d[2]), int(d[3])), (255, 120, 0) if u else (0, 0, 255), t)
    for g, f in zip(im["gt"], found):
        c = (0, 200, 0) if f else (255, 0, 255)
        cv2.rectangle(img, (int(g[0]), int(g[1])), (int(g[2]), int(g[3])), c, t if f else 2 * t)
    f = min(1.0, 1400 / max(img.shape[:2]))
    cv2.imwrite(str(dest), cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA),
                [cv2.IMWRITE_JPEG_QUALITY, 85])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data/web_liners"))
    ap.add_argument("--detector", choices=["baseline", "flatbug", "both"], default="both")
    ap.add_argument("--weights", default="flat_bug_M.pt")
    ap.add_argument("--grid-mm", type=float, default=25.0, help="printed grid spacing on the liner")
    ap.add_argument("--trap-ppm", type=float, default=None, help="also score at this px/mm (webcam ~7, Camera Module 3 ~15)")
    ap.add_argument("--iou", type=float, default=0.3)
    ap.add_argument("--worst", type=int, default=6, help="overlays written per run (lowest recall first)")
    args = ap.parse_args(argv)

    out = args.data / "detector_eval"
    (out / "overlays").mkdir(parents=True, exist_ok=True)
    names = ["baseline", "flatbug"] if args.detector == "both" else [args.detector]
    res = [None] + ([args.trap_ppm] if args.trap_ppm else [])
    lines = ["# Detectors vs hand-drawn boxes (Roboflow liner photos)", "",
             f"Matching: IoU ≥ {args.iou:g} or mutual centres; baseline clumps may take n boxes. Only the target "
             "moth was boxed, so unmatched detections include real bycatch: **precision is a lower bound**. "
             "Count ratio = detected insects ÷ boxed moths (above 1 is expected where there's bycatch).", "",
             "| Dataset | Detector | Resolution | Photos | Boxed | Recall | Precision ≥ | Count ratio | Median px/mm |",
             "|---|---|---|---|---|---|---|---|---|"]
    rows = []
    for ds in dict.fromkeys(g[0] for g in GROUPS):
        images = load_coco(dataset_dir(args.data, ds))
        ppm_of = {im["path"].name: grid_px_per_mm(cv2.imread(str(im["path"])), args.grid_mm) for im in images}
        for name in names:
            det = None
            for r in res:
                tag = "native" if r is None else f"{r:g}ppm"
                cache = out / "cache" / f"{ds}__{name}__{tag}.json"
                if det is None and not _cached_all(cache, images):
                    det = Flatbug(args.weights) if name == "flatbug" else Baseline(args.grid_mm)
                run_of = dict(zip((im["path"].name for im in images),
                                  detect_all(f"{ds}/{name}/{tag}", det, images, cache, r, args.grid_mm)))
                for gds, group, keep in GROUPS:
                    if gds != ds:
                        continue
                    sub = [im for im in images if keep(im) and "skip" not in run_of[im["path"].name]]
                    if not sub:
                        continue
                    ppms = [ppm_of[im["path"].name] for im in sub if ppm_of[im["path"].name]]
                    med = f"{np.median(ppms):.1f}" if ppms else "?"
                    for th in (CONFS if name == "flatbug" else [0.0]):
                        tot_gt = tot_found = tot_det = tot_used = count_det = 0
                        per = []
                        for im in sub:
                            dets = [d for d in run_of[im["path"].name]["dets"] if d[4] >= th]
                            found, used = match(im["gt"], dets, args.iou)
                            tot_gt += len(im["gt"])
                            tot_found += sum(found)
                            tot_det += len(dets)
                            tot_used += sum(1 for u in used if u)
                            count_det += sum(max(1, int(d[5])) for d in dets)
                            per.append((sum(found) / max(1, len(im["gt"])), im, dets, found, used))
                            rows.append({"dataset": ds, "group": group, "detector": name, "resolution": tag,
                                         "min_conf": th, "photo": im["path"].name, "boxed": len(im["gt"]),
                                         "found": sum(found), "detections": len(dets),
                                         "matched_dets": sum(1 for u in used if u),
                                         "px_per_mm": f"{ppm_of[im['path'].name]:.1f}" if ppm_of[im["path"].name] else ""})
                        conf = f" (conf ≥ {th:g})" if name == "flatbug" else ""
                        lines.append(f"| {ds} · {group} | {name}{conf} | {tag} | {len(sub)} | {tot_gt} | "
                                     f"**{tot_found / tot_gt:.0%}** | {tot_used / max(1, tot_det):.0%} | "
                                     f"{count_det / tot_gt:.2f} | {med} |")
                        if th == (0.3 if name == "flatbug" else 0.0):
                            for k, (_, im, dets, found, used) in enumerate(sorted(per, key=lambda p: p[0])[:args.worst]):
                                overlay(im, dets, found, used, out / "overlays" /
                                        f"{ds}__{group.split()[0].replace('²', '')}__{name}__{tag}__{k + 1}_{im['path'].stem[:30]}.jpg")
    lines += ["", "Overlays (worst recall first, flatbug at conf 0.3): green = boxed and found, **magenta = boxed "
              "but missed**, orange = detection that matched, red = detection with no box (bycatch, debris or a "
              "false alarm)."]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    with open(out / "per_image.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print("\n".join(lines))
    return 0


def _cached_all(cache: Path, images: list[dict]) -> bool:
    if not cache.exists():
        return False
    done = json.load(open(cache))
    return all(im["path"].name in done for im in images)


if __name__ == "__main__":
    raise SystemExit(main())
