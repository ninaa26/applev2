"""Model v2 species ID: fine-tune a small CNN end to end on the same dataset.csv as v1.

    python train_v2.py                              # EfficientNet-B0, 8 epochs
    python train_v2.py --arch mobilenet_v3_large    # smaller/faster, a candidate for running on the Pi
    python train_v2.py --final                      # also report on our locked test cards (once, at the end)

Grew out of Patti's MobileNetV3 script (CM vs not-CM on an ImageFolder, repo root "Patti's code"):
same idea (any rotation, flips), but on all six trap classes and the group-aware train/val/test
split from build_dataset.py, so photos of the same moth never sit on both sides. Classes are
balanced by sampling, since there are ~100 OFM photos and ~2,000 of each of the others. The epoch
with the best val balanced accuracy is kept.

Augmentation follows what closed the web-photo -> trap gap on the AMI benchmark (Jain et al. 2024:
trap accuracy 51.5% -> 71.9%): RandAugment plus mixed resolution (MixRes: half the training photos
are shrunk to a trap-sized crop and blown back up, so the net sees the blur of a small moth and not
only sharp web photos). AdamW, one warm-up epoch then cosine decay, label smoothing 0.1, as in the
AMI classifiers. --size stays 224: a trap crop is 110-260 px here (10-15 px/mm, padded), and on AMI
going from 128 to 224 helped web photos but cost 3.5 points on trap crops, so compare --size 128 on
real-liner crops (eval_liner_species.py) before trusting the web-photo score.

Reports use the same format as train_v1.py, with web photos and trap-style photos
(make_trap_style.py) scored separately. Writes models/v2/<arch>.pt (weights, classes, arch,
image size), metrics.json and report.md.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

from train_v1 import format_report, load_rows, report

ARCHS = ("efficientnet_b0", "mobilenet_v3_large", "mobilenet_v3_small")
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]


def build_model(arch: str, n_classes: int):
    import torch.nn as nn
    from torchvision import models

    if arch == "efficientnet_b0":
        m = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.DEFAULT)
        m.classifier[1] = nn.Linear(m.classifier[1].in_features, n_classes)
    elif arch == "mobilenet_v3_large":
        m = models.mobilenet_v3_large(weights=models.MobileNet_V3_Large_Weights.DEFAULT)
        m.classifier[3] = nn.Linear(m.classifier[3].in_features, n_classes)
    elif arch == "mobilenet_v3_small":
        m = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT)
        m.classifier[3] = nn.Linear(m.classifier[3].in_features, n_classes)
    else:
        raise ValueError(arch)
    return m


class Photos:
    """(path, class index) pairs -> tensors. JPEGs are decoded at reduced size (draft mode):
    the web photos are up to 2048 px and we only need ~256."""

    def __init__(self, items: list[tuple[str, int]], transform, size: int):
        self.items, self.transform, self.size = items, transform, size

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        from PIL import Image, ImageOps

        path, y = self.items[i]
        with Image.open(path) as im:
            im.draft("RGB", (self.size * 2, self.size * 2))
            im = ImageOps.exif_transpose(im).convert("RGB")
        return self.transform(im), y


class MixRes:
    """Mixed resolution: with probability p, shrink the photo so its long side is a random `sides` px (what a
    small or far-off moth's crop holds) and enlarge it back, keeping its size."""

    def __init__(self, sides: tuple[int, int] = (48, 160), p: float = 0.5, seed: int | None = None):
        import random

        self.sides, self.p, self.rng = sides, p, random.Random(seed)

    def __call__(self, im):
        from PIL import Image

        if self.rng.random() >= self.p:
            return im
        s = self.rng.randint(*self.sides) / max(im.size)
        if s >= 1:
            return im
        small = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.BILINEAR)
        return small.resize(im.size, Image.BILINEAR)


def transforms_for(size: int):
    from torchvision import transforms as T

    train = T.Compose([
        T.RandomResizedCrop(size, scale=(0.6, 1.0), ratio=(0.8, 1.25)),
        T.RandomRotation(180),  # moths land on the liner at any angle
        T.RandomHorizontalFlip(),
        T.RandomVerticalFlip(),
        T.RandAugment(num_ops=2, magnitude=9),
        MixRes(),
        T.ToTensor(),
        T.Normalize(MEAN, STD),
    ])
    evaluate = T.Compose([T.Resize((size, size)), T.ToTensor(), T.Normalize(MEAN, STD)])
    return train, evaluate


def predict(model, loader, device) -> np.ndarray:
    import torch

    model.eval()
    out = []
    with torch.no_grad():
        for x, _ in loader:
            out.append(model(x.to(device)).float().cpu().numpy())
    return np.concatenate(out) if out else np.zeros((0, 0))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--out", type=Path, default=Path("models/v2"))
    ap.add_argument("--arch", choices=ARCHS, default="efficientnet_b0")
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--batch", type=int, default=48)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--size", type=int, default=224)
    ap.add_argument("--samples-per-epoch", type=int, default=12000,
                    help="class-balanced draws per epoch (the rare classes repeat, the common ones are subsampled)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--device", default="auto", help="auto (mps > cuda > cpu), or cpu if the GPU stalls")
    ap.add_argument("--final", action="store_true", help="also evaluate on the locked test cards")
    args = ap.parse_args(argv)

    import torch
    from torch.utils.data import DataLoader, WeightedRandomSampler

    torch.manual_seed(0)
    device = args.device
    if device == "auto":
        device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    rows = [r for r in load_rows(args.data) if r["split"] != "locked" or args.final]
    classes = sorted({r["class"] for r in rows if r["split"] == "train"})
    idx = {c: k for k, c in enumerate(classes)}
    rows = [r for r in rows if r["class"] in idx]

    def items(pred):
        return [(r["path"], idx[r["class"]]) for r in rows if pred(r)]

    train_items = items(lambda r: r["split"] == "train")
    evals = {"val": items(lambda r: r["split"] == "val"),
             "test · web photos": items(lambda r: r["split"] == "test" and r["source"] in ("inat", "ami")),
             "test · trap-style": items(lambda r: r["split"] == "test" and r["source"] == "synth"),
             "test · real liners (held out)": items(lambda r: r["split"] == "test" and r["source"] == "liner")}
    if args.final:
        evals["LOCKED own cards"] = items(lambda r: r["split"] == "locked")
    evals = {k: v for k, v in evals.items() if v}
    counts = np.bincount([y for _, y in train_items], minlength=len(classes))
    print(f"Device {device}; classes {classes}; train per class {counts.tolist()}; "
          + ", ".join(f"{k} {len(v)}" for k, v in evals.items()))

    t_train, t_eval = transforms_for(args.size)
    weights = [1.0 / counts[y] for _, y in train_items]
    sampler = WeightedRandomSampler(weights, num_samples=args.samples_per_epoch, replacement=True)
    loader_kw = dict(batch_size=args.batch, num_workers=args.workers, persistent_workers=args.workers > 0)
    train_loader = DataLoader(Photos(train_items, t_train, args.size), sampler=sampler, **loader_kw)
    eval_loaders = {k: DataLoader(Photos(v, t_eval, args.size), shuffle=False, **loader_kw) for k, v in evals.items()}
    y_eval = {k: np.array([y for _, y in v]) for k, v in evals.items()}

    model = build_model(args.arch, len(classes)).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    steps = args.epochs * len(train_loader)
    warm = min(len(train_loader), steps // 2)
    sched = torch.optim.lr_scheduler.SequentialLR(opt, milestones=[warm], schedulers=[
        torch.optim.lr_scheduler.LinearLR(opt, start_factor=0.05, total_iters=warm),
        torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(1, steps - warm))])
    loss_fn = torch.nn.CrossEntropyLoss(label_smoothing=0.1)

    best, best_state = -1.0, None
    for epoch in range(1, args.epochs + 1):
        model.train()
        t0, total, n = time.time(), 0.0, 0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            opt.zero_grad()
            loss = loss_fn(model(x), y)
            loss.backward()
            opt.step()
            sched.step()
            total, n = total + loss.item() * len(y), n + len(y)
        val = report(y_eval["val"], predict(model, eval_loaders["val"], device).argmax(1), classes)
        print(f"epoch {epoch}/{args.epochs}  loss {total / n:.3f}  val balanced acc {val['balanced_accuracy']:.3f}"
              f"  ({time.time() - t0:.0f}s)", flush=True)
        if val["balanced_accuracy"] > best:
            best = val["balanced_accuracy"]
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)
    results = {}
    for k in evals:
        if k != "val":
            results[f"v2 {args.arch} · {k}"] = report(y_eval[k], predict(model, eval_loaders[k], device).argmax(1), classes)

    args.out.mkdir(parents=True, exist_ok=True)
    torch.save({"state_dict": best_state, "arch": args.arch, "classes": classes, "size": args.size,
                "mean": MEAN, "std": STD, "val_balanced_accuracy": best}, args.out / f"{args.arch}.pt")
    (args.out / "metrics.json").write_text(json.dumps(results, indent=2))
    md = [f"# Species ID v2: fine-tuned {args.arch}", "",
          f"{args.epochs} epochs, {args.samples_per_epoch} class-balanced draws each; best val balanced accuracy "
          f"{best:.3f}. Web-photo and trap-style tests are sanity checks, not trap accuracy (see ml/README.md).", ""]
    md += [format_report(k, v) for k, v in results.items()]
    (args.out / "report.md").write_text("\n".join(md))
    for k, v in results.items():
        print("\n" + format_report(k, v))
    print(f"Saved {args.out / (args.arch + '.pt')}, metrics.json, report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
