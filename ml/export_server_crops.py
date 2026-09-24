"""Turn the server's reviewed detections into training photos: data/own/<label>/<card>/*.jpg.

    python export_server_crops.py --server ../server/data                  # reviewed insects only
    python export_server_crops.py --server ../server/data --empty-card T1-20260924T1650
                                   # every detection on a card we know is blank -> debris

What becomes a photo:
  * a track someone confirmed or relabelled on the dashboard's review page -> that label
  * a track someone rejected ("not an insect")                              -> debris
  * with --empty-card, every detection on that card                         -> debris
    (use it for liners photographed before any moth was on them: whatever the detector
    found there is grid, glare, dust or a shadow, which is exactly the debris class)

Every photo of a track is exported, not just one: the same insect under different light
and after a few days on the glue. They all share the card's folder, so build_dataset.py keeps
them in one split. Crops use the same square box and padding as the server's classifier
(server/sentinel_server/pipeline/classify.py: crop), so training crops look like what the
model will be given. Card folder names are <trap>-<install time>, e.g. T1-20260924T1650,
which is the name to put in data/own/locked_test.txt. Re-running overwrites the same files.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from PIL import Image

LABELS = {"CM", "OFM", "OBLR", "other_moth", "debris"}
PAD = 0.35  # same as the server's crop()


def crop(img: Image.Image, x1: float, y1: float, x2: float, y2: float, pad: float = PAD) -> Image.Image:
    side = max(x2 - x1, y2 - y1) * (1 + 2 * pad)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    return img.crop((int(cx - side / 2), int(cy - side / 2), int(cx + side / 2), int(cy + side / 2)))


def card_name(trap: str, installed_at: str) -> str:
    return f"{trap}-{datetime.fromisoformat(installed_at):%Y%m%dT%H%M}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", type=Path, required=True, help="the server's data dir (has sentinel.db and media/)")
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--empty-card", action="append", default=[], metavar="CARD",
                    help="card folder name whose detections are all debris (repeatable)")
    ap.add_argument("--min-side", type=int, default=12, help="skip detections smaller than this (px)")
    args = ap.parse_args(argv)

    db = sqlite3.connect(f"file:{args.server / 'sentinel.db'}?mode=ro", uri=True)
    q = """SELECT d.id, d.x1, d.y1, d.x2, d.y2, c.image_path, k.trap_id, k.installed_at,
                  t.review_status, t.reviewed_label
           FROM detections d JOIN captures c ON c.id = d.capture_id JOIN cards k ON k.id = c.card_id
           LEFT JOIN tracks t ON t.id = d.track_id"""
    empty = set(args.empty_card)
    seen_cards, counts, skipped = set(), Counter(), 0
    images: dict[str, Image.Image] = {}
    for det, x1, y1, x2, y2, image_path, trap, installed, status, reviewed in db.execute(q):
        card = card_name(trap, installed)
        seen_cards.add(card)
        if card in empty:
            label = "debris"
        elif status == "rejected":
            label = "debris"
        elif status == "confirmed" and reviewed in LABELS:
            label = reviewed
        else:
            continue
        if min(x2 - x1, y2 - y1) < args.min_side:
            skipped += 1
            continue
        if image_path not in images:
            with Image.open(args.server / "media" / image_path) as im:
                images[image_path] = im.convert("RGB")
        dest = args.data / "own" / label / card / f"{Path(image_path).stem}_d{det}.jpg"
        dest.parent.mkdir(parents=True, exist_ok=True)
        crop(images[image_path], x1, y1, x2, y2).save(dest, quality=95)
        counts[(label, card)] += 1

    for c in sorted(empty - seen_cards):
        print(f"warning: --empty-card {c} is not in this database (cards: {', '.join(sorted(seen_cards))})",
              file=sys.stderr)
    for (label, card), n in sorted(counts.items()):
        print(f"  {label:11} {card}  {n}")
    print(f"Exported {sum(counts.values())} crops to {args.data / 'own'}"
          + (f" (skipped {skipped} smaller than {args.min_side} px)" if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
