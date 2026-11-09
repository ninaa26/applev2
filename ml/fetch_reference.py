"""Build a reference library of every openly licensed photo of our five moths we can find on the web.

    python fetch_reference.py                       # all five species, all sources
    python fetch_reference.py --only OFM lookalike_LAW --sources inat gbif
    python fetch_reference.py --dry-run             # counts per species and source, no downloads

Writes data/web_moth_photos/reference/<label>/<source>/<id>.jpg and one manifest.csv. This is a library to
look at and pick from, not a training set: build_dataset.py doesn't read it, so fetching more here doesn't
change what any model trains on. fetch_inat.py and fetch_ami.py are still what training uses.

Sources, best documented first (each photo keeps its licence and attribution in the manifest):
  inat           iNaturalist research grade (two or more people agree on the species), CC licences only,
                 every photo of every observation, all life stages (`life_stage` says which, when annotated)
  bugwood        Bugwood / insectimages.org: extension, USDA, university and INRA photos, including the USDA
                 TortAI identification tool's adults, larvae and damage. CC BY or CC BY-NC 3.0 per photo
  gbif           every other GBIF dataset with images: museum collections (MCZ Harvard, Albert J. Cook,
                 Delaware, UNH, Smithsonian...), Observation.org, iBOL barcode specimens (BOLD's photos reach
                 GBIF this way), BugGuide's GBIF share, national recording schemes. GBIF's copy of iNaturalist
                 is skipped (that's `inat`)
  idigbio        iDigBio, US museum specimens. Mostly the same photos as GBIF; links already fetched are skipped
  commons        Wikimedia Commons, the species category and its subcategories
  ecdysis        Ecdysis (ecdysis.org), the Symbiota portal for arthropod collections: imaged specimens from
                 MSU, the Mississippi Entomological Museum and others, CC0 or CC as each page says. Many are
                 also in GBIF; links already fetched are skipped
  adw            Animal Diversity Web (University of Michigan): Phil Myers' photos, CC BY-NC-SA
  europeana      Europeana: Naturalis specimens, old bulletins and plates (public domain or CC only)
  inat_needs_id  iNaturalist observations nobody has confirmed yet. The species is the uploader's guess
  inat_casual    iNaturalist casual grade: captive or reared moths, or observations missing a date or place.
                 Both of these are kept apart so nobody trains on them without looking

Looked at and not fetched (Nov 2026): BugGuide's own site, Moth Photographers Group, UKMoths, Lepiforum and
Pherobase (all rights reserved, no API); Flickr and Openverse (need an API key or an account); EOL (its image
API returns nothing now); BOLD (its v5 API has no image links; the photos come through GBIF); the Atlas of
Living Australia (its CM photos are iNaturalist Australia and GBIF datasets again).

SCAN (scan-bugs.org, e.g. Delaware's specimens) refuses scripted downloads, so its photo links, which GBIF and
iDigBio give, are fetched from Symbiota's media server (media01.symbiota.org), where the same files are and
where Ecdysis links SCAN photos. Anything that still fails goes in hand_download.csv.

Sizes: iNaturalist 'medium' (500 px long side), Bugwood 1536 px, Commons 1024 px, the rest as the host serves them. Exact duplicates
(same bytes, e.g. an iNaturalist photo also on Commons) are kept once per species, from the source listed
first; the manifest marks the rest `duplicate_of`. `--dedupe` reruns that over the whole manifest.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import paths

UA = {"User-Agent": "orchard-sentinel-capstone/0.1 (educational research)"}
INAT_API = "https://api.inaturalist.org/v1/observations"
GBIF_API = "https://api.gbif.org/v1/occurrence/search"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
BUGWOOD_API = "https://api.bugwood.org/rest/api/image/.json"
BUGWOOD_V2 = "https://api.bugwoodcloud.org/v2/image"
IDIGBIO_API = "https://search.idigbio.org/v2/search/media"
ADW = "https://animaldiversity.org"
ECDYSIS = "https://ecdysis.org/collections"
# SCAN (scan-bugs.org) refuses scripted downloads, but its photos are also on Symbiota's media server, where
# Ecdysis and SCAN's newer records link them. The path keeps its case there.
SCAN_IMGLIB = re.compile(r"^https?://scan-bugs\.org(?::443)?/imglib/scan/")
SYMBIOTA_MEDIA = "https://media01.symbiota.org/media/scan/"
EUROPEANA_API = "https://api.europeana.eu/record/v2/search.json"  # api2demo is Europeana's public demo key
OLD_NAMES = {"CM": ["Laspeyresia pomonella", "Carpocapsa pomonella"], "lookalike_LAW": ["Laspeyresia prunivora"]}
# Bugwood gives each image a `commercial` flag; checked against the licence its pages show (Nov 2026)
BUGWOOD_LICENSES = {1: "cc-by-nc-3.0-us", 2: "cc-by-3.0-us", 3: "cc-by-3.0-us"}
GBIF_INAT_DATASET = "50c9509d-22c7-4a22-a47d-8c48425ef4a7"
INAT_LICENSES = "cc0,cc-by,cc-by-nc,cc-by-sa,cc-by-nc-sa,cc-by-nd,cc-by-nc-nd"
SOURCES = ("inat", "bugwood", "gbif", "idigbio", "commons", "ecdysis", "adw", "europeana", "inat_needs_id", "inat_casual")
# iNaturalist annotation 1 (life stage): value ids
LIFE_STAGES = {2: "adult", 3: "teneral", 4: "pupa", 5: "nymph", 6: "larva", 7: "egg", 8: "juvenile"}

# label -> iNaturalist taxon, GBIF taxon key, Bugwood subject, Commons categories (names as each site files them),
# Animal Diversity Web account (None: no pictures). Checked Nov 2026.
SPECIES = {
    "CM": (47153, 1737847, 9000, ["Cydia pomonella"], "Cydia_pomonella"),  # codling moth
    "OFM": (1507298, 1736574, 9017, ["Grapholita molesta", "Aspila molesta"], None),  # oriental fruit moth
    "OBLR": (143728, 5102671, 8988, ["Choristoneura rosaceana"], "Choristoneura_rosaceana"),  # obliquebanded leafroller
    "lookalike_RBLR": (208118, 1747189, 8981, ["Argyrotaenia velutinana"], "Argyrotaenia_velutinana"),  # redbanded
    "lookalike_LAW": (1507295, 10457666, 9019, ["Grapholita prunivora", "Aspila prunivora"], None),  # lesser appleworm
}

FIELDS = ["label", "source", "record", "photo", "record_url", "taxon", "life_stage", "place", "country", "date",
          "license", "attribution", "source_url", "local_path", "sha1", "status", "duplicate_of"]


def get_json(url: str, retries: int = 5) -> dict:
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return json.load(r)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(4 * (attempt + 1))
    raise RuntimeError("unreachable")


# ---------- iNaturalist ----------

def inat_rows(label: str, taxon: int, grade: str, source: str, count_only: bool = False) -> list[dict] | int:
    base = {"taxon_id": taxon, "quality_grade": grade, "photo_license": INAT_LICENSES, "photos": "true",
            "order_by": "id", "order": "desc"}
    if count_only:
        return get_json(f"{INAT_API}?{urllib.parse.urlencode({**base, 'per_page': 0})}")["total_results"]
    rows, id_below = [], None
    while True:
        q = {**base, "per_page": 200, **({"id_below": id_below} if id_below else {})}
        results = get_json(f"{INAT_API}?{urllib.parse.urlencode(q)}")["results"]
        if not results:
            return rows
        for obs in results:
            stage = ""
            for a in obs.get("annotations") or []:
                if a.get("controlled_attribute_id") == 1:
                    stage = LIFE_STAGES.get(a.get("controlled_value_id"), "")
            for p in obs["photos"]:
                if not p.get("license_code"):
                    continue
                rows.append({
                    "label": label, "source": source, "record": obs["id"], "photo": p["id"],
                    "record_url": f"https://www.inaturalist.org/observations/{obs['id']}",
                    "taxon": (obs.get("taxon") or {}).get("name", ""), "life_stage": stage,
                    "place": obs.get("place_guess") or "", "country": "", "date": obs.get("observed_on") or "",
                    "license": p["license_code"], "attribution": p.get("attribution", ""),
                    "source_url": p["url"].replace("square.", "medium."),
                })
        id_below = results[-1]["id"]
        time.sleep(1.0)  # iNaturalist asks for about one request a second


# ---------- GBIF ----------

def gbif_license(url: str) -> str:
    """GBIF gives licences as URLs; shorten to cc-by-nc etc. Empty if not an open licence."""
    u = (url or "").lower()
    if "publicdomain" in u or "cc0" in u:
        return "cc0"
    m = re.search(r"licenses/([a-z-]+)/", u)
    if m:
        return "cc-" + m.group(1)
    m = re.match(r"cc[ _-]?(by(?:[ _-](?:nc|sa|nd))*)", u.replace("cc-", "cc "))
    return "cc-" + re.sub(r"[ _]", "-", m.group(1)) if m else ""


def gbif_rows(label: str, key: int, count_only: bool = False) -> list[dict] | int:
    """Page through each dataset but GBIF's copy of iNaturalist on its own: GBIF has no "not this dataset" filter,
    and paging past the iNaturalist records (1.9 MB per 300) is what made this slow."""
    base = {"taxonKey": key, "mediaType": "StillImage"}
    facets = get_json(f"{GBIF_API}?{urllib.parse.urlencode({**base, 'limit': 0, 'facet': 'datasetKey', 'facetLimit': 1000})}")
    datasets = {f["name"]: f["count"] for f in facets["facets"][0]["counts"]} if facets.get("facets") else {}
    datasets.pop(GBIF_INAT_DATASET, None)
    if count_only:
        return sum(datasets.values())
    rows = []
    for dataset, total in datasets.items():
        offset = 0
        while offset < total:
            q = {**base, "datasetKey": dataset, "limit": 100, "offset": offset}
            page = get_json(f"{GBIF_API}?{urllib.parse.urlencode(q)}")
            for occ in page["results"]:
                for i, m in enumerate(occ.get("media") or []):
                    lic = gbif_license(m.get("license") or occ.get("license", ""))
                    url = m.get("identifier", "")
                    if m.get("type") != "StillImage" or not url.startswith("http") or not lic:
                        continue
                    rows.append({
                        "label": label, "source": "gbif", "record": occ["key"], "photo": f"{occ['key']}_{i}",
                        "record_url": f"https://www.gbif.org/occurrence/{occ['key']}",
                        "taxon": occ.get("species") or occ.get("scientificName", ""),
                        "life_stage": (occ.get("lifeStage") or "").lower(),
                        "place": occ.get("locality") or occ.get("stateProvince") or "",
                        "country": occ.get("countryCode", ""), "date": (occ.get("eventDate") or "")[:10],
                        "license": lic,
                        "attribution": " / ".join(x for x in (m.get("rightsHolder") or m.get("creator"),
                                                              occ.get("institutionCode") or occ.get("datasetName"))
                                                  if x),
                        "source_url": url,
                    })
            offset += 100
            if page.get("endOfRecords"):
                break
    return rows


# ---------- Wikimedia Commons ----------

def commons_files(category: str, depth: int = 2, seen: set | None = None) -> list[str]:
    seen = seen if seen is not None else set()
    if category in seen:
        return []
    seen.add(category)
    files, cont = [], {}
    while True:
        q = {"action": "query", "list": "categorymembers", "cmtitle": f"Category:{category}", "cmlimit": 500,
             "cmtype": "file|subcat", "format": "json", **cont}
        r = get_json(f"{COMMONS_API}?{urllib.parse.urlencode(q)}")
        for m in r.get("query", {}).get("categorymembers", []):
            if m["ns"] == 6:
                files.append(m["title"])
            elif m["ns"] == 14 and depth > 0:
                files += commons_files(m["title"].split(":", 1)[1], depth - 1, seen)
        if "continue" not in r:
            return files
        cont = r["continue"]


def meta_text(meta: dict, key: str) -> str:
    """One Commons extmetadata field as plain text (they come as HTML)."""
    return re.sub(r"<[^>]+>", "", meta.get(key, {}).get("value", "")).strip()


def commons_rows(label: str, categories: list[str], count_only: bool = False) -> list[dict] | int:
    titles, seen = [], set()
    for c in categories:
        titles += [t for t in commons_files(c, seen=seen) if t not in titles]
    titles = [t for t in titles if re.search(r"\.(jpe?g|png|tiff?|webp)$", t, re.I)]
    if count_only:
        return len(titles)
    rows = []
    for i in range(0, len(titles), 50):
        q = {"action": "query", "titles": "|".join(titles[i:i + 50]), "prop": "imageinfo",
             "iiprop": "url|extmetadata", "iiurlwidth": 1024, "format": "json"}
        for page in get_json(f"{COMMONS_API}?{urllib.parse.urlencode(q)}")["query"]["pages"].values():
            info = (page.get("imageinfo") or [{}])[0]
            meta = info.get("extmetadata", {})
            lic = meta_text(meta, "LicenseShortName").lower().replace(" ", "-")
            if not info.get("thumburl") or not (lic.startswith("cc") or "public-domain" in lic or lic == "pd"):
                continue
            rows.append({
                "label": label, "source": "commons", "record": page["pageid"], "photo": page["pageid"],
                "record_url": info.get("descriptionurl", ""), "taxon": categories[0], "life_stage": "",
                "place": "", "country": "", "date": meta_text(meta, "DateTimeOriginal")[:10], "license": lic,
                "attribution": meta_text(meta, "Artist")[:200], "source_url": info["thumburl"],
            })
    return rows


# ---------- Bugwood (insectimages.org: extension, USDA and university photos, incl. USDA's TortAI) ----------

def bugwood_rows(label: str, subject: int, count_only: bool = False) -> list[dict] | int:
    listing = get_json(f"{BUGWOOD_API}?sub={subject}&rows=1000&fmt=json")
    if count_only:
        return listing["total"]
    rows = []
    for r in listing["rows"]:
        num = r["imgnum"]
        info = get_json(f"{BUGWOOD_V2}/{num}")  # the licence flag, descriptor and date are only here
        lic = BUGWOOD_LICENSES.get(info.get("commercial"), "")
        if not lic:
            continue
        stage = (info.get("descriptorname") or "").lower()
        size = "1536x1024" if (info.get("maxresolution") or 0) >= 5 else "768x512"
        rows.append({
            "label": label, "source": "bugwood", "record": num, "photo": num,
            "record_url": f"https://www.insectimages.org/browse/image/{num}", "taxon": r.get("scientificName", ""),
            "life_stage": stage, "place": info.get("imagetype") or "", "country": "",
            "date": (info.get("dateacquired") or "")[:10], "license": lic,
            "attribution": (info.get("citation") or "").strip(),
            # maxresolution 5 is published at 1536 px; lower ones only up to 768 px (1536 gives 403)
            "source_url": f"https://bugwoodcloud.org/images/{size}/{num}.jpg",
        })
    return rows


# ---------- iDigBio (US museum specimens; mostly also in GBIF, same links are skipped later) ----------

def idigbio_rows(label: str, names: list[str], count_only: bool = False) -> list[dict] | int:
    rows, total = [], 0
    for name in names:
        rq = json.dumps({"scientificname": name.lower()})
        offset = 0
        while True:
            page = get_json(f"{IDIGBIO_API}?{urllib.parse.urlencode({'rq': rq, 'limit': 100, 'offset': offset})}")
            total += page["itemCount"] if offset == 0 else 0
            if count_only:
                break
            for it in page["items"]:
                d, t = it.get("data", {}), it.get("indexTerms", {})
                url = d.get("ac:accessURI") or d.get("ac:goodQualityAccessURI") or d.get("dcterms:identifier") or ""
                lic = gbif_license(d.get("xmpRights:WebStatement") or d.get("xmpRights:UsageTerms") or "")
                # api.idigbio.org/v2/media/... was iDigBio's own copy and is gone (410, Nov 2026); those
                # collections (MSU's on Ecdysis) come through GBIF with their original links instead
                if not url.startswith("http") or "api.idigbio.org" in url or not lic:
                    continue
                rows.append({
                    "label": label, "source": "idigbio", "record": (t.get("records") or [""])[0],
                    "photo": it["uuid"], "record_url": f"https://portal.idigbio.org/portal/mediarecords/{it['uuid']}",
                    "taxon": name, "life_stage": "", "place": "", "country": "", "date": "", "license": lic,
                    "attribution": d.get("xmpRights:Owner", ""), "source_url": url,
                })
            offset += 100
            if offset >= page["itemCount"]:
                break
    return total if count_only else rows


# ---------- Animal Diversity Web (University of Michigan; Phil Myers' moth photos, CC BY-NC-SA) ----------

def get_text(url: str, retries: int = 5) -> str:
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500 or attempt == retries - 1:
                raise
            time.sleep(30 * (attempt + 1))  # 429: the portal asks us to slow down
    raise RuntimeError("unreachable")


def adw_rows(label: str, account: str | None, count_only: bool = False) -> list[dict] | int:
    if not account:
        return 0 if count_only else []
    pages = sorted(set(re.findall(r'href="(/collections/contributors/[^"]+/)"', get_text(f"{ADW}/accounts/{account}/pictures/"))))
    if count_only:
        return len(pages)
    rows, names = [], set()
    for page in pages:
        name = page.rstrip("/").split("/")[-1]
        if name in names:  # the same photo filed under two collection folders
            continue
        names.add(name)
        html = get_text(ADW + page)
        img = re.search(r'src="(' + re.escape(page) + r'[^"]+\.jpg)"', html)
        lic = re.search(r"creativecommons.org/licenses/([a-z-]+)/([0-9.]+)", html)
        if not img or not lic:
            continue
        who = page.split("/")[3].replace("_", " ").title()
        rows.append({
            "label": label, "source": "adw", "record": page.rstrip("/").split("/")[-1], "photo": page.rstrip("/").split("/")[-1],
            "record_url": ADW + page, "taxon": account.replace("_", " "), "life_stage": "", "place": "", "country": "",
            "date": "", "license": f"cc-{lic.group(1)}-{lic.group(2)}", "attribution": f"{who}, Animal Diversity Web",
            "source_url": ADW + img.group(1),
        })
        time.sleep(0.5)
    return rows


# ---------- Ecdysis (Symbiota portal for arthropod collections: MSU, Mississippi, Purdue...) ----------

def ecdysis_rows(label: str, names: list[str], count_only: bool = False) -> list[dict] | int:
    """Its API has no image links, so: the search results (imaged specimens only, 100 a page), then each
    specimen's page for its photos and licence."""
    occids: list[str] = []
    for name in names:
        page = 1
        while True:
            time.sleep(2)
            q = {"taxa": name, "usethes": 1, "taxontype": 2, "hasimages": 1, "page": page}
            html = get_text(f"{ECDYSIS}/list.php?{urllib.parse.urlencode(q)}")
            found = [o for o in dict.fromkeys(re.findall(r"openIndPU\((\d+)", html)) if o not in occids]
            occids += found
            m = re.search(r"records \d+-(\d+) of ([\d,]+)", html)
            if not found or not m or int(m.group(1)) >= int(m.group(2).replace(",", "")):
                break
            page += 1
            time.sleep(2)
    if count_only:
        return len(occids)
    rows = []
    for occ in occids:
        url = f"{ECDYSIS}/individual/index.php?occid={occ}"
        html = get_text(url)
        lic = re.search(r"creativecommons\.org/(licenses/([a-z-]+)/([0-9.]+)|publicdomain/zero)", html)
        if not lic:
            continue
        license_ = "cc0" if "zero" in lic.group(1) else f"cc-{lic.group(2)}-{lic.group(3)}"
        holder = re.search(r"Rights Holder:\s*(?:<[^>]+>\s*)*([^<]+)", html)
        files = re.findall(r"https://media01\.symbiota\.org/media/[^\"' ]+?\.(?:jpe?g|JPE?G)", html)
        # each photo comes as base, _lg (large) and _tn (thumbnail): keep the large one, else the base
        bases = dict.fromkeys(re.sub(r"_(?:lg|tn)(\.\w+)$", r"\1", f) for f in files)
        for i, base in enumerate(bases):
            large = re.sub(r"(\.\w+)$", r"_lg\1", base)
            rows.append({
                "label": label, "source": "ecdysis", "record": occ, "photo": f"{occ}_{i}", "record_url": url,
                "taxon": names[0], "life_stage": "", "place": "", "country": "", "date": "",
                "license": license_, "attribution": holder.group(1).strip() if holder else "",
                "source_url": large if large in files else base,
            })
        time.sleep(2)
    return rows


# ---------- Europeana (European museums and libraries: Naturalis specimens, old bulletins and plates) ----------

def europeana_license(rights: str) -> str:
    r = rights.lower()
    if "publicdomain" in r or "noc-" in r:  # public domain mark, CC0, or rightsstatements.org "no copyright"
        return "public-domain" if "zero" not in r else "cc0"
    return gbif_license(r)


def europeana_rows(label: str, names: list[str], count_only: bool = False) -> list[dict] | int:
    rows, seen = [], set()
    for name in names + OLD_NAMES.get(label, []):
        q = {"wskey": "api2demo", "query": f'"{name}"', "media": "true", "rows": 100}
        for it in get_json(f"{EUROPEANA_API}?{urllib.parse.urlencode(q)}").get("items", []):
            lic = europeana_license((it.get("rights") or [""])[0])
            url = (it.get("edmIsShownBy") or [""])[0]
            if it["id"] in seen or not lic or not url:
                continue
            seen.add(it["id"])
            rows.append({
                "label": label, "source": "europeana", "record": it["id"], "photo": it["id"].strip("/").replace("/", "_"),
                "record_url": (it.get("guid") or ""), "taxon": name, "life_stage": "",
                "place": (it.get("title") or [""])[0][:120], "country": (it.get("country") or [""])[0], "date": "",
                "license": lic, "attribution": (it.get("dataProvider") or [""])[0], "source_url": url,
            })
    return len(rows) if count_only else rows


# ---------- download ----------

def image_kind(data: bytes) -> str:
    """The file extension for these bytes, or "" if they aren't a picture (an HTML error page, say)."""
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG"):
        return ".png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ""


def download(row: dict, out: Path, retries: int = 3) -> None:
    stem = out / row["label"] / row["source"] / str(row["photo"])
    for ext in (".jpg", ".png", ".gif", ".webp"):  # a file already there, fetched earlier or saved by hand
        dest = stem.with_suffix(ext)
        if dest.exists() and dest.stat().st_size > 0:
            row["local_path"] = str(dest)
            row["sha1"], row["status"] = hashlib.sha1(dest.read_bytes(), usedforsecurity=False).hexdigest(), "cached"
            return
    stem.parent.mkdir(parents=True, exist_ok=True)
    err = ""
    for attempt in range(retries):
        try:
            url = SCAN_IMGLIB.sub(SYMBIOTA_MEDIA, row["source_url"])
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                data = r.read()
            ext = image_kind(data)
            if not ext:
                raise ValueError("not an image")
            dest = stem.with_suffix(ext)
            dest.write_bytes(data)
            row["local_path"] = str(dest)
            row["sha1"], row["status"] = hashlib.sha1(data, usedforsecurity=False).hexdigest(), "ok"
            return
        except urllib.error.HTTPError as e:
            err = str(e)
            if e.code in (403, 404, 410):  # refused or gone: retrying won't help
                break
            time.sleep((20 if e.code == 429 else 2) * (attempt + 1))  # 429: the host asks us to slow down
        except Exception as e:
            err = str(e)
            time.sleep(2 * (attempt + 1))
    row["local_path"], row["status"] = "", f"failed: {err[:80]}"


def list_rows(label: str, source: str, count_only: bool = False):
    taxon, key, bugwood, cats, adw = SPECIES[label]
    if source == "inat":
        return inat_rows(label, taxon, "research", source, count_only)
    if source == "inat_needs_id":
        return inat_rows(label, taxon, "needs_id", source, count_only)
    if source == "inat_casual":
        return inat_rows(label, taxon, "casual", source, count_only)
    if source == "gbif":
        return gbif_rows(label, key, count_only)
    if source == "bugwood":
        return bugwood_rows(label, bugwood, count_only)
    if source == "idigbio":
        return idigbio_rows(label, cats, count_only)
    if source == "europeana":
        return europeana_rows(label, cats, count_only)
    if source == "ecdysis":
        return ecdysis_rows(label, cats, count_only)
    if source == "adw":
        return adw_rows(label, adw, count_only)
    return commons_rows(label, cats, count_only)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=paths.DATA / paths.REFERENCE)
    ap.add_argument("--only", nargs="*", choices=list(SPECIES), help="just these species")
    ap.add_argument("--sources", nargs="*", choices=SOURCES, default=list(SOURCES))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true", help="count records (observations, occurrences, files)")
    ap.add_argument("--retry-failed", action="store_true",
                    help="only download again the manifest's failed photos (no listing), then dedupe")
    ap.add_argument("--dedupe", action="store_true", help="only remove duplicate photos across the whole manifest")
    args = ap.parse_args(argv)
    labels = args.only or list(SPECIES)
    if args.dedupe:
        print(f"{dedupe(args.out / 'manifest.csv')} duplicates removed")
        return 0
    if args.retry_failed:
        return retry_failed(args.out, args.workers)

    if args.dry_run:
        for label in labels:
            print(f"  {label:15}", "  ".join(f"{s} {list_rows(label, s, True)}" for s in args.sources), flush=True)
        return 0

    manifest = args.out / "manifest.csv"
    keep = read_manifest(manifest)
    keep = [r for r in keep if not (r["label"] in labels and r["source"] in args.sources)]
    have = {(r["label"], same_link(r["source_url"])) for r in keep if r.get("local_path")}

    rows: list[dict] = []
    for label in labels:
        for source in args.sources:
            found = list_rows(label, source)
            new = [r for r in found if (label, same_link(r["source_url"])) not in have]
            have |= {(label, same_link(r["source_url"])) for r in new}
            print(f"  {label:15} {source:14} {len(found):6} photos, {len(found) - len(new)} links already fetched",
                  flush=True)
            rows += new

    counts: dict[str, int] = {}
    with ThreadPoolExecutor(args.workers) as pool:
        for i, _ in enumerate(pool.map(lambda r: download(r, args.out), rows), 1):
            s = rows[i - 1]["status"].split(":")[0]
            counts[s] = counts.get(s, 0) + 1
            if i % 1000 == 0:
                print(f"  {i}/{len(rows)} {counts}", flush=True)

    # Re-read: another run may have written its rows while this one downloaded.
    keep = [r for r in read_manifest(manifest) if not (r["label"] in labels and r["source"] in args.sources)]
    write_manifest(manifest, keep + rows)
    print(f"Done: {counts}. {dedupe(manifest)} duplicates removed. {manifest}. "
          f"{write_hand_list(args.out)} failed, listed in hand_download.csv.")
    return 0


def retry_failed(out: Path, workers: int) -> int:
    manifest = out / "manifest.csv"
    rows = read_manifest(manifest)
    failed = [r for r in rows if r["status"].startswith("failed")]
    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(lambda r: download(r, out), failed))
    write_manifest(manifest, rows)
    now = collections.Counter(r["status"].split(":")[0] for r in failed)
    print(f"Retried {len(failed)}: {dict(now)}. {dedupe(manifest)} duplicates removed. "
          f"{write_hand_list(out)} still to fetch by hand (hand_download.csv).")
    return 0


def write_hand_list(out: Path) -> int:
    """hand_download.csv: each photo that failed, its record page, and the name to save it under so the next
    run picks it up (as `cached`). Most are SCAN's museum photos, which refuse scripted downloads."""
    rows, seen = [], set()
    for r in read_manifest(out / "manifest.csv"):
        key = (r["label"], same_link(r["source_url"]))
        if r["status"].startswith("failed") and key not in seen:
            seen.add(key)
            rows.append({"label": r["label"], "source": r["source"], "why": r["status"][8:60],
                         "record_page": r["record_url"], "image_url": r["source_url"],
                         "save_as": f"{r['label']}/{r['source']}/{r['photo']}.jpg"})
    with open(out / "hand_download.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["label", "source", "why", "record_page", "image_url", "save_as"])
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def same_link(url: str) -> str:
    """One spelling per link: GBIF and iDigBio give the same museum photo as http/https, with or without :443."""
    return re.sub(r"^https?://", "", url.lower()).replace(":443/", "/")


def read_manifest(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def write_manifest(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def dedupe(path: Path) -> int:
    """Same bytes twice for one species, from any source or run: keep the copy from the source listed first in
    SOURCES (best documented), delete the others' files and mark them `duplicate`. Returns how many it removed."""
    rows = read_manifest(path)
    rank = {s: i for i, s in enumerate(SOURCES)}
    first: dict[tuple, str] = {}
    removed = 0
    for r in sorted(rows, key=lambda r: rank.get(r["source"], 99)):
        if not r.get("sha1") or not r.get("local_path"):
            continue
        k = (r["label"], r["sha1"])
        if k in first and first[k] != r["local_path"]:
            Path(r["local_path"]).unlink(missing_ok=True)
            r["duplicate_of"], r["status"], r["local_path"] = first[k], "duplicate", ""
            removed += 1
        else:
            first.setdefault(k, r["local_path"])
    write_manifest(path, rows)
    return removed

if __name__ == "__main__":
    sys.exit(main())
