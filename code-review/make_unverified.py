"""Builds UNVERIFIED.md: everything Gemini claimed that Claude has not checked yet.

    python3 code-review/make_unverified.py && python3 code-review/build_ledger.py

The Flash findings are pulled from gemini-raw/review_*.md automatically. The other sections are lists
kept in this file. When an item gets checked, move it into LEDGER.md (as a to-do, a fact, or a wrong
claim) and delete it from the list here (or, for Flash findings, add its title to CHECKED below).
"""
import re
from pathlib import Path

here = Path(__file__).parent
raw = here / "gemini-raw"

# Flash medium/low findings already checked (a substring of the title is enough).
CHECKED = [
    "services.card_at returns None",  # wrong: see LEDGER.md, Checked and wrong
]

HIGH_UNCHECKED = [
    ("ML", "ml/export_server_crops.py:63-80", "Keeps every capture image in memory while exporting crops; may run out of memory on a big export.", "review_ml_1.md"),
    ("ML", "ml/eval_field_cards.py:42-44", "The `coarse()` mapping of the head's species labels to moth / other_insect / debris may score species as the wrong coarse class.", "review_ml_1.md"),
    ("ML", "ml/fetch_ami.py:118-120", "Uses the GBIF occurrence id as the key, but one occurrence can have several images, so images may be dropped or duplicated.", "review_ml_1.md"),
    ("ML", "ml/build_dataset.py:227-231", "Near-duplicate removal drops both photos when an own photo matches a web photo with a different label.", "review_ml_0.md"),
    ("ML", "ml/build_dataset.py:246-251", "Synthetic crops from field cards (`own_group`) get a split from their group alone, which may not match the split of their source card.", "review_ml_0.md"),
    ("ML", "ml labeller (save handling)", "Saving boxes asynchronously can lose box ids or leave orphan boxes if you draw quickly.", "review_ml_2.md"),
    ("ML", "ml/make_bundle.py", "Absolute paths in dataset.csv can break the bundle or escape the bundle folder.", "review_ml_2.md"),
    ("ML", "ml/make_trap_style.py:188", "A size like `-`, `?` or blank in the field-card sheet crashes `float()`.", "review_ml_3.md"),
    ("ML", "ml/make_trap_style.py:230, 244", "Cutouts whose label isn't in CLASS_OF aren't filtered (only LENGTH_MM is checked).", "review_ml_3.md"),
    ("ML", "ml/recover_roboflow_originals.py:40-41, 54-55", "A missing or corrupt image gives `None` from `cv2.imread` and crashes `cvtColor`.", "review_ml_3.md"),
    ("ML", "ml/tests/test_trap_style.py, ml/tests/test_train_v2.py:20-33", "The tests miss key paths (claimed gaps).", "review_ml_3.md"),
    ("ML", "ml/train_v2.py:192-196", "SequentialLR breaks when there are 2 or fewer steps (1 epoch, 1 batch); needs torch to test.", "review_ml_4.md"),
    ("Field tests", "field-tests/esp32-window-day/finish.sh:31-32", "Image paths from the database go to `tar` unchecked (`../` paths).", "review_cross_1.md"),
    ("Hardware", "hardware/mockup_template.py:62, 67-71", "The SVG's cut line cuts the end flaps off the floor.", "review_cross_2.md"),
    ("Repo", "Patti's code (root)", "Uses ImageFolder's alphabetical class order, no grouped split (leakage), and binary CM / not-CM classes instead of the six labels.", "review_cross_0.md"),
]

ARGON_PARTLY = [
    ("A2", "The ESP32 → hub → server field table", "Spot-checked only. Check each row against `main.cpp`, `gateway.py` and `app.py`."),
    ("SRV-04", "Worker overwrites dashboard edits made while a photo is being classified", "Likely, not traced. Needs a test that edits a liner during a slow classify."),
    ("ARCH-02", "The worker thread stalls the API through Python's GIL", "Most heavy work (OpenCV, torch) releases the GIL. Measure upload latency while the worker runs."),
    ("ARCH-04", "Switch node-to-hub from HTTP to ESP-NOW or LoRa for range and battery", "Opinion. LoRa can't carry photos; ESP-NOW would need a relay design."),
    ("C2 OPS-01", "Leafed-out canopy will cut Wi-Fi range", "Plausible; needs the field test (ledger L-23)."),
    ("C2 CV-01", "Dawn condensation blurs photos, and the blur check rejects them", "Guess; check whether rejected-for-blur photos cluster at dawn."),
    ("C2 OPS-02", "Daylight saving time makes fixed wake times drift against dawn and dusk", "Design opinion; the schedule itself is DST-safe."),
    ("C2 CV-02", "Summer heat melts the glue and insects slide, breaking tracking", "Guess."),
    ("UI-01", "Make the dashboard an offline-capable app (PWA)", "Opinion; L effort."),
    ("UI-03", "The overview overflows on phones", "`.tbl{overflow-x:auto}` exists, so tables scroll; check on a real phone."),
    ("UI-04", "Scouts need bulk review and CSV export", "Feature request; not checked against the review page."),
    ("ML-01", "The v2 CNNs learnt the single OFM trap's look", "Matches `docs/ml-research-status.md`; the numbers weren't re-run."),
    ("CV-04", "Change detection between photos would fail from shifting sunlight", "Opinion."),
    ("ML-03", "Only 1 lesser appleworm in training, so OFM look-alikes aren't covered", "The count matches `ml/README.md`; the risk is a judgement."),
    ("B3", "Cellular data is about 159 MB a month per trap", "At test settings (48 photos a day); recompute for field settings."),
]

RESEARCH = [
    ("D1", "Product specs for Trapview, Semios, FarmSense, iSCOUT, CropVue (capture rate, power, price)", "Not opened."),
    ("D1", "Litestream to Cloudflare R2 plus Cloudflare Tunnel for HTTPS as the backup and hosting setup", "Not checked against current pricing or limits."),
    ("D1", "Add a hardware RTC to the hub Pi", "Not checked; the Pi 5 has an RTC, the battery is optional."),
    ("D2", "Clamp scale and remove first-photo lock gives \"+25 pts\"; other per-fix gains", "Numbers have no source."),
    ("D2", "Add measured size (mm) and lure as classifier inputs", "Method claim not checked against sources."),
    ("D2", "Cross-polarizer film on LED and lens removes most glare on sticky cards", "Sources not opened."),
    ("D2", "1-class YOLOv8n with OpenVINO INT8 runs under 0.45 s per image on a Pi 5", "Speed figure not checked."),
    ("D2", "Freeze each insect's species after its first 5 fresh photos", "Method claim not checked."),
    ("D2", "Poisson background swap and outlier exposure fix the single-trap OFM shortcut", "Method claim not checked."),
    ("D2", "Public sticky-trap datasets and their licences (list in the report)", "Links exist (mostly); licences not checked."),
    ("D3", "Part weights (trap 70 g, liner 18 g, turret 31 g, tray 58 g, pod 195 g)", "Estimates; weigh real parts."),
    ("D3", "ASA vs PETG vs PLA outdoors, snap-fit design rules", "Sources not opened."),
    ("D3", "ePTFE vent, O-ring window, IP66/67 test plan", "Not checked."),
    ("D3", "Hang at 6-8 ft in the upper third of the canopy for CM; per-pest heights", "Sources not opened."),
    ("D4", "OBLR biofix rule and spray timing (DD43)", "The cited Penn State page doesn't say it; check NEWA's OBLR page."),
    ("D4", "OBLR: trap counts don't gate sprays; scout 3% of terminals", "Sources not opened."),
    ("D4", "Feature list F-05 onward (SMS/email alerts, spray log, NYSDEC record export, multi-farm)", "Not checked."),
    ("D4", "What growers praise or complain about in Trapview, Semios, Croptracker and others", "Review sites not opened."),
    ("All", "The roughly 360 sources not opened", "The links exist (87%), but whether they say what's claimed is unchecked."),
]


def flash_medium_low():
    out = []
    for f in sorted(raw.glob("review_*.md")):
        lines = f.read_text().split("\n")
        head = None
        for i, line in enumerate(lines):
            if re.match(r"^(#{2,5} |\*\*[A-Z0-9]|[0-9]+\. \*\*)", line) and "Severity" not in line:
                head = line
            m = re.search(r"Severity\W*(Medium|Low)", line, re.I)
            if not (m and head):
                continue
            title = re.sub(r"\(file:[^)]*\)|[#*`]|\[|\]", "", head).strip()
            title = re.sub(r"^\d+(\.\d+)*\.?\s*", "", title)
            claim = ""
            for j in range(i, min(i + 25, len(lines))):
                if re.search(r"Failure Scenario|What goes wrong|Problem|Issue", lines[j], re.I):
                    claim = " ".join(lines[j:j + 2])
                    break
            claim = re.sub(r"\(file:[^)]*\)|[*`]|\[|\]", "", claim)
            claim = re.sub(r"^.*?(Scenario|wrong|Problem|Issue)\W*", "", claim, flags=re.I).strip()
            if len(claim) > 220:
                claim = claim[:217].rsplit(" ", 1)[0] + "…"
            if not any(c in title for c in CHECKED):
                area = f.stem.replace("review_", "").split("_")[0]
                out.append((area, m.group(1).capitalize(), title[:140], claim, f.name))
            head = None
    return out


def esc(s):
    return s.replace("|", "\\|")


md = ["# Unverified",
      "",
      "Everything Gemini claimed that Claude **hasn't checked yet**. Treat these as leads, not facts. When one is checked, it "
      "moves to the Ledger tab (as a to-do, a fact, or a wrong claim) and leaves this list. Source files are in "
      "`code-review/gemini-raw/`.",
      "",
      "## 1. High-severity code claims not checked (Flash)",
      "",
      "| Area | Where | Claimed problem | Raw file | Status |",
      "|---|---|---|---|---|"]
md += [f"| {a} | `{esc(w)}` | {esc(c)} | `{r}` | unverified |" for a, w, c, r in HIGH_UNCHECKED]
md += ["", "## 2. Argon findings only partly checked", "",
       "| ID | Claim | What's missing | Status |", "|---|---|---|---|"]
md += [f"| {i} | {esc(c)} | {esc(n)} | unverified |" for i, c, n in ARGON_PARTLY]
md += ["", "## 3. Research claims not checked (Deep Research D1–D4)", "",
       "| Report | Claim | Note | Status |", "|---|---|---|---|"]
md += [f"| {r} | {esc(c)} | {esc(n)} | unverified |" for r, c, n in RESEARCH]
flash = flash_medium_low()
md += ["", f"## 4. Flash medium and low findings ({len(flash)}, none checked)", "",
       "Pulled automatically from the raw review files. Many repeat the high-severity ones or are style points; "
       "the ones about the upload protocol, phenology and data splits are worth checking first.", ""]
for area in ("server", "device", "ml", "cross"):
    rows = [x for x in flash if x[0] == area]
    if not rows:
        continue
    name = {"server": "Server", "device": "Device, hub and firmware", "ml": "ML", "cross": "Docs, hardware, field tests, CI"}[area]
    md += [f"### {name} ({len(rows)})", "", "| Severity | Finding | Claimed problem | Raw file | Status |", "|---|---|---|---|---|"]
    md += [f"| {s} | {esc(t)} | {esc(c)} | `{r}` | unverified |" for _, s, t, c, r in rows]
    md.append("")

(here / "UNVERIFIED.md").write_text("\n".join(md) + "\n")
print(f"wrote UNVERIFIED.md: {len(HIGH_UNCHECKED)} high, {len(ARGON_PARTLY)} Argon, {len(RESEARCH)} research, {len(flash)} Flash medium/low")
