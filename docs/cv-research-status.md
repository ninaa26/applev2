# Insect-CV research: what we did with each finding

Status of every item in "Moth Monitoring: Computer Vision (Imaging, Detection, Counting)" (Oct 6 2026)
against this repo, as of Oct 7 2026. Start with what could **not** be done; the full item-by-item list follows.

Words used: **Done** = changed in code or docs on Oct 6–7 2026 and tested. **Had** = already how the repo
worked. **Not ours** = about light traps, other hardware or other pests. **Open** = see the first two sections.

## Could not be done here

| # | Item | Why not | What would settle it |
|---|---|---|---|
| 1 | A detector score on our own trap | No moth of target size has been photographed by the trap camera; `ml/data/own/` does not exist | Stage cards in the trap, lock test cards, run `sentinel-server evaluate` ([evaluation.md](evaluation.md)) |
| 2 | Retrained YOLO with the new options scored on its test photos | Partly done: one run finished on Oct 7 (three-way split, overlap 224, blank liners): test mAP50 0.52, moth 0.82, moth precision 0.77 and recall 0.80 at the chosen settings, debris not found (`ml/README.md`). `--imgsz 800`, `--one-insect-class` and `--synth` have not been compared, at about two hours a run | One run per option, same test photos |
| 3 | Trap-style training photos on trap-camera liners | The only blank IMX219 liner photos predate the LED move; the camera needs its white-card calibration redone first | Recalibrate, photograph a blank liner, put it in `ml/data/liners/`, re-run `make_trap_style.py` |
| 4 | Glare removed at the source | Hardware: the LED needs a diffuser or re-aiming. Measured Oct 6 photos with the LED beside the camera: 10–13% of the card blown out to white. Software now measures it and raises a `glare` event, nothing more | Diffuser, then recalibrate |
| 5 | Lens focal length and aperture confirmed | Our measurement (15.3 px/mm at ~110 mm) implies ~1.9 mm; a reseller's listing says 2.5 mm f/2.8. Unresolved ([CAMERAS.md](../hardware/CAMERAS.md)) | Measure lens-to-card distance, read the lens barrel |
| 6 | Counting crowded liners with the YOLO detector | The baseline estimates touching clumps by area; YOLO has nothing equivalent, and we have no crowded liner with a true count to build or check one | A labelled liner past ~60 insects |
| 7 | Telling a spread-wing moth from two touching moths | Part-boxes are now folded into the whole insect, but a single blob of two wings still goes to review as "2?". No spread-wing example with a true label exists in our data | Stage spread-wing moths on a locked card |
| 8 | Insects under 3 mm | The baseline ignores them on purpose (targets are 6 mm and up; smaller boxes are mostly dust). Their counts are therefore not reported. YOLO labels do include them | Nothing, unless bycatch counts become a goal |
| 9 | Hard-negative bootstrapping from our own false alarms | Needs reviewed photos from our trap (rejected detections). Blank liners are in as negatives; the loop itself is not built | Dashboard reviews, then extend `export_server_crops.py` to write YOLO backgrounds |
| 10 | Wind, and hourly weather, logged per photo | No sensor and no feed for them; temperature, humidity, battery, liner age and moon are logged | A weather feed (NEWA) joined by time |
| 11 | Pi-side numbers: energy per photo, battery days, memory on the Pi | The full cycle has not run on a Pi yet; detection runs on the Mac, where it was measured (4–5 s, 350 MB) | Bench cycle on the trap Pi with the INA219 log |
| 12 | Seals, battery storage, lure placement, liner changes | Physical. Written as a checklist: [bring-up.md](bring-up.md), "Before a trap goes out" | Doing the checklist |
| 13 | Liner discolouring over a season, and a different liner or trap colour | No season of photos yet. The card's colour is now logged with every photo so drift can be seen; any change of liner, colour, light or camera needs new locked cards | A season of photos |
| 14 | Measuring tracking on real sequences | The score exists (`insect` column in `boxes.csv`) and is unit-tested; no real multi-day sequence has been labelled | Box one liner on 3+ days |

## Needs your decision

- **Photos per day.** One a day is enough for pheromone traps and saves most battery (Suto 2022). The trap takes
  six. Two-photo confirmation needs a second photo, so at one a day a catch is confirmed a day late (it is still
  dated to the day it was first seen). A middle way that keeps same-night confirmation: 22:00 and 07:00. Not
  changed: it trades battery against delay, and battery life has not been measured.
- **Liner age limit.** `SENTINEL_LINER_MAX_DAYS=28` is our own number, not from the research.
- **Shape filter on the baseline** (from our own Oct 2 test, not this research): still not ported.

## What worked

| Finding | Status | What we do |
|---|---|---|
| Slicing / tiled inference | Done | Server YOLO detector runs on overlapping tiles at the trained px/mm; tiles merged by overlap with the smaller box. Baseline shrinks to 1,600 px: full size was tested and gained 1 moth of 211 for 2.4× the time, so it stays |
| Two-stage detect → classify | Had | Detector finds everything, classifier names it. The classifier is still switched off in the running server |
| Tuning NMS and max detections | Done | Max detections 1,000 per tile. NMS IoU and confidence are chosen on val by F1 and saved with the run. Yolo-pest's IoU 0.9 was tried: moth F1 0.74 against 0.84 at 0.5, so not copied |
| Larger, screened dataset; higher input size | Done / Open 2 | `--imgsz` added. Dataset: 25 fully labelled photos; 17 OFM liner photos still to label |
| Generic insect detector | Done | Server drops YOLO's classes and sends every box to the classifier; `--one-insect-class` trains it that way. Not yet compared |
| Synthetic copy-paste data | Had / Open 3 | `--synth` pastes cut-out web insects; `--blank` tiles are now among its backgrounds. Its one run was stopped at epoch 7 |
| Hard negatives; rotation / translation | Done / Open 9 | Blank trap-camera liners as empty tiles. Rotation, flips and scale were already in training |
| Grey-world colour correction | Had | Fixed colour gains plus white-card flat field do more than grey-world. Card colour now logged per photo to catch drift |
| Lightweight backbone | Not ours | Detection runs on the Mac. `--model yolo11n.pt` exists if it ever moves to the Pi |
| Tracking with appearance embeddings | Not ours | Insects on glue don't move; position matching is enough |
| Minimum track length | Had | Confirmed on the second photo; single sightings are dropped |
| 2-min time-lapse | Not ours | Light traps |
| On-device detect on a low-res stream | Not ours | Server-side |
| Image-based MCU trigger | Not ours | Scheduled wakes by RTC |
| Density / regression counting | Had / Open 6 | Baseline counts clumps by area and sends them to review; `card_full` at 60 |
| Self-cleaning trap | Not ours | No mechanism; liner changes instead (`card_full`, `card_old`) |
| Controlled light, background, distance | Had / Open 4 | Fixed exposure, gains and white-card map per camera and light |
| Edge hardware choice | Not ours | Pi 5 captures only |

## What didn't work

| Pitfall | Status | How we avoid it |
|---|---|---|
| Blob / background-subtraction detection | Done / Open 1 | Ours is still the default until a YOLO run is scored on our liners; YOLO is now selectable. Its known failures are guarded: off-card boxes, part-boxes, mis-scaled and blurred photos |
| SAM as the detector | Had | Never used; cut-outs come from flatbug |
| Full-image inference on high-res images | Done | Tiles (above) |
| Upgrading detector version as the fix | Done | Rule in `.claude/rules/ml.md`: labels and resolution first |
| Leaving small insects out of labels | Done / Open 8 | Labelling rule added; public sets where only the target was boxed are kept out of training |
| Box detectors on dense, overlapping catches | Open 6 | |
| PIR / heat triggers; IR beam counters | Not ours | |
| Double detections on large moths | Done / Open 7 | `merge_fragments`: 31 → 25 and 21 → 17 boxes for 7 pinned specimens; 2 of 328 OFM lost |
| Tracking fast or similar insects | Not ours | Stationary insects |
| Lab-only or single-background training | Done / Open 3 | Blank trap-camera liners added; trap-style classifier data still on 3 webcam liners |
| Tiny trigger CNNs | Not ours | |
| Slicing on a Raspberry Pi | Not ours | Slicing runs on the Mac: 10–12 s a photo |

## Overlooked considerations

| Item | Status | What we do |
|---|---|---|
| Document the optics | Done / Open 5 | Derived focal length, depth of field and the disagreement with the listing are in CAMERAS.md |
| Resolution sets the taxonomic ceiling | Done | `evaluate` reports px/mm and the OFM's length in px against the 50 px minimum |
| Report results by object size | Done | Recall and species accuracy in four size bins |
| Glare and landing surface | Done / Open 4 | Glare measured per photo, `glare` event over 2% |
| Unusable frames | Done | Blurred or mis-scaled photos are left out and counted in the report |
| Decay after ~72 h | Done | Species vote only from a moth's first 72 hours; confirmed moths stay counted when later missed |
| Non-insect objects | Done | Off-card boxes dropped; lure mask; `debris` class; false moths reported by cause |
| Background colour, discolouring | Open 13 | Card colour logged per photo |
| Spread wings | Done / Open 7 | |
| Pick and validate a counting rule | Had | New arrivals by tracking; validated by `evaluate` per liner and per trap-day |
| Light-off recounts; rare taxa; different community | Not ours | |
| Tracking is rarely measured | Done / Open 14 | |
| Busy nights spike memory | Done / Open 11 | Mac: 350 MB peak for the baseline on an 8 MP photo |
| Field failures are mundane | Open 12 | Checklist |
| Storage | Done | 2.2 MB a photo, ~2.4 GB per trap per season; server keeps all, trap keeps its last 200 |
| Log context with each image | Done / Open 10 | Liner age, moon, sharpness, glare, card colour, px/mm, temperature, humidity, battery |

## Things not to do

| # | Don't | Status |
|---|---|---|
| 1 | Downscale a high-res image into a detector | Done: tiles for YOLO; baseline tested at full size |
| 2 | Leave small, blurry or partial insects out of labels | Done: labelling rule; overlap fits the longest moth so each is whole in some tile |
| 3 | Blob detection or SAM in production | Open 1: baseline stays only until YOLO is scored |
| 4 | PIR or IR beams | Not ours |
| 5 | Sum detections across frames | Had: tracks |
| 6 | Let sticky surfaces fill up | Done: `card_full` at 60, `card_old` at 28 days |
| 7 | Lure in view; scale shedding | Had (mask) / Open 12 |
| 8 | Change the setup without re-validating | Done: stated in evaluation.md; scale check catches a moved camera |
| 9 | Chase newer YOLO versions | Done: rule |
| 10 | Assume a box detector counts crowds | Open 6 |
| 11 | Report only mAP | Done: count error per liner and per trap-day, by size, by cause; rule |
| 12 | Skip pre-deployment hardware tests | Open 12: checklist |
| 13 | Throw away raw images | Had: server keeps every photo |

## Pheromone / sticky traps

| Item | Status |
|---|---|
| One image per day | Needs your decision |
| Count new arrivals; track across days so a decaying moth isn't new | Had |
| Detector classes for debris | Had: YOLO `debris`, classifier `debris`; scored 0.04 with 89 boxes, so more debris labels are needed (Open 2) |
| Slice and raise max detections; density counting for overlap | Done / Open 6 |
| Varied phones | Not ours: growers don't photograph these traps |
| ±20% count error; trend alerts first | Had: pass mark 0.80; alerts are not built |

## Light traps / screens

All four items (time-lapse interval, appearance tracking with re-entries, intermittent lighting, solar sizing):
not ours.

## CV pipeline checklist

| Step | Status |
|---|---|
| Fix the hardware and document optics | Open 4, 5 |
| px/mm from the smallest target | Done: reported by `evaluate`; bring-up check |
| Capture schedule; no PIR | Needs your decision |
| Log liner age, moon, weather | Done / Open 10 |
| Label every insect plus debris | Done (rule); 454 boxes still unlabelled |
| Augmentation, hard negatives, synthetic copy-paste | Done / Open 2, 9 |
| Sliced inference; tuned NMS and max detections | Done |
| Counting method | Had |
| Label sequences to measure tracking and counting | Open 14 |
| Count error per trap-day, by size, by false-positive cause | Done |
| Benchmark latency, memory, energy | Done on the Mac / Open 11 |
| Crops to the classifier; archive raw images | Had |
