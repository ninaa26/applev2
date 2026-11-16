"""Pull research-grade, Creative Commons photos of our moths from iNaturalist.

    python fetch_inat.py --out data/web_moth_photos/inaturalist                 # all classes (our five moths uncapped)
    python fetch_inat.py --out data/web_moth_photos/inaturalist --dry-run       # counts only
    python fetch_inat.py --out data/web_moth_photos/inaturalist --only OFM      # one class

Only research-grade observations (two or more people agree on the species) with a CC
photo licence. Observations annotated as egg, larva or pupa are skipped; unannotated
ones are kept, since most moth photos are adults. Our five moths have no cap: every photo
of every observation. The other classes are capped (uncapped they would be ~500,000 photos).
A photo already in the reference library (fetch_reference.py) is hard-linked from there,
not downloaded again.

The bycatch_* labels are New York flies, parasitoid wasps, beetles, lacewings, leafhoppers and
spiders: insects that land on the liner but aren't moths.

iNaturalist lists OFM as *Aspila molesta* and lesser appleworm as *Aspila prunivora*.
manifest.csv records each photo's licence and attribution for the report's credits.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import paths

API = "https://api.inaturalist.org/v1/observations"
UA = {"User-Agent": "orchard-sentinel-capstone/0.1 (educational research)"}
LICENSES = "cc0,cc-by,cc-by-nc,cc-by-sa,cc-by-nc-sa,cc-by-nd,cc-by-nc-nd"
# Life stage: annotated adults, plus observations nobody annotated (mostly adults for moths).
# `without_term_value_id` alone is ignored by the API, so we run both queries and merge.
LIFE_STAGE = ({"term_id": 1, "term_value_id": 2}, {"without_term_id": 1})
NEW_YORK = 48

# label -> (query, cap (None: every photo), all photos per observation?)
# Our five moths have no cap since Nov 9 2026: every research-grade CC photo. Before, CM and OBLR stopped at
# 2,000 photos and RBLR at 1,500, one photo per observation.
CLASSES = {
    "CM": ({"taxon_id": 47153}, None, True),               # Cydia pomonella
    "OFM": ({"taxon_id": 1507298}, None, True),            # Aspila (Grapholita) molesta
    "OBLR": ({"taxon_id": 143728}, None, True),            # Choristoneura rosaceana
    "lookalike_LAW": ({"taxon_id": 1507295}, None, True),     # Aspila (Grapholita) prunivora
    "lookalike_RBLR": ({"taxon_id": 208118}, None, True),     # Argyrotaenia velutinana
    # Other tortricids photographed in New York: the moths most likely to be confused with ours.
    # Spread across species (PER_SPECIES), not the newest observations, which were mostly a few common species.
    "other_tortricid": ({"taxon_id": 47155, "place_id": NEW_YORK,
                         "without_taxon_id": "47153,1507298,143728,1507295,208118"}, None, False),
    # Non-moth bycatch in New York (flies, wasps/bees, beetles, true bugs): class other_insect, so
    # an insect that isn't a moth doesn't get counted as one.
    "other_insect": ({"taxon_id": "47822,47201,47208,47744", "place_id": NEW_YORK}, 1200, False),
    # Non-moth bycatch that ends up on delta-trap liners, as negatives for the other_insect class
    # (Hong et al. 2020 and Mamdouh & Khattab 2021 added non-target insects the same way).
    "bycatch_fly": ({"taxon_id": 47822, "place_id": NEW_YORK}, 300, False),         # Diptera
    "bycatch_wasp": ({"taxon_id": 47200, "place_id": NEW_YORK}, 300, False),        # Ichneumonoidea (parasitoid wasps)
    "bycatch_beetle": ({"taxon_id": 47208, "place_id": NEW_YORK}, 300, False),      # Coleoptera
    "bycatch_lacewing": ({"taxon_id": 48763, "place_id": NEW_YORK}, 300, False),    # Neuroptera
    "bycatch_leafhopper": ({"taxon_id": 53237, "place_id": NEW_YORK}, 300, False),  # Cicadellidae
    "bycatch_spider": ({"taxon_id": 47118, "place_id": NEW_YORK}, 300, False),      # Araneae
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


# label -> photos per species: the class is every species in its query, up to this many photos of each, so the
# head sees many kinds of look-alike (Nov 9 2026: 364 tortricid species in New York; before, the newest 1,500
# observations, a quarter of them from 4 species).
PER_SPECIES = {"other_tortricid": 25}
SPECIES_COUNTS = "https://api.inaturalist.org/v1/observations/species_counts"


def species_in(q: dict) -> list[tuple[int, str, int]]:
    """(taxon id, name, research-grade CC observations) for every species the query covers."""
    params = {k: v for k, v in q.items() if k != "without_taxon_id"}
    params.update(quality_grade="research", photo_license=LICENSES, per_page=500)
    skip = {int(t) for t in str(q.get("without_taxon_id", "")).split(",") if t}
    out, page = [], 1
    while True:
        d = get_json(f"{SPECIES_COUNTS}?{urllib.parse.urlencode({**params, 'page': page})}")
        out += [(r["taxon"]["id"], r["taxon"]["name"], r["count"]) for r in d["results"] if r["taxon"]["id"] not in skip]
        if page * 500 >= d["total_results"]:
            return out
        page += 1
        time.sleep(1.0)


def list_class(label: str, q: dict, cap: int | None, all_photos: bool) -> list[dict]:
    if label not in PER_SPECIES:
        return list_photos(label, q, cap, all_photos)
    rows = []
    for taxon, _name, _n in species_in(q):
        sq = {k: v for k, v in q.items() if k != "without_taxon_id"} | {"taxon_id": taxon}
        rows += list_photos(label, sq, PER_SPECIES[label], all_photos)
    return rows


def list_photos(label: str, q: dict, cap: int | None, all_photos: bool) -> list[dict]:
    """Page through observations newest-first with id_below (the API caps plain paging at 10k)."""
    rows, seen = [], set()
    for stage in LIFE_STAGE:
        id_below = None
        while cap is None or len(rows) < cap:
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
    have = out.parent / "reference" / row["label"] / "inat" / f"{row['photo']}.jpg"  # same 'medium' file
    if have.exists() and have.stat().st_size > 0:
        try:
            os.link(have, dest)
            return "linked"
        except OSError:
            pass
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
    ap.add_argument("--out", type=Path, default=paths.DATA / paths.INAT)
    ap.add_argument("--only", nargs="*", choices=list(CLASSES), help="fetch just these classes")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    labels = args.only or list(CLASSES)
    if args.dry_run:
        for label in labels:
            q, cap, _ = CLASSES[label]
            if label in PER_SPECIES:
                sp = species_in(q)
                n = sum(min(c, PER_SPECIES[label]) for _, _, c in sp)
                print(f"  {label:16} {len(sp)} species, about {n} photos at {PER_SPECIES[label]} per species")
                continue
            n = 0
            for stage in LIFE_STAGE:
                n += get_json(query_url(q, **stage, per_page=0))["total_results"]
                time.sleep(1.0)
            print(f"  {label:16} {n:6} observations (cap {cap})")
        return 0

    rows: list[dict] = []
    for label in labels:
        q, cap, all_photos = CLASSES[label]
        found = list_class(label, q, cap, all_photos)
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
