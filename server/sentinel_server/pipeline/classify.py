"""Stage 2: species ID on a crop around each detection.

`none` leaves every insect as "unclassified" (counts still work).
`bioclip` is the v0 zero-shot baseline from the model plan: BioCLIP 2 compares
each crop with text prompts for our classes.
`bioclip-v1` puts the linear head trained by ml/train_v1.py on the same features
(SENTINEL_CLASSIFIER_HEAD points at its head.npz). Classes the head wasn't trained
on (e.g. debris, before we have debris crops) get probability 0.
`cnn-v2` is the fine-tuned CNN from ml/train_v2.py (SENTINEL_CLASSIFIER_MODEL points at
its models/v2/<arch>.pt).
"""

from __future__ import annotations

import os

import numpy as np
from PIL import Image

from ..models import SPECIES

PROMPTS = {
    "CM": "a photo of Cydia pomonella, codling moth",
    "OFM": "a photo of Grapholita molesta, oriental fruit moth",
    "OBLR": "a photo of Choristoneura rosaceana, obliquebanded leafroller",
    "other_moth": "a photo of a small moth",
    "debris": "a photo of dirt, a leaf fragment or debris on sticky paper",
}


def crop(img: Image.Image, box, pad: float = 0.35) -> Image.Image:
    w, h = box.x2 - box.x1, box.y2 - box.y1
    side = max(w, h) * (1 + 2 * pad)
    cx, cy = (box.x1 + box.x2) / 2, (box.y1 + box.y2) / 2
    return img.crop((int(cx - side / 2), int(cy - side / 2), int(cx + side / 2), int(cy + side / 2)))


class NoClassifier:
    version = "none"

    def classify(self, crops: list[Image.Image]) -> list[dict[str, float]]:
        return [{} for _ in crops]


class _BioClip:  # pragma: no cover - needs torch + open_clip + weights download
    MODEL = "hf-hub:imageomics/bioclip-2"

    def __init__(self, model_name: str | None = None):
        import open_clip
        import torch

        self.torch = torch
        self.model_name = model_name or self.MODEL
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(self.model_name)
        self.model = self.model.to(self.device).eval()
        self.tokenizer = open_clip.get_tokenizer(self.model_name)

    def features(self, crops: list[Image.Image]):
        torch = self.torch
        with torch.no_grad():
            batch = torch.stack([self.preprocess(c.convert("RGB")) for c in crops]).to(self.device)
            feats = self.model.encode_image(batch)
            return feats / feats.norm(dim=-1, keepdim=True)


class BioClipZeroShot(_BioClip):  # pragma: no cover
    version = "bioclip2-zeroshot"

    def __init__(self):
        super().__init__()
        with self.torch.no_grad():
            feats = self.model.encode_text(self.tokenizer([PROMPTS[s] for s in SPECIES]).to(self.device))
            self.text_feats = feats / feats.norm(dim=-1, keepdim=True)

    def classify(self, crops: list[Image.Image]) -> list[dict[str, float]]:
        if not crops:
            return []
        probs = (100.0 * self.features(crops) @ self.text_feats.T).softmax(dim=-1).cpu().tolist()
        return [dict(zip(SPECIES, p)) for p in probs]


def linear_head_probs(feats: np.ndarray, W: np.ndarray, b: np.ndarray, classes: list[str]) -> list[dict[str, float]]:
    logits = feats @ W.T + b
    logits -= logits.max(axis=1, keepdims=True)
    p = np.exp(logits)
    p /= p.sum(axis=1, keepdims=True)
    return [{s: float(row[classes.index(s)]) if s in classes else 0.0 for s in SPECIES} for row in p]


class BioClipLinear(_BioClip):  # pragma: no cover
    def __init__(self, head_path: str):
        z = np.load(head_path, allow_pickle=False)
        self.W, self.b = z["W"], z["b"]
        self.classes = z["classes"].tolist()
        super().__init__(str(z["model"]))
        self.version = f"bioclip2-v1:{os.path.basename(os.path.dirname(os.path.abspath(head_path)))}"

    def classify(self, crops: list[Image.Image]) -> list[dict[str, float]]:
        if not crops:
            return []
        feats = self.features(crops).float().cpu().numpy()
        return linear_head_probs(feats, self.W, self.b, self.classes)


class FineTunedCNN:  # pragma: no cover - needs torch + torchvision
    def __init__(self, model_path: str):
        import torch
        from torchvision import models, transforms

        ck = torch.load(model_path, map_location="cpu", weights_only=False)
        self.torch, self.classes = torch, list(ck["classes"])
        m = getattr(models, ck["arch"])(num_classes=len(self.classes))
        m.load_state_dict(ck["state_dict"])
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.model = m.to(self.device).eval()
        size = ck["size"]
        self.preprocess = transforms.Compose([transforms.Resize((size, size)), transforms.ToTensor(),
                                              transforms.Normalize(ck["mean"], ck["std"])])
        self.version = f"cnn-v2:{ck['arch']}"

    def classify(self, crops: list[Image.Image]) -> list[dict[str, float]]:
        if not crops:
            return []
        torch = self.torch
        with torch.no_grad():
            x = torch.stack([self.preprocess(c.convert("RGB")) for c in crops]).to(self.device)
            p = self.model(x).softmax(dim=-1).cpu().numpy()
        return [{s: float(row[self.classes.index(s)]) if s in self.classes else 0.0 for s in SPECIES} for row in p]


def make_classifier(name: str):
    if name == "none":
        return NoClassifier()
    if name == "bioclip":
        return BioClipZeroShot()
    if name == "bioclip-v1":
        head = os.environ.get("SENTINEL_CLASSIFIER_HEAD", "")
        if not head:
            raise ValueError("SENTINEL_CLASSIFIER=bioclip-v1 needs SENTINEL_CLASSIFIER_HEAD=<path to ml/models/v1/head.npz>")
        return BioClipLinear(head)
    if name == "cnn-v2":
        path = os.environ.get("SENTINEL_CLASSIFIER_MODEL", "")
        if not path:
            raise ValueError("SENTINEL_CLASSIFIER=cnn-v2 needs SENTINEL_CLASSIFIER_MODEL=<path to ml/models/v2/<arch>.pt>")
        return FineTunedCNN(path)
    raise ValueError(f"unknown classifier {name!r}")
