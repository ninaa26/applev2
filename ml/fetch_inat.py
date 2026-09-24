"""Pull research-grade, Creative Commons photos of our moths from iNaturalist.

    python fetch_inat.py --out data/inat                 # all classes, default caps
    python fetch_inat.py --out data/inat --dry-run       # counts only
    python fetch_inat.py --out data/inat --only OFM      # one class

Only research-grade observations (two or more people agree on the species) with a CC
photo licence. Observations annotated as egg, larva or pupa are skipped; unannotated
ones are kept, since most moth photos are adults. OFM and lesser appleworm are scarce,
so every photo of every observation is kept; the common species get one photo per
observation, which gives more distinct moths for the same download.

iNaturalist lists OFM as *Aspila molesta* and lesser appleworm as *Aspila prunivora*.
manifest.csv records each photo's licence and attribution for the report's credits.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API = "https://api.inaturalist.org/v1/observations"
UA = {"User-Agent": "orchard-sentinel-capstone/0.1 (educational research)"}
LICENSES = "cc0,cc-by,cc-by-nc,cc-by-sa,cc-by-nc-sa,cc-by-nd,cc-by-nc-nd"
# Life stage: annotated adults, plus observations nobody annotated (mostly adults for moths).
# `without_term_value_id` alone is ignored by the API, so we run both queries and merge.
LIFE_STAGE = ({"term_id": 1, "term_value_id": 2}, {"without_term_id": 1})
NEW_YORK = 48

# label -> (query, cap, all photos per observation?)
CLASSES = {
    "CM": ({"taxon_id": 47153}, 2000, False),              # Cydia pomonella
    "OFM": ({"taxon_id": 1507298}, 10_000, True),          # Aspila (Grapholita) molesta
    "OBLR": ({"taxon_id": 143728}, 2000, False),           # Choristoneura rosaceana
    "lookalike_LAW": ({"taxon_id": 1507295}, 10_000, True),   # Aspila (Grapholita) prunivora
    "lookalike_RBLR": ({"taxon_id": 208118}, 1500, False),    # Argyrotaenia velutinana
    # Other tortricids photographed in New York: the moths most likely to be confused with ours.
    "other_tortricid": ({"taxon_id": 47155, "place_id": NEW_YORK,
                         "without_taxon_id": "47153,1507298,143728,1507295,208118"}, 1500, False),
}


def get_json(url: str, retries: int = 4) -> dict:
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(3 * (attempt + 1))
    raise RuntimeError("unreachable")


def query_url(q: dict, **extra) -> str:
    params = {"quality_grade": "research", "photo_license": LICENSES, "photos": "true",
              "order_by": "id", "order": "desc", **q, **extra}
    return f"{API}?{urllib.parse.urlencode(params)}"


def list_photos(label: str, q: dict, cap: int, all_photos: bool) -> list[dict]:
    """Page through observations newest-first with id_below (the API caps plain paging at 10k)."""
    rows, seen = [], set()
    for stage in LIFE_STAGE:
        id_below = None
        while len(rows) < cap:
            extra = {**stage, "per_page": 200, **({"id_below": id_below} if id_below else {})}
            results = get_json(query_url(q, **extra))["results"]
            if not results:
                break
            for obs in results:
                if obs["id"] in seen:
                    continue
                seen.add(obs["id"])
                photos = [p for p in obs["photos"] if p.get("license_code")]
                for p in photos if all_photos else photos[:1]:
                    rows.append({
                        "label": label,
                        "observation": obs["id"],
                        "photo": p["id"],
                        "taxon": (obs.get("taxon") or {}).get("name", ""),
                        "place": obs.get("place_guess") or "",
                        "license": p["license_code"],
                        "attribution": p.get("attribution", ""),
                        # CC photos live in the open-data bucket; 'medium' is 500 px on the long side.
                        "source_url": p["url"].replace("square.", "medium."),
                    })
            id_below = results[-1]["id"]
            time.sleep(1.0)  # iNat asks for ~1 request/second
    return rows[:cap]


def download(row: dict, out: Path, retries: int = 3) -> str:
    dest = out / row["label"] / f"{row['photo']}.jpg"
    row["local_path"] = str(dest)
    if dest.exists():
        return "cached"
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(row["source_url"], headers=UA), timeout=30) as r:
                dest.write_bytes(r.read())
            return "ok"
        except Exception as e:
            err = str(e)
            time.sleep(1.5 * (attempt + 1))
    row["local_path"] = ""
    return f"failed: {err[:80]}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("data/inat"))
    ap.add_argument("--only", nargs="*", choices=list(CLASSES), help="fetch just these classes")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    labels = args.only or list(CLASSES)
    if args.dry_run:
        for label in labels:
            q, cap, _ = CLASSES[label]
            n = 0
            for stage in LIFE_STAGE:
                n += get_json(query_url(q, **stage, per_page=0))["total_results"]
                time.sleep(1.0)
            print(f"  {label:16} {n:6} observations (cap {cap})")
        return 0

    rows: list[dict] = []
    for label in labels:
        q, cap, all_photos = CLASSES[label]
        found = list_photos(label, q, cap, all_photos)
        print(f"  {label:16} {len(found):5} photos from {len({r['observation'] for r in found})} observations")
        rows += found

    counts: dict[str, int] = {}
    with ThreadPoolExecutor(args.workers) as pool:
        for i, status in enumerate(pool.map(lambda r: download(r, args.out), rows), 1):
            rows[i - 1]["status"] = status
            key = status if not status.startswith("failed") else "failed"
            counts[key] = counts.get(key, 0) + 1
            if i % 500 == 0:
                print(f"  {i}/{len(rows)} {counts}", flush=True)

    # Merge with an existing manifest so --only runs don't drop other classes.
    manifest = args.out / "manifest.csv"
    fields = ["label", "observation", "photo", "taxon", "place", "license", "attribution", "source_url", "local_path", "status"]
    keep = []
    if manifest.exists():
        with open(manifest, newline="") as f:
            keep = [r for r in csv.DictReader(f) if r["label"] not in labels]
    with open(manifest, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(keep + rows)
    print(f"Done: {counts}. Manifest: {manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
