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
the collections, so it takes no space; copy it elsewhere with `cp -RL`. Photos whose species nobody has
confirmed (iNaturalist needs_id and casual) go in <label>/unconfirmed/. manifest.csv has one row per photo:
every collection and source it was found in, licence, attribution, record link and life stage.

Training doesn't read this folder; it's for looking at, and for picking from.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import sys
from collections import Counter
from pathlib import Path

import paths

SPECIES = ["CM", "OFM", "OBLR", "lookalike_RBLR", "lookalike_LAW"]
UNCONFIRMED = {"inat_needs_id", "inat_casual"}
FIELDS = ["label", "confirmed", "file", "source", "found_in", "license", "attribution", "record_url",
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=paths.DATA)
    args = ap.parse_args(argv)
    data = args.data.resolve()
    out = data / paths.ALL_SPECIES

    photos = gather(data)
    groups = group(photos)
    if out.exists():  # only ever links and our manifest in here, so a rebuild starts clean
        for f in out.rglob("*"):
            if f.is_symlink() or f.name == "manifest.csv":
                f.unlink()
    rows, table = [], Counter()
    for copies in groups:
        keep, info = best(copies)
        confirmed = any(p["confirmed"] for p in copies)
        label = keep["label"]
        folder = out / label if confirmed else out / label / "unconfirmed"
        folder.mkdir(parents=True, exist_ok=True)
        source = keep.get("source", keep["collection"])
        name = f"{source}_{keep.get('photo') or keep['path'].stem}{keep['path'].suffix}"
        link = folder / re.sub(r"[^\w.-]", "_", name)
        os.symlink(os.path.relpath(keep["path"], folder), link)
        found_in = sorted({f"{p['collection']}/{p.get('source', '')}".rstrip("/") for p in copies})
        rows.append({
            "label": label, "confirmed": "yes" if confirmed else "no", "file": str(link.relative_to(out)),
            "source": source, "found_in": "; ".join(found_in), "license": info.get("license", ""),
            "attribution": info.get("attribution", ""), "record_url": info.get("record_url", ""),
            "life_stage": info.get("life_stage", ""), "source_url": keep.get("source_url", ""),
            "target": str(keep["path"]),
        })
        table[(label, confirmed)] += 1
    rows.sort(key=lambda r: (SPECIES.index(r["label"]), r["confirmed"] == "no", r["file"]))
    with open(out / "manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    print(f"{len(photos)} photo files in the three collections -> {len(rows)} different photos")
    print(f"  {'':16}{'confirmed':>10}{'unconfirmed':>12}")
    for label in SPECIES:
        print(f"  {label:16}{table[(label, True)]:>10,}{table[(label, False)]:>12,}")
    print(f"Written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
