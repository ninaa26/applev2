# Brief for Gemini: full review of Orchard Sentinel, plus research

You are the reviewer and researcher for **Orchard Sentinel**, a Cornell capstone (fall 2026, a small student
team). Read this whole brief before the attached files. It says what the project is for, what already exists, what
we already know is broken, what we want from you, and the exact format to answer in.

Claude (another AI) checks every claim you make against the code before anyone acts on it. A claim with a file path
and quoted line is useful. A confident claim with no evidence costs time. When you aren't sure, say so.

---

## 0. How to use this brief (for the person running it)

The work is split into parts so no single answer gets cut short:

| Chat | Mode | Attach | Paste |
|---|---|---|---|
| 1 | Argon (or the strongest model you have) | all files 01–06 and this brief | "Do Part A" |
| 2 | same chat as 1 | — | "Do Part B" |
| 3 | same chat as 1 | — | "Do Part C" |
| 4 | **Deep Research** | this brief only | the Part D1 prompt (pipeline and architecture) |
| 5 | **Deep Research** | this brief only | the Part D2 prompt (ML and computer vision) |
| 6 | **Deep Research** | this brief only | the Part D3 prompt (the physical trap mount) |
| 7 | **Deep Research** | this brief only | the Part D4 prompt (what growers need from the dashboard) |

If an answer stops partway, reply "continue from where you stopped, same format". On the free plan with no Argon,
use the strongest model in the picker (e.g. 3.1 Pro), with Deep Research for chats 4–7. Save every answer as a
`.md` file and give them to Claude.

---

## 1. What the project is for

**Goal:** a camera inside a standard pheromone delta trap photographs the sticky liner on a schedule. Software counts
and identifies the moths caught and turns the counts into the spray and scouting timings growers use. The trap
replaces a person walking the orchard each week to count moths on cards by eye.

**Pests** (class labels used everywhere: `CM`, `OFM`, `OBLR`, `other_moth`, `other_insect`, `debris`):
- **CM**, codling moth (*Cydia pomonella*): main apple pest
- **OFM**, oriental fruit moth (*Grapholita molesta*): similar-looking, smaller
- **OBLR**, obliquebanded leafroller (*Choristoneura rosaceana*)

Each trap has one lure, so it's meant to catch one species, but other moths and insects land on the glue too.

**What growers act on:** the **biofix** (date of the first sustained catch, the season's start point) and the
**degree days** accumulated since then, following the NEWA (Cornell's Network for Environment and Weather
Applications) apple pest guidance. These give spray windows (e.g. CM egg hatch) and scouting dates. Weekly catch
per trap also matters against action thresholds. Getting the biofix date right, to within a day, matters more than
counting every moth perfectly.

**Users:**
1. **The grower or farm manager:** not technical, checks a phone in a truck or the packing house. Wants "do I need
   to spray, and when?", "which block?", and "is anything broken?"
2. **The scout or IPM consultant:** checks several farms, confirms IDs, keeps records.
3. **The student team:** maintains the hardware and software, labels data and trains models.

**Constraints:**
- A student team with one field season of data.
- Little money: a few hundred dollars of hardware per trap is already too much.
- Server is a Raspberry Pi 5 (no GPU) for now, a small rented cloud server later.
- The hub has mains power in a fieldhouse with a cellular connection.
- Traps are on battery, maybe with solar.
- The trap body is a cheap, thin, corrugated-plastic delta trap.

---

## 2. How it works now (verify against the code)

```
ESP32-S3 camera nodes (one per trap, battery)
   │  Wi-Fi: the hub's access point or the fieldhouse Wi-Fi; HTTP POST of a JPEG + JSON metadata header
   ▼
Hub Raspberry Pi (no camera, mains power, always on)          device/sentinel_device/gateway.py
   │  stores photos to disk (queue/ → sent/), serves each node its wake schedule and the time,
   │  relays "Take a photo now" requests from the dashboard
   │  cellular + Tailscale VPN; HTTP upload with each trap's API key
   ▼
Server: FastAPI + SQLite on a Raspberry Pi 5 (stand-in for cloud)          server/sentinel_server/
   │  upload API (dedup by capture_uid) → background worker thread:
   │  detect (OpenCV baseline that measures the liner's 25 mm grid for scale and removes grid lines,
   │  corrects lens distortion) → track each insect across the liner's photos so each is counted once
   │  → classify (BioCLIP embeddings + linear head, or a trained checkpoint) → species consensus per track
   │  → review queue (unsure labels + a 1-in-10 spot check of sure ones)
   │  → phenology: sustained-catch biofix + degree days (NEWA weather import, or the trap's sensor)
   ▼
Dashboard (server-rendered HTML; Jinja templates + one CSS file)
   orchard overview, per-trap page, photo pages, review queue, set-up page for hubs and cameras
```

Earlier design, still in the code: a Raspberry Pi with its own camera *in* the trap (`device/sentinel_device/`
cycle, camera, queue, uploader, RTC wake scheduling, SHT45 temperature/humidity and INA219 power sensors). The team
switched to ESP32 cameras on Oct 22 2026 for lower power.

**Hardware facts:**
- **Trap:** Alpha Scents red plastic delta trap, corrugated plastic.
  - Roof panels: 150 mm each side.
  - Floor: 195 mm wide.
  - Floor to inside roof peak: **110 mm**.
  - Length: 227 mm with the end flaps folded up.
  - Comes with a wire hanger.
- **Sticky liner card:** 174 × 198 mm, printed 7 × 7 grid of 25 mm squares, a 174 × 22 mm printed header at one end.
- **Camera now:** Freenove ESP32-S3-WROOM CAM (N8R8: 8 MB flash, 8 MB PSRAM) with a Taidacent OV5640 (5 MP, 130° lens, 24-pin DVP). It reads about 10.3 px/mm at 2048 × 1536 from 110 mm.
- **Height:** the 130° fisheye sees the whole card from the roof peak (lens about 110 mm above the card), so no
  housing above the roof is needed. The cost is fisheye distortion (corrected in software by straightening the
  grid) and lower px/mm toward the card's edges.
- **3D-print designs** (not printed yet):
  - `hardware/scad/camera_mount.scad`, a wedge in the roof apex, sized for the old Pi camera.
  - `hardware/scad/liner_tray.scad`, a slide-in liner tray with ArUco corner markers. It's wider than the floor and
    needs a redesign.
- **Lighting:** an LED lights the card. 10–13 % of the card is blown out by glare, and there's no diffuser yet.
- **Power** (docs/wiring.md): 1S lithium pack (18650s or LiFePO4); a solar option uses a CN3791 charger.

---

## 3. What we already know (don't spend your answer re-finding these)

File `05_review_findings_so_far.md` has an earlier review (Gemini Flash, checked by Claude). In short:
- **Confirmed:** the bugs it lists, for example:
  - `reprocess_card` inflates reviewed tracks' counters
  - liner age is computed before the false-new-liner check
  - the scale check can lock in a wrong grid reading
  - the OBLR biofix label and the code disagree
  - the firmware's drift-rate correction rarely runs
  - `train_v1.py --final` crashes
  - a weekday-flaky test
- **Shown wrong:** a few claims it lists (don't repeat them).
- **Already built:**
  - dedup uploads by `capture_uid`
  - store-and-forward queues on the hub and the Pi trap
  - SQLite WAL mode
  - tracking across photos
  - grouped train/test splits
  - a review queue
  - the NEWA sustained-catch biofix
- **Not built yet** (from README "Not done yet"):
  - ArUco alignment in the pipeline
  - an LED diffuser
  - finished OFM labels
  - accuracy measured on our own locked test cards
  - an entomologist's check of labels
  - a second OFM data source (every model learnt one trap's look)
  - the hub on cellular with its own access point
  - a cloud server with HTTPS and a domain
  - a dashboard settings page
  - alerts (including "hub offline")
  - Postgres or Docker
- **Known problems** (README): the grid finder misreads photos with insects on them (5 of 10 read 32–63 px/mm
  instead of 15.3); the scale check trusts a liner's first photos.

`docs/cv-research-status.md` and `docs/ml-research-status.md` list research the team already acted on, what failed,
and "things not to do". **Read them before suggesting ML or CV changes**, and say when you disagree with one of
their conclusions rather than silently re-suggesting it.

---

## 4. Rules for every answer

1. **Evidence:** every code claim gets the file path, the function, and a short quote of the line(s). Every web
   claim gets a URL. No URL means no claim. Don't make up papers, products or numbers.
2. **Confidence:** label each finding **Sure** (you read the code and traced it), **Likely** (you read it but
   couldn't trace every path) or **Guess** (an idea worth checking).
3. **Search first:** the code is spread over four files. Before saying "X is missing", search all four for it.
4. **Be specific to this project:** "add monitoring" is useless; "the hub should email when a node misses 2
   check-ins: add it to `gateway.py`'s check-in handler, here's how" is useful.
5. **Rank:** within each section, most important first. Give an effort for each fix: **S** (under a day),
   **M** (2–5 days) or **L** (over a week).
6. **Format:** use this finding template, with an ID prefix by area (`SRV-`, `DEV-`, `FW-`, `ML-`, `CV-`, `UI-`,
   `ARCH-`, `DOC-`, `HW-`, `OPS-`):

```
### SRV-07 · <one-line title>
- Severity: critical | high | medium | low     Confidence: Sure | Likely | Guess     Effort: S | M | L
- Where: server/sentinel_server/pipeline/worker.py, Worker.process()
- Evidence: `quoted line(s)`
- What goes wrong: a concrete scenario (inputs → wrong result)
- Fix: what to change, with a code sketch if short
```

---

## Part A: Code review (chat 1, files 01–05 attached)

Go through **every file** and report the following. Spend the most effort on A1–A3.

**A1. Bugs.** Wrong results, crashes, data loss, races (the API and the worker write the same SQLite database),
time and timezone errors (naive UTC is stored; local dates for biofix), off-by-ones, error handling that hides
failures.

**A2. The edges between parts.** Check that the ESP32 firmware (`device/esp32-node/src/main.cpp`), the hub
(`device/sentinel_device/gateway.py`, `uploader.py`, `queue`) and the server API (`server/sentinel_server/app.py`)
agree, field by field. Make a table: field, what the firmware sends, what the gateway expects or forwards, what the
server expects. Cover:
- HTTP status codes and how each side reacts
- retries and duplicates
- photo size limits
- clock and time sync (the node takes its time from the hub)
- what happens on reboot mid-upload, a full disk on the hub, a full flash on the node, or the server unreachable
  for a week

**A3. The core logic, checked against the domain:**
- **Counting:** does tracking across photos count each moth once? Consider moths that shift, get covered, overlap,
  or arrive as two touching insects; a liner replaced without the button press; photos arriving late or out of
  order.
- **Phenology:** `phenology.py` and `services.phenology_status`. Check the biofix rule per pest against NEWA, and
  check the degree-day method (base and upper thresholds, the horizontal cutoff, single sine vs.
  Baskerville–Emin), season boundaries and missing weather days.
- **Review policy:** do unsure labels reach a person, and can one wrong unreviewed label move the biofix?

**A4. Security.** The upload API's auth, the dashboard password, path traversal on stored images, input validation,
CSRF, secrets in code or config, and the ESP32's open web server during setup preview. The server will move to the
public internet with HTTPS. List what must change before that.

**A5. Deprecated or outdated code.** Old FastAPI, Starlette, SQLAlchemy, Pydantic, PyTorch or Arduino-ESP32 /
ESP-IDF APIs, unpinned dependencies, the `httpx`/TestClient deprecation warning.

**A6. Inconsistencies.**
- Docs vs. code: commands, paths, flags and defaults that changed.
- Between modules: names, defaults, class labels.
- Leftovers from the Pi-camera design that confuse the ESP32 design.
- The stray root file `Patti's code`.

**A7. Dead code, duplication, structure.** What can be deleted or merged, and where modules are too coupled. Is the
`server/`, `device/`, `ml/` split right? Should the upload protocol be defined once and shared?

**A8. Performance on a Raspberry Pi 5 with no GPU:**
- detection and classification time per photo
- memory use
- N+1 queries on the dashboard
- blocking work in `async` handlers
- photo storage growth over a season
- what breaks first at 10, 50 or 200 traps

**A9. Tests.** What's untested that matters most, with a concrete test for each. Flaky tests (date- or
weekday-dependent). What CI should add (firmware build, lint).

## Part B: Live system review (chat 2, uses file 06)

**B1. Health right now.** Using `06_live_snapshot.md`, go through:
- photos per camera per day vs. the schedule
- gaps
- failed photos and their reasons
- queue backlogs on the hub
- check-in gaps per node (status.jsonl: rssi, boots, errors, awake time, chip temperature)
- server and hub logs (errors, tracebacks, "database is locked", timeouts)
- Pi temperature, throttling, memory and disk

Quote the rows or lines.

**B2. Root causes.** For each problem in B1, point at the code that causes it, or say it's environmental (Wi-Fi
range, power).

**B3. Battery and data budget.** Work these out from the real wake times and photo sizes in the snapshot:
- the ESP32's energy per day
- the cellular data per trap per month
- the storage per trap per season

Say what would make each cheaper.

**B4. What to watch.** What the team should monitor or get alerted on, with thresholds.

## Part C: Design, product, and what's missing (chat 3)

**C1. Architecture review** of capture → transfer → detect/track/classify → review → phenology → dashboard. What
would you change for:
- (a) this season, with no new hardware
- (b) a real multi-farm product

Cover:
- HTTP vs. MQTT vs. ESP-NOW from node to hub
- whether the hub should run detection itself (edge inference) to cut cellular data
- SQLite vs. Postgres
- job queue vs. worker thread
- image storage
- backups (none exist today)
- migrations (hand-rolled `_add_missing_columns` today)
- over-the-air firmware updates (none today)
- device provisioning and keys
- time sync

**C2. What we didn't account for.** Think like a grower, an entomologist and a field technician. Examples to
consider, beyond whatever else you spot:
- rain, dew and condensation on the lens
- glue melting in heat, dust and pollen
- birds, wasps or slugs on the liner
- moths caught at night when the camera can't see
- the lure changed but not the liner
- a liner full of debris
- a trap knocked down or hanging tilted
- the hub losing power
- spring frost and battery chemistry
- Wi-Fi range through foliage once leaves come in
- the red trap colour and the white balance
- someone changing a liner without pressing the button
- daylight saving time
- multiple traps per block
- a farmer with no signal in the orchard

**C3. What to build out next,** as a ranked roadmap with effort, split into "before the field season", "during"
and "after".

**C4. The web interface.** Read `server/sentinel_server/templates/` and `static/app.css` and judge them from the
grower's side (section 1). Then give:
1. Today's problems: confusing words, missing information, too many clicks, phone layout, accessibility.
2. A page-by-page spec of what a grower needs:
   - the first screen
   - a block or trap page
   - "what to do this week" (spray, scout, nothing)
   - a degree-day chart with the next milestone date
   - catch trends vs. threshold
   - alerts (email/SMS/push) and when to send them
   - trap health (battery, last photo, liner age, lure age)
   - record export for spray records and audits
   - multiple farms and users
   - offline or low-signal behaviour
   - a print view
3. What a scout or consultant needs on top.
4. A short wireframe in text for the 3 most important pages.

Keep the team's size in mind: say which parts are cheap wins and which aren't worth it this season.

**C5. ML and CV review** (`ml/` scripts, `server/sentinel_server/pipeline/detect.py`, `classify.py`, `track.py`,
the two research-status docs):
- Is the approach right (a classical OpenCV detector plus BioCLIP embeddings and a linear head, versus YOLO
  detect-and-classify, versus a two-stage detector and classifier)?
- Is the data plan right (AMI, iNaturalist, synthetic copy-paste onto liner photos, a few thousand real crops, OFM
  from a single trap)?
- Are the splits leak-free (`.claude/rules/ml.md`)? Is the evaluation honest (locked test cards, per-card count
  error, biofix-days error)?
- What would get the biggest accuracy gain per hour of student work?
- How should the grid-scale misreads be fixed (ArUco markers vs. the printed grid vs. a fixed camera height)?
- Should the pipeline use change detection between consecutive photos to find new arrivals?
- How should glare be handled?

---

## Part D: Web research (chats 4–7, Deep Research mode)

For each one: search widely, prefer primary sources (papers, extension publications, vendor docs, datasheets),
give URLs, and end with recommendations specific to the facts in section 2 of this brief. Separate what's proven
(measured in a paper or product) from opinion.

### D1. Pipeline and architecture: how professionals build this

Paste:
```
Do Part D1 of the attached brief. Research how commercial and academic automated insect-trap camera systems
work end to end, and how professionals build low-power camera IoT pipelines. Cover:
1. Commercial systems: Trapview, Semios, FarmSense, DTN/Spensa Z-Trap, Pessl/METOS iSCOUT, CropVue, Ecomatik,
   and any others. For each: capture frequency and resolution, lighting, power (battery/solar, battery life),
   transfer (cellular, LoRa, Wi-Fi, satellite), where inference runs (edge or cloud), how they count only new
   arrivals, reported accuracy and how it was validated, how a person reviews or corrects counts, price.
2. Academic papers since 2018 on automated codling moth, oriental fruit moth or tortricid sticky-trap counting:
   methods, dataset sizes, accuracy, and what failed.
3. ESP32-camera field deployments: deep-sleep current of ESP32-S3 camera boards in practice, OV5640 vs OV3660
   for this job, Wi-Fi range through orchard foliage, ESP-NOW or LoRa as alternatives, OTA updates with
   rollback, keeping the time right without the internet, PSRAM and JPEG settings.
4. Hub and server patterns: store-and-forward, idempotent uploads, MQTT vs HTTP for photos, device provisioning
   and per-device keys, fleet health monitoring and alerts, SQLite in production (WAL, backups with Litestream),
   when to move to Postgres, cheap cloud hosting with HTTPS for a student project.
5. Cellular data budgets for photo uploads and how products shrink them (crop, compress, send only changes,
   run detection on the hub).
End with: our pipeline vs. the best practice you found, a gap table, and recommendations ranked by value per
effort for a student team with one season.
```

### D2. ML and computer vision for sticky-trap insects

Paste:
```
Do Part D2 of the attached brief. Research the best current methods for detecting, counting and identifying
moths on sticky-trap photos with little labelled data and no GPU at inference time. Cover:
1. Detection: classical (thresholding, blob detection, grid removal) vs YOLO-family vs DETR vs SAM-based
   segmentation; small-object tricks (tiling such as SAHI, higher resolution); touching and overlapping insects.
2. Identification: CM vs OFM vs OBLR vs look-alikes (what features separate them, wingspan in mm, wing pattern;
   how many px/mm are needed); BioCLIP and other foundation-model embeddings with a linear head vs fine-tuning;
   hierarchical and open-set classification for "other moth"; how well models trained on one trap or region
   transfer to another (domain shift), and what fixes it.
3. Data: public sticky-trap and moth datasets (AMI, iNaturalist, the Nature/ScienceDirect sticky-trap datasets,
   others with URLs and licences), synthetic copy-paste data (does it help?), active learning, how many real
   labelled examples per class are typically needed.
4. Counting over time: change detection between consecutive photos of the same card, tracking, handling
   insects that decay, shift or get covered, and estimating count error.
5. Imaging: lighting for glossy sticky cards (diffusers, cross-polarisation, ring lights), glare removal,
   white-balance against a coloured trap, lens distortion correction, using fiducial markers (ArUco/AprilTag)
   for scale and alignment instead of the printed grid.
6. Evaluation: how papers and products report accuracy (per-card count error, precision/recall per class,
   biofix date error), and grouped splits by card and trap to avoid leakage.
7. Running on a Raspberry Pi 5 CPU: model sizes and speeds (ONNX, int8 quantisation, OpenVINO, NCNN).
End with: what our pipeline should change, ranked by expected accuracy gain per hour of student work.
```

### D3. The physical camera mount on the delta trap

Paste:
```
Do Part D3 of the attached brief. Research how to design and build the camera mount and housing for our trap,
and give a concrete design. Facts: the Alpha Scents red corrugated-plastic delta trap (roof panels 150 mm each,
floor 195 mm wide, 110 mm floor to inside peak, 227 mm long, thin and flexible, hung from a wire hanger on a
branch); a 174 x 198 mm sticky liner on the floor; a Freenove ESP32-S3 CAM board (about 40 x 50 mm) with an
Taidacent OV5640 5 MP with a 130° lens (sees the whole card from about 110 mm); a white LED; a 1S lithium battery pack (18650s or
LiFePO4) and maybe a small solar panel. To see the whole card, the lens must sit about 131-150 mm above the card,
which is 21-40 mm above the roof peak, so the camera probably needs a housing that pokes out above the roof, or a
wider lens. Cover:
1. How commercial camera traps (Trapview, Semios, iSCOUT, FarmSense and others) mount the camera on or in the
   trap, and photos or drawings of their designs with URLs.
2. Weight and strength: how much load a corrugated-plastic delta trap and its hanger can carry before it sags,
   twists or swings in wind; whether the electronics and battery should hang from the branch or hanger
   separately so the trap carries only the camera; ways to stiffen the trap (a printed frame or spine, ribs,
   clips along the roof peak, a rigid floor plate under the liner, replacing the floor) without changing how it
   catches moths.
3. Weatherproofing: IP ratings worth aiming for, sealing a camera window (gaskets, O-rings, glued acrylic or
   polycarbonate window), cable glands, breathable vents (ePTFE) against condensation, keeping dew and rain off
   the lens, desiccant, conformal coating, keeping the battery out of direct sun (heat) and frost.
4. Materials for 3D printing outdoors: PETG vs ASA vs PLA (UV, heat in summer sun, creep), wall thickness, how to
   design printed snap-fits and clips that survive a season, and the lightest structure that is still stiff.
5. Lighting and optics in the housing: LED placement and diffusers to stop glare on the glossy glue, keeping the
   LED from reflecting off the window into the lens, anti-fog.
6. Does a camera housing or light change how well the trap catches moths (entrance blocked, airflow and lure
   plume changed, light attracting or repelling moths, colour)? Find studies on trap design and catch.
7. The liner change workflow: a grower must swap the liner (every 1-4 weeks) and the lure without tools, in
   gloves, without knocking the camera out of focus or alignment. Designs for a slide-in tray, alignment
   markers, and a hinged or removable camera unit.
8. Hanging: height and position in the tree per NEWA/Cornell guidance for CM, OFM and OBLR traps, and how the
   mount affects that.
End with: a recommended design (a sketch in words with dimensions, parts list, materials, weight budget per
part, total weight target), two alternatives with trade-offs, and a test plan (rain test, drop test, a week
in sun, a wind test, a catch-comparison test against a plain trap).
```

### D4. What growers need from the dashboard

Paste:
```
Do Part D4 of the attached brief. Research what tree-fruit growers and IPM scouts actually need from a pest
monitoring app. Cover:
1. How growers use trap counts and degree days today for CM, OFM and OBLR in the Northeast US (NEWA apple pest
   models, Cornell and Penn State extension guides): biofix rules per pest, action thresholds (moths per trap
   per week), spray timing windows, which decisions depend on which numbers. Give exact values with sources.
2. What existing tools show (NEWA's own pages, Trapview, Semios, FarmSense, Spensa/DTN, Croptracker, Agworld):
   their key screens, alerts, and what users praise or complain about (reviews, extension articles, forum posts).
3. Usability for farmers: phone-first use in the field, low signal, gloves and sunlight, plain language, how
   often they check, SMS vs email vs push, trust in automatic counts (showing the photo, confidence, a person's
   confirmation), and spray record-keeping requirements.
4. Multi-farm and consultant needs: many blocks and farms, sharing, reports, exports.
End with: a ranked list of features for our dashboard, a page-by-page spec for the first version, and the
wording of the main "what to do this week" message for each pest.
```

---

## Part E: Anything else

After A–D, add anything a senior engineer, an entomologist or a product manager would raise that this brief didn't
ask about. For example:
- the field season plan and test schedule
- a risk register (what's most likely to sink the project, and how to prevent it)
- a field-deployment checklist
- a bill of materials sanity check with prices
- questions the team should ask an entomologist or a grower
- how to prove the system works to the capstone judges (which experiments and numbers to show)
- legal or privacy concerns (photos, farm data)

---

## What Claude would most like answered

These are the open questions behind the review. Answer any you can, with evidence:

1. **OBLR biofix:** NEWA's rule (first catch, or first sustained catch?). Also the exact CM and OFM rules, base
   temperatures, upper cutoffs, and which degree-day method NEWA uses for each.
2. **Resolution:** how many px/mm are needed to tell CM from OFM reliably on glue? Does the OV3660's narrow view
   (~18 px/mm over the card's middle) beat a wide OV5640 lens covering the whole card at fewer px/mm?
3. **Scale:** is the printed 25 mm grid a reliable scale reference, or should we rely on ArUco markers on a
   tray or a fixed, known camera height?
4. **Counting:** is counting only new arrivals between consecutive photos (change detection) more robust than
   our track-across-all-photos approach? How do products handle a liner that's replaced without anyone telling
   the system?
5. **Glare:** the cheapest proven fix for glare on sticky cards with a single LED.
6. **Power:** realistic ESP32-S3 camera board deep-sleep and per-photo energy, and how many days on 2 × 18650 at 6
   photos a day.
7. **Range:** 2.4 GHz Wi-Fi range from inside a delta trap through apple foliage. Is ESP-NOW or a long-range
   mode worth it?
8. **Mount:** the heaviest load the delta trap can carry without sagging (grams), and whether to hang the battery
   separately.
9. **Catch effect:** whether a camera housing in or on the trap reduces catches.
10. **Growers:** what they would pay, and what makes them stop trusting automatic counts.
11. **Classifier:** for one season of data, is BioCLIP embeddings plus a linear head the right choice, or would a
    small YOLO trained on our own cards beat it?
12. **Most likely failure:** of everything in the code, what is most likely to fail in the field in the first
    week?
