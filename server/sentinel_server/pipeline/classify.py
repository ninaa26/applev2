"""Stage 2: species ID on a crop around each detection.

`none` leaves every insect as "unclassified" (counts still work).
`bioclip` is the v0 zero-shot baseline from the model plan: BioCLIP 2 compares
each crop with text prompts for our classes. v1 (a small trained layer on top
of these features) replaces it once we have labelled staged-card crops.
"""

from __future__ import annotations

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


class BioClipZeroShot:  # pragma: no cover - needs torch + open_clip + weights download
    version = "bioclip2-zeroshot"

    def __init__(self):
        import open_clip
        import torch

        self.torch = torch
        self.device = "mps" if torch.backends.mps.is_available() else "cpu"
        self.model, _, self.preprocess = open_clip.create_model_and_transforms("hf-hub:imageomics/bioclip-2")
        self.model = self.model.to(self.device).eval()
        tokenizer = open_clip.get_tokenizer("hf-hub:imageomics/bioclip-2")
        with torch.no_grad():
            text = tokenizer([PROMPTS[s] for s in SPECIES]).to(self.device)
            feats = self.model.encode_text(text)
            self.text_feats = feats / feats.norm(dim=-1, keepdim=True)

    def classify(self, crops: list[Image.Image]) -> list[dict[str, float]]:
        if not crops:
            return []
        torch = self.torch
        with torch.no_grad():
            batch = torch.stack([self.preprocess(c.convert("RGB")) for c in crops]).to(self.device)
            feats = self.model.encode_image(batch)
            feats = feats / feats.norm(dim=-1, keepdim=True)
            probs = (100.0 * feats @ self.text_feats.T).softmax(dim=-1).cpu().tolist()
        return [dict(zip(SPECIES, p)) for p in probs]


def make_classifier(name: str):
    if name == "none":
        return NoClassifier()
    if name == "bioclip":
        return BioClipZeroShot()
    raise ValueError(f"unknown classifier {name!r}")
