"""Every web photo we have of each of our five moths, in one folder per species.

    python compile_species.py          # (re)builds data/web_moth_photos/all_by_species/

Gathers the photos from all three web collections: reference/ (fetch_reference.py: iNaturalist, Bugwood,
GBIF, iDigBio, Commons, Ecdysis, ADW, Europeana), inaturalist/ (fetch_inat.py) and ami_gbif/ (fetch_ami.py).
The same photo often sits in two or three of them (AMI's and our iNaturalist set overlap the reference
library), so each photo is listed once:
  - same iNaturalist photo number, or the same link (http/https, :443, Symbiota's _lg/_tn sizes and SCAN's
    old address all count as one), or the same bytes = the same photo
  - of its copies, the largest file is kept (AMI's iNaturalist originals beat the 500 px copies)

Writes data/web_moth_photos/all_by_species/<label>/<source>_<id>.<ext>, links (not copies) to the files in
the collections, so it takes no space; copy it elsewhere with `cp -RL`. Confirmed photos only: a photo whose
species nobody has confirmed (iNaturalist needs_id and casual, and nowhere else) is left out; those stay in
reference/<label>/inat_needs_id/ and inat_casual/. manifest.csv has one row per photo: every collection and
source it was found in, licence, attribution, record link and life stage.

Also other_moth/, the look-alikes, in one folder: a sample of each species (7 photos per species from each
source by default, the same ones on every rebuild) of inaturalist/'s other_tortricid (New York tortricids,
fetch_inat.py) and ami_gbif/'s other_moth (common northeastern moths, fetch_ami.py). Both are `other_moth` to
the classifier. The manifest's `taxon` names each one's species and `source` says which set it came from.

Then near-duplicates are removed: the same picture resized or re-encoded (BOLD's old and new image hosts, a
Commons copy of an iNaturalist photo, consecutive near-identical shots). Same check as build_dataset.py: a
256-bit difference hash within 10 bits, confirmed by 64x64 thumbnails. Of each group the largest image stays.
If one picture is under two labels, every copy goes, since one label is wrong. removed_duplicates.csv lists
each removed photo, why, and the one kept.

Training doesn't read this folder; it's for looking at, and for picking from.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

import numpy as np
import paths
from build_dataset import dhash, same_picture
from PIL import Image

SPECIES = ["CM", "OFM", "OBLR", "lookalike_RBLR", "lookalike_LAW"]
UNCONFIRMED = {"inat_needs_id", "inat_casual"}
LOOKALIKES = ["other_moth"]  # other tortricids (iNaturalist) and other moths (AMI), sampled per species
FIELDS = ["label", "taxon", "file", "source", "found_in", "license", "attribution", "record_url",
          "life_stage", "source_url", "target"]


def photo_key(url: str) -> str:
    """One name per photo, whatever copy or size of it a collection linked."""
    m = re.search(r"inaturalist[^/]*/photos/(\d+)/", url)
    if m:
        return f"inat:{m.group(1)}"
    u = re.sub(r"^https?://", "", url.lower()).replace(":443/", "/")
    u = u.replace("scan-bugs.org/imglib/scan/", "media01.symbiota.org/media/scan/")
    return re.sub(r"_(?:lg|tn)(\.\w+)$", r"\1", u)


def sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes(), usedforsecurity=False).hexdigest()


def resolve(local_path: str, ml_dir: Path) -> Path | None:
    if not local_path:
        return None
    p = Path(local_path)
    p = p if p.is_absolute() else ml_dir / p
    return p if p.exists() and p.stat().st_size > 0 else None


def read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def gather(data: Path) -> list[dict]:
    """Every photo file of our species in the three collections, as one kind of row."""
    ml_dir = data.parent
    photos = []
    for r in read(data / paths.REFERENCE / "manifest.csv"):
        f = resolve(r.get("local_path", ""), ml_dir)
        if f and r["label"] in SPECIES:
            photos.append({**r, "collection": "reference", "path": f})
    for r in read(data / paths.INAT / "manifest.csv"):
        f = resolve(r.get("local_path", ""), ml_dir)
        if f and r["label"] in SPECIES:
            photos.append({**r, "collection": "inaturalist", "source": "inat", "record": r["observation"],
                           "record_url": f"https://www.inaturalist.org/observations/{r['observation']}",
                           "path": f})
    for r in read(data / paths.AMI / "manifest.csv"):
        f = resolve(r.get("local_path", ""), ml_dir)
        if f and r["label"] in SPECIES:
            photos.append({**r, "collection": "ami_gbif", "source": "ami", "photo": r["gbif_occurrence"],
                           "record_url": f"https://www.gbif.org/occurrence/{r['gbif_occurrence']}",
                           "path": f})
    for p in photos:
        p["confirmed"] = p.get("source") not in UNCONFIRMED
    return photos


def group(photos: list[dict]) -> list[list[dict]]:
    """Union the copies of one photo: same key from its link, or same bytes."""
    parent = list(range(len(photos)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union_by(keyf) -> None:
        first: dict[tuple, int] = {}
        for i, p in enumerate(photos):
            k = (p["label"], keyf(p))
            if k[1]:
                if k in first:
                    parent[find(i)] = find(first[k])
                else:
                    first[k] = i

    union_by(lambda p: photo_key(p.get("source_url", "")))
    union_by(lambda p: p.get("sha1") or sha1(p["path"]))
    groups: dict[int, list[dict]] = {}
    for i, p in enumerate(photos):
        groups.setdefault(find(i), []).append(p)
    return list(groups.values())


def best(copies: list[dict]) -> tuple[dict, dict]:
    """The largest file, and the best-documented row for licence and links (reference rows have the most)."""
    keep = max(copies, key=lambda p: p["path"].stat().st_size)
    info = next((p for p in copies if p["collection"] == "reference" and p.get("license")), None)
    info = info or next((p for p in copies if p.get("license")), keep)
    return keep, info


def gbif_names(keys: set[str], cache: Path) -> dict[str, str]:
    """GBIF species key -> scientific name (AMI's rows only have the key), cached next to AMI's metadata."""
    names = json.loads(cache.read_text()) if cache.exists() else {}
    for k in sorted(keys - names.keys()):
        try:
            req = urllib.request.Request(f"https://api.gbif.org/v1/species/{k}",
                                         headers={"User-Agent": "orchard-sentinel-capstone/0.1 (educational research)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                names[k] = json.load(r).get("canonicalName", "")
        except Exception:
            names[k] = ""
        time.sleep(0.1)
    cache.write_text(json.dumps(names, indent=0, sort_keys=True))
    return names


def lookalike_rows(data: Path, per_species: int) -> list[dict]:
    """Up to `per_species` photos of each species from each of other_tortricid (iNaturalist) and other_moth
    (AMI), all labelled other_moth. A photo listed twice in a manifest is taken once."""
    ml_dir = data.parent
    found: list[dict] = []
    for r in read(data / paths.INAT / "manifest.csv"):
        f = resolve(r.get("local_path", ""), ml_dir)
        if f and r["label"] == "other_tortricid":
            found.append({"label": "other_moth", "taxon": r["taxon"], "source": "inat", "photo": r["photo"],
                          "license": r["license"], "attribution": r["attribution"], "source_url": r["source_url"],
                          "record_url": f"https://www.inaturalist.org/observations/{r['observation']}", "path": f})
    ami = [r for r in read(data / paths.AMI / "manifest.csv") if r["label"] == "other_moth"]
    names = gbif_names({r["species_key"] for r in ami}, data / paths.AMI / "_metadata" / "species_names.json")
    for r in ami:
        f = resolve(r.get("local_path", ""), ml_dir)
        if f:
            found.append({"label": "other_moth", "taxon": names.get(r["species_key"]) or r["species_key"],
                          "source": "ami", "photo": r["gbif_occurrence"], "license": "", "attribution": "",
                          "source_url": r["source_url"], "path": f,
                          "record_url": f"https://www.gbif.org/occurrence/{r['gbif_occurrence']}"})
    by_species: dict[tuple, dict[str, dict]] = {}
    for p in found:  # keyed by photo, so a repeated manifest row counts once
        by_species.setdefault((p["source"], p["taxon"]), {})[str(p["photo"])] = p
    picked = []
    for (source, taxon), by_photo in sorted(by_species.items()):
        ps = [by_photo[k] for k in sorted(by_photo)]
        random.Random(f"{source}:{taxon}").shuffle(ps)  # the same sample on every rebuild
        picked += ps[:per_species]
    return picked


def near_pairs(hashes: np.ndarray, max_bits: int, block: int = 256) -> list[tuple[int, int]]:
    """All (i, j), i < j, whose hashes differ in <= max_bits bits; small blocks keep memory under ~400 MB."""
    pairs = []
    for start in range(0, len(hashes), block):
        dist = np.bitwise_count(hashes[start:start + block, None, :] ^ hashes[None, :, :]).sum(axis=-1)
        for a, b in zip(*np.nonzero(dist <= max_bits)):
            i, j = start + int(a), int(b)
            if i < j:
                pairs.append((i, j))
    return pairs


def remove_near_duplicates(rows: list[dict], out: Path, max_bits: int) -> list[dict]:
    """Drop near-identical pictures (see the module docstring); returns what was removed."""
    cache_file = out / ".dhash_cache.json"  # hashing 45,000 photos takes minutes; keyed by file, size, mtime
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    hashes, usable = [], []
    for i, r in enumerate(rows):
        st = Path(r["target"]).stat()
        key = f"{r['target']}|{st.st_size}|{int(st.st_mtime)}"
        if key not in cache:
            h = dhash(r["target"])
            cache[key] = "".join(f"{int(x):016x}" for x in h) if h is not None else ""
        if cache[key]:
            hashes.append([int(cache[key][k:k + 16], 16) for k in range(0, 64, 16)])
            usable.append(i)
    cache_file.write_text(json.dumps(cache))
    H = np.array(hashes, dtype=np.uint64)

    parent = {i: i for i in usable}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in near_pairs(H, max_bits):
        i, j = usable[a], usable[b]
        if find(i) != find(j) and same_picture(rows[i]["target"], rows[j]["target"]):
            parent[find(j)] = find(i)
    groups: dict[int, list[int]] = {}
    for i in usable:
        groups.setdefault(find(i), []).append(i)

    def area(i: int) -> int:
        with Image.open(rows[i]["target"]) as im:
            return im.size[0] * im.size[1]

    removed = []
    for members in groups.values():
        if len(members) < 2:
            continue
        labels = {rows[i]["label"] for i in members}
        if len(labels) > 1:
            for i in members:
                removed.append({**rows[i], "why": "same picture under " + " and ".join(sorted(labels)), "kept": ""})
            continue
        keep = max(members, key=lambda i: (area(i), Path(rows[i]["target"]).stat().st_size))
        for i in members:
            if i != keep:
                removed.append({**rows[i], "why": "near-duplicate", "kept": rows[keep]["file"]})
    for r in removed:
        (out / r["file"]).unlink(missing_ok=True)
    return removed


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=paths.DATA)
    ap.add_argument("--max-bits", type=int, default=10, help="near-duplicate threshold (of 256 bits)")
    ap.add_argument("--per-lookalike-species", type=int, default=7,
                    help="photos of each species in other_tortricid and other_moth (0: leave those out)")
    args = ap.parse_args(argv)
    data = args.data.resolve()
    out = data / paths.ALL_SPECIES

    photos = gather(data)
    groups = group(photos)
    if out.exists():  # only ever links and our manifest in here, so a rebuild starts clean
        for f in out.rglob("*"):
            if f.is_symlink() or f.name in ("manifest.csv", "removed_duplicates.csv"):
                f.unlink()
        for d in sorted((d for d in out.rglob("*") if d.is_dir()), reverse=True):
            if not any(d.iterdir()):
                d.rmdir()
    rows, kept, left_out = [], Counter(), Counter()
    for copies in groups:
        label = copies[0]["label"]
        copies = [p for p in copies if p["confirmed"]]  # an unconfirmed copy never decides which file is kept
        if not copies:
            left_out[label] += 1
            continue
        keep, info = best(copies)
        folder = out / label
        folder.mkdir(parents=True, exist_ok=True)
        source = keep.get("source", keep["collection"])
        name = f"{source}_{keep.get('photo') or keep['path'].stem}{keep['path'].suffix}"
        link = folder / re.sub(r"[^\w.-]", "_", name)
        os.symlink(os.path.relpath(keep["path"], folder), link)
        found_in = sorted({f"{p['collection']}/{p.get('source', '')}".rstrip("/") for p in copies})
        rows.append({
            "label": label, "taxon": keep.get("taxon", ""), "file": str(link.relative_to(out)),
            "source": source, "found_in": "; ".join(found_in), "license": info.get("license", ""),
            "attribution": info.get("attribution", ""), "record_url": info.get("record_url", ""),
            "life_stage": info.get("life_stage", ""), "source_url": keep.get("source_url", ""),
            "target": str(keep["path"]),
        })
        kept[label] += 1
    look = lookalike_rows(data, args.per_lookalike_species) if args.per_lookalike_species else []
    for p in look:
        folder = out / p["label"]
        folder.mkdir(parents=True, exist_ok=True)
        link = folder / re.sub(r"[^\w.-]", "_", f"{p['source']}_{p['photo']}{p['path'].suffix}")
        os.symlink(os.path.relpath(p["path"], folder), link)
        rows.append({"label": p["label"], "taxon": p["taxon"], "file": str(link.relative_to(out)),
                     "source": p["source"], "found_in": "inaturalist/other_tortricid" if p["source"] == "inat"
                     else "ami_gbif/other_moth", "license": p["license"], "attribution": p["attribution"],
                     "record_url": p["record_url"], "life_stage": "", "source_url": p["source_url"],
                     "target": str(p["path"])})
    order = SPECIES + LOOKALIKES
    rows.sort(key=lambda r: (order.index(r["label"]), r["taxon"], r["file"]))
    removed = remove_near_duplicates(rows, out, args.max_bits)
    gone = {r["file"] for r in removed}
    rows = [r for r in rows if r["file"] not in gone]
    with open(out / "removed_duplicates.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["label", "file", "why", "kept", "source", "found_in", "record_url",
                                          "target"], extrasaction="ignore")
        w.writeheader()
        w.writerows(removed)
    with open(out / "manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"{len(photos)} photo files in the three collections -> {len(rows)} different confirmed photos")
    print(f"  {'':16}{'in folder':>10}{'unconfirmed, left out':>23}")
    for label in SPECIES:
        print(f"  {label:16}{kept[label]:>10,}{left_out[label]:>23,}")
    for source, what in (("inat", "New York tortricids"), ("ami", "northeastern moths")):
        sample = [p for p in look if p["source"] == source]
        print(f"  {'other_moth':16}{len(sample):>10,}   {what} ({source}): {len({p['taxon'] for p in sample})} "
              f"species, up to {args.per_lookalike_species} each")
    by = Counter((r["label"], r["why"] == "near-duplicate") for r in removed)
    print(f"Removed {len(removed)} near-duplicates: " + ", ".join(
        f"{label} {by[(label, True)]}" for label in order if by[(label, True)]) +
        f"; {sum(v for (_, d), v in by.items() if not d)} photos whose picture is under two labels "
        "(removed_duplicates.csv)")
    final = Counter(r["label"] for r in rows)
    print("In the folder now: " + ", ".join(f"{label} {final[label]:,}" for label in order))
    print(f"Written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
