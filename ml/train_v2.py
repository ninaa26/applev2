"""Model v2 species ID: fine-tune a small CNN end to end on the same dataset.csv as v1.

    python train_v2.py                              # EfficientNet-B0, 8 epochs
    python train_v2.py --arch mobilenet_v3_large    # smaller/faster, a candidate for running on the Pi
    python train_v2.py --final                      # also report on our locked test cards (once, at the end)

Grew out of Patti's MobileNetV3 script (CM vs not-CM on an ImageFolder, repo root "Patti's code"):
same idea and augmentations (any rotation, flips, colour jitter), but on all five trap classes and
the group-aware train/val/test split from build_dataset.py, so photos of the same moth never
sit on both sides. Classes are balanced by sampling, since there are ~100 OFM photos and ~2,000
of each of the others. The epoch with the best val balanced accuracy is kept.

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


def transforms_for(size: int):
    from torchvision import transforms as T

    train = T.Compose([
        T.RandomResizedCrop(size, scale=(0.6, 1.0), ratio=(0.8, 1.25)),
        T.RandomRotation(180),  # moths land on the liner at any angle
        T.RandomHorizontalFlip(),
        T.RandomVerticalFlip(),
        T.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.05),
        T.RandomApply([T.GaussianBlur(5, sigma=(0.1, 1.5))], p=0.3),
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
    ap.add_argument("--final", action="store_true", help="also evaluate on the locked test cards")
    args = ap.parse_args(argv)

    import torch
    from torch.utils.data import DataLoader, WeightedRandomSampler

    torch.manual_seed(0)
    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    rows = [r for r in load_rows(args.data) if r["split"] != "locked" or args.final]
    classes = sorted({r["class"] for r in rows if r["split"] == "train"})
    idx = {c: k for k, c in enumerate(classes)}
    rows = [r for r in rows if r["class"] in idx]

    def items(pred):
        return [(r["path"], idx[r["class"]]) for r in rows if pred(r)]

    train_items = items(lambda r: r["split"] == "train")
    evals = {"val": items(lambda r: r["split"] == "val"),
             "test · web photos": items(lambda r: r["split"] == "test" and r["source"] != "synth"),
             "test · trap-style": items(lambda r: r["split"] == "test" and r["source"] == "synth")}
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
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=steps)
    loss_fn = torch.nn.CrossEntropyLoss(label_smoothing=0.05)

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
