"""Pull our species' training photos from the AMI dataset without downloading its 16 GB zip.

The AMI Zenodo record (https://zenodo.org/records/12554005) is one Archive.zip.
The GBIF half contains only image *links*. This script reads the zip remotely
(HTTP range requests), extracts just the NE-America metadata CSVs, keeps rows
for the species we care about, and downloads those photos from their original
hosts into data/ami/<label>/.

    python fetch_ami.py --out data/ami                          # our 5 moths
    python fetch_ami.py --out data/ami --other-moths 80          # + 80 common NE moths as "other_moth"
    python fetch_ami.py --out data/ami --dry-run                 # counts only

Photos keep their original licences; manifest.csv records each image's source URL
so credits can be produced for the report.
"""

from __future__ import annotations

import argparse
import csv
import io
import random
import sys
import time
import urllib.request
import zipfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ZIP_URL = "https://zenodo.org/records/12554005/files/Archive.zip?download=1"
META = "ami_gbif/fine-grained_classification/metadata/"
SPLITS = {s: f"{META}01_ami-gbif_fine-grained_ne-america_{s}.csv" for s in ("train", "val", "test")}

# GBIF species keys (checked against AMI's taxonomy map, Sep 2026)
TARGETS = {
    "1737847": "CM",                 # Cydia pomonella
    "1736574": "OFM",                # Grapholita molesta (iNaturalist: Aspila molesta)
    "5102671": "OBLR",               # Choristoneura rosaceana
    "10457666": "lookalike_LAW",     # Grapholita prunivora, lesser appleworm
    "1747189": "lookalike_RBLR",     # Argyrotaenia velutinana, redbanded leafroller
}
UA = {"User-Agent": "orchard-sentinel-capstone/0.1 (educational research)"}


class HttpFile(io.RawIOBase):
    """Seekable read-only file over HTTP range requests, enough for zipfile."""

    def __init__(self, url: str):
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD", headers=UA)) as r:
            self.url, self.size = r.geturl(), int(r.headers["Content-Length"])
        self.pos = 0

    def readable(self): return True
    def seekable(self): return True
    def tell(self): return self.pos

    def seek(self, offset, whence=0):
        self.pos = offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset
        return self.pos

    def read(self, n=-1):
        if n < 0 or n > self.size - self.pos:
            n = self.size - self.pos
        if n <= 0:
            return b""
        req = urllib.request.Request(self.url, headers={**UA, "Range": f"bytes={self.pos}-{self.pos + n - 1}"})
        with urllib.request.urlopen(req) as r:
            data = r.read()
        self.pos += len(data)
        return data

    def readinto(self, b):
        data = self.read(len(b))
        b[: len(data)] = data
        return len(data)


def extract_metadata(cache: Path) -> dict[str, Path]:
    cache.mkdir(parents=True, exist_ok=True)
    wanted = {split: cache / Path(name).name for split, name in SPLITS.items()}
    if all(p.exists() for p in wanted.values()):
        return wanted
    print("Reading AMI Archive.zip index remotely (no full download)…")
    z = zipfile.ZipFile(io.BufferedReader(HttpFile(ZIP_URL), buffer_size=1 << 20))
    for split, name in SPLITS.items():
        if not wanted[split].exists():
            info = z.getinfo(name)
            print(f"  extracting {Path(name).name} ({info.file_size / 1e6:.0f} MB)")
            wanted[split].write_bytes(z.read(name))
    return wanted


def select_rows(csv_paths: dict[str, Path], other_moths: int, per_other: int, seed: int) -> list[dict]:
    rows, by_species = [], {}
    for split, path in csv_paths.items():
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                if r.get("lifeStage") not in ("", "Adult", None):
                    continue
                r["split"] = split
                key = r["speciesKey"]
                if key in TARGETS:
                    rows.append({**r, "label": TARGETS[key]})
                elif other_moths:
                    by_species.setdefault(key, []).append(r)
    if other_moths:
        rng = random.Random(seed)
        common = sorted(by_species, key=lambda k: len(by_species[k]), reverse=True)[:other_moths]
        for key in common:
            picks = by_species[key][:]
            rng.shuffle(picks)
            rows += [{**r, "label": "other_moth"} for r in picks[:per_other]]
    return rows


def download(row: dict, out: Path, retries: int = 3) -> tuple[str, str]:
    dest = out / row["label"] / f"{row['id']}.jpg"
    if dest.exists():
        return "cached", str(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(row["identifier"], headers=UA), timeout=30) as r:
                dest.write_bytes(r.read())
            return "ok", str(dest)
        except Exception as e:  # dead links are common in GBIF media; skip after retries
            err = str(e)
            time.sleep(1.5 * (attempt + 1))
    return f"failed: {err[:80]}", ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("data/ami"))
    ap.add_argument("--other-moths", type=int, default=0, help="also fetch the N most common other NE moths")
    ap.add_argument("--per-other", type=int, default=15, help="photos per 'other moth' species")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    csvs = extract_metadata(args.out / "_metadata")
    rows = select_rows(csvs, args.other_moths, args.per_other, args.seed)
    counts = Counter((r["label"], r["split"]) for r in rows)
    print("\nSelected photos (label / AMI split):")
    for label in sorted({l for l, _ in counts}):
        print(f"  {label:16} " + "  ".join(f"{s}={counts[(label, s)]}" for s in ("train", "val", "test")))
    if args.dry_run:
        return 0

    manifest = args.out / "manifest.csv"
    results = Counter()
    with ThreadPoolExecutor(args.workers) as pool, open(manifest, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["label", "ami_split", "gbif_occurrence", "species_key", "source_url", "local_path", "status"])
        for row, (status, path) in zip(rows, pool.map(lambda r: download(r, args.out), rows)):
            results[status.split(":")[0]] += 1
            w.writerow([row["label"], row["split"], row["id"], row["speciesKey"], row["identifier"], path, status])
    print(f"\nDone: {dict(results)}. Manifest with source URLs: {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
