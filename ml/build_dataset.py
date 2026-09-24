"""Merge every photo source into one labelled, de-duplicated, split dataset: data/dataset.csv.

    python build_dataset.py                 # after fetch_ami.py / fetch_inat.py / adding own photos
    python build_dataset.py --data data     # (default)

Sources, all optional:
  data/ami/manifest.csv     from fetch_ami.py
  data/inat/manifest.csv    from fetch_inat.py
  data/own/<label>/<card>/*.jpg
                            our own photos: crops from staged cards or trap liners, one folder per
                            card. Labels: CM, OFM, OBLR, other_moth, debris (or any fine label below).
  data/own/locked_test.txt  card folder names set aside for the final evaluation (one per line).
                            These get split "locked" and train_v1.py never touches them unless --final.
  data/synth/manifest.csv   from make_trap_style.py: web moths pasted onto liner photos. Each one
                            takes its source photo's group, so it lands in the same split, and is
                            dropped if its source photo was dropped. Not de-duplicated (they are
                            all different by construction).

Duplicates: AMI photos that came from iNaturalist are matched by photo id and the iNat copy
is kept. Then every image gets a 256-bit difference hash (16x16); near-identical images
(<= 10 bits apart) are candidates, confirmed by comparing 64x64 thumbnails (a small moth on
a plain wall hashes like any other plain wall); confirmed duplicates are dropped, keeping own > inat > ami. Near-duplicates with *different* labels are
dropped entirely and listed, since one of the labels is wrong.

Splits are by group (an iNat observation, a GBIF occurrence, or one of our cards), so photos
of the same moth never land in both train and test. Web photos are for training and model
selection only; accuracy for the report comes from our own locked cards.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

# Fine label -> the class the trap's classifier predicts.
CLASS_OF = {
    "CM": "CM",
    "OFM": "OFM",
    "OBLR": "OBLR",
    "lookalike_LAW": "other_moth",
    "lookalike_RBLR": "other_moth",
    "other_tortricid": "other_moth",
    "other_moth": "other_moth",
    # Non-moth bycatch is its own class: an insect, but not a moth, so it isn't counted.
    "other_insect": "other_insect",
    "bycatch_fly": "other_insect",
    "bycatch_wasp": "other_insect",
    "bycatch_beetle": "other_insect",
    "bycatch_lacewing": "other_insect",
    "bycatch_leafhopper": "other_insect",
    "bycatch_spider": "other_insect",
    "debris": "debris",
}
SOURCE_RANK = {"own": 0, "inat": 1, "ami": 2, "synth": 3}
INAT_PHOTO = re.compile(r"(?:inaturalist-open-data[^/]*/photos|static\.inaturalist\.org/photos)/(\d+)/")
MIN_SIDE = 100


def read_ami(data: Path) -> list[dict]:
    path = data / "ami" / "manifest.csv"
    if not path.exists():
        return []
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if r["status"] not in ("ok", "cached") or not r["local_path"]:
                continue
            m = INAT_PHOTO.search(r["source_url"])
            rows.append({"path": r["local_path"], "label": r["label"], "source": "ami",
                         "group": f"gbif:{r['gbif_occurrence']}", "inat_photo": m.group(1) if m else "",
                         "license": "", "credit": r["source_url"]})
    return rows


def read_inat(data: Path) -> list[dict]:
    path = data / "inat" / "manifest.csv"
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return [{"path": r["local_path"], "label": r["label"], "source": "inat",
                 "group": f"inat:{r['observation']}", "inat_photo": r["photo"],
                 "license": r["license"], "credit": r["attribution"]}
                for r in csv.DictReader(f) if r["status"] in ("ok", "cached") and r["local_path"]]


def read_own(data: Path) -> tuple[list[dict], set[str]]:
    root = data / "own"
    locked_file = root / "locked_test.txt"
    locked = {ln.strip() for ln in locked_file.read_text().splitlines() if ln.strip()} if locked_file.exists() else set()
    rows = []
    if root.exists():
        for img in sorted(root.glob("*/*/*")):
            if img.suffix.lower() not in (".jpg", ".jpeg", ".png"):
                continue
            label, card = img.parent.parent.name, img.parent.name
            if label not in CLASS_OF:
                print(f"  skipping {img}: unknown label folder {label!r}", file=sys.stderr)
                continue
            rows.append({"path": str(img), "label": label, "source": "own", "group": f"card:{card}",
                         "inat_photo": "", "license": "own", "credit": "Orchard Sentinel team"})
    return rows, locked


def read_synth(data: Path) -> list[dict]:
    path = data / "synth" / "manifest.csv"
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return [{"path": r["path"], "label": r["label"], "source": "synth", "source_path": r["source_path"],
                 # bare-liner debris has no source photo: each crop is its own group
                 "group": "" if r["source_path"] else f"liner:{Path(r['path']).stem}",
                 "inat_photo": "", "license": "derived", "credit": r["source_path"] or r["liner"]}
                for r in csv.DictReader(f)]


def dhash(path: str) -> np.ndarray | None:
    """256-bit difference hash as 4 uint64 words. 64 bits is too coarse here: most photos are
    one moth centred on a plain background, and those collide at 8x8."""
    try:
        with Image.open(path) as im:
            if min(im.size) < MIN_SIDE:
                return None
            g = np.asarray(ImageOps.exif_transpose(im).convert("L").resize((17, 16), Image.BILINEAR), dtype=np.int16)
    except Exception:
        return None
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return np.packbits(bits).view(">u8").astype(np.uint64)


def near_duplicates(hashes: np.ndarray, max_bits: int) -> list[tuple[int, int]]:
    """All (i, j), i < j, whose hashes differ in <= max_bits bits. Chunked so memory stays small."""
    pairs = []
    for start in range(0, len(hashes), 512):
        block = hashes[start:start + 512, None, :] ^ hashes[None, :, :]
        dist = np.bitwise_count(block).sum(axis=-1)
        for a, b in zip(*np.nonzero(dist <= max_bits)):
            i, j = start + int(a), int(b)
            if i < j:
                pairs.append((i, j))
    return pairs


def same_picture(a: str, b: str, min_corr: float = 0.95) -> bool:
    """Confirm a hash match: correlation of 64x64 grayscale thumbnails."""
    def thumb(p):
        with Image.open(p) as im:
            t = np.asarray(ImageOps.exif_transpose(im).convert("L").resize((64, 64), Image.BILINEAR), dtype=np.float32).ravel()
        return (t - t.mean()) / (t.std() + 1e-6)
    return float(np.mean(thumb(a) * thumb(b))) >= min_corr


def split_of(group: str, seed: int, val: float, test: float) -> str:
    u = int(hashlib.sha1(f"{seed}:{group}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "test" if u < test else "val" if u < test + val else "train"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data"))
    ap.add_argument("--val", type=float, default=0.15)
    ap.add_argument("--test", type=float, default=0.15)
    ap.add_argument("--max-bits", type=int, default=10, help="near-duplicate threshold (of 256)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    ami, inat, synth = read_ami(args.data), read_inat(args.data), read_synth(args.data)
    own, locked = read_own(args.data)
    inat_ids = {r["inat_photo"] for r in inat}
    ami_kept = [r for r in ami if not (r["inat_photo"] and r["inat_photo"] in inat_ids)]
    print(f"Sources: own {len(own)}, iNat {len(inat)}, AMI {len(ami)} "
          f"({len(ami) - len(ami_kept)} AMI photos already in the iNat download), trap-style synthetic {len(synth)}")

    rows = sorted(own + inat + ami_kept, key=lambda r: SOURCE_RANK[r["source"]])
    for r in rows:
        r["dhash"] = dhash(r["path"])
    bad = [r for r in rows if r["dhash"] is None]
    rows = [r for r in rows if r["dhash"] is not None]
    if bad:
        print(f"Dropped {len(bad)} unreadable or tiny (<{MIN_SIDE} px) images")

    hashes = np.stack([r["dhash"] for r in rows]) if rows else np.zeros((0, 4), np.uint64)
    drop, conflicts = set(), []
    for i, j in near_duplicates(hashes, args.max_bits):
        if not same_picture(rows[i]["path"], rows[j]["path"]):
            continue
        if CLASS_OF[rows[i]["label"]] == CLASS_OF[rows[j]["label"]]:
            drop.add(j)  # rows are sorted by source preference, so i is the one to keep
        elif rows[i]["source"] != "own" or rows[j]["source"] != "own":
            drop |= {i, j}
            conflicts.append((rows[i]["path"], rows[i]["label"], rows[j]["path"], rows[j]["label"]))
    rows = [r for k, r in enumerate(rows) if k not in drop]
    print(f"Dropped {len(drop)} near-duplicates ({len(conflicts)} pairs with conflicting labels)")
    for c in conflicts[:10]:
        print(f"  conflict: {c[0]} ({c[1]})  vs  {c[2]} ({c[3]})")

    # Groups can contain several photos; a group that spans labels (rare) goes to the first label's split.
    for r in rows:
        r["class"] = CLASS_OF[r["label"]]
        card = r["group"].removeprefix("card:")
        r["split"] = "locked" if r["source"] == "own" and card in locked else split_of(r["group"], args.seed, args.val, args.test)

    # Synthetic photos follow their source photo; those whose source was dropped go too.
    kept = {r["path"]: r for r in rows}
    n_synth = len(synth)
    synth = [s for s in synth if not s["source_path"] or s["source_path"] in kept]
    for s in synth:
        src = kept.get(s["source_path"])
        s["group"] = src["group"] if src else s["group"]
        s["class"] = CLASS_OF[s["label"]]
        s["split"] = src["split"] if src else split_of(s["group"], args.seed, args.val, args.test)
    if n_synth:
        print(f"Kept {len(synth)}/{n_synth} synthetic photos (the rest came from dropped photos)")
    rows += synth

    out = args.data / "dataset.csv"
    fields = ["path", "label", "class", "source", "group", "split", "license", "credit", "dhash"]
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            h = r.get("dhash")
            w.writerow({**r, "dhash": "".join(f"{int(x):016x}" for x in h) if h is not None else ""})

    table: dict[tuple[str, str], Counter] = defaultdict(Counter)
    groups: dict[tuple[str, str], set] = defaultdict(set)
    for r in rows:
        key = (r["label"], "trap-style" if r["source"] == "synth" else "photos")
        table[key][r["split"]] += 1
        groups[key].add(r["group"])
    print(f"\n{'label':16} {'class':11} {'kind':10} {'train':>6} {'val':>5} {'test':>5} {'locked':>6}  groups")
    for key in sorted(table, key=lambda k: (CLASS_OF[k[0]], k)):
        c = table[key]
        print(f"{key[0]:16} {CLASS_OF[key[0]]:11} {key[1]:10} {c['train']:6} {c['val']:5} {c['test']:5} {c['locked']:6}"
              f"  {len(groups[key])}")
    print(f"\nWrote {len(rows)} rows to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
