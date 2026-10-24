# Orchard Sentinel

A camera inside a pheromone delta trap that photographs its sticky liner, identifies and counts
codling moth, oriental fruit moth and obliquebanded leafroller, and turns the counts into the
biofix and degree-day timings from the NEWA guide. Cornell capstone, fall 2026.

Planning pages: [spec](https://claude.ai/artifact/GaBWYoqoXfmxyqFotrfH41) ·
[architecture](https://claude.ai/artifact/2WRtPNZk5ZcjBQNcR3oqus) ·
[build plan & tracker](https://claude.ai/artifact/VYyBzxuE8YnGAWV8XVyej5)

**How it fits together (plan since Oct 22 2026).** Each trap's camera is an ESP32-S3 board that wakes,
photographs the liner, sends the photo over Wi-Fi to the **hub** and sleeps. The hub is a Raspberry Pi
with no camera, on mains power in the fieldhouse, with a cellular connection; it keeps every photo
until the server has it. The **server** detects, classifies and counts, and serves the dashboard: a
Raspberry Pi 5 stands in for it now, a rented cloud server later. Details: [docs/esp32-traps.md](docs/esp32-traps.md)
and [docs/server-on-linux.md](docs/server-on-linux.md).

```
ESP32 cameras ──Wi-Fi──► hub Pi (no camera, always on) ──cellular + Tailscale──► server (Pi 5 now, cloud later) ──► dashboard
```

```
device/     Raspberry Pi software: the hub for the ESP32 cameras (gateway.py, install-hub.sh), the ESP32
            firmware (esp32-node/), and the earlier Pi camera trap (wake → LED → photo → upload → power off)
server/     FastAPI + SQLite (Postgres later): upload API, detection/tracking/counting worker, dashboard
ml/         training photos (AMI, iNaturalist, trap-style synthetic), labelling tool, detector and classifier training and scoring
hardware/   trap dimensions (TRAP.md), mockup trap template, 3D-printable camera mount + liner tray, calibration prints
docs/       ESP32 traps and the hub, the server on Linux or the Mac, Pi camera bring-up and wiring, camera bench test, measuring accuracy
```

## Quick start (no hardware needed)

```bash
cd server && uv venv --python 3.12 .venv && uv pip install -p .venv/bin/python -e '.[dev]'
.venv/bin/sentinel-server init && .venv/bin/sentinel-server add-trap T1 --lure CM --name Bench
.venv/bin/sentinel-server serve          # http://localhost:8000
```

Then run the device software with the fake camera ([docs/server-on-mac.md](docs/server-on-mac.md#try-it-without-a-pi)).
ESP32 cameras and the hub: [docs/esp32-traps.md](docs/esp32-traps.md). The server on a Pi or a cloud machine: [docs/server-on-linux.md](docs/server-on-linux.md). A Pi with its own camera: [docs/bring-up.md](docs/bring-up.md). Choosing between cameras: [docs/camera-bench.md](docs/camera-bench.md).

## What works today

- Pi camera trap (the first design; the plan is now ESP32 cameras through a hub): capture with locked focus/exposure/white balance, SHT45 + INA219 readings, offline queue, upload, next-wake scheduling (DST-safe), RTC alarm + power-off, "new liner" by power-button wake; focus-sweep tool. Tested on a Mac with the fake camera. On a Pi so far: capture and white-card calibration with the wide-angle IMX219 on a bench Pi 5 ([hardware/CAMERAS.md](hardware/CAMERAS.md)); **the full cycle has not yet run on the Pi**.
- Server: authenticated uploads (duplicate-safe), new-liner handling, lure masking, detection (OpenCV baseline that measures the liner grid for scale and removes grid lines; corrects wide/fisheye lens distortion by straightening the grid, estimated once per liner; on empty-liner photos, re-run Oct 6 2026: 1 false box on a grid crossing in the Oct 1 webcam photo, and 7 on the IMX219 photo, all on the trap walls outside the card; ignores everything off the card when the lens also sees the trap's walls; leaves out a photo that is blurred or whose scale disagrees with its liner's other photos; folds part-boxes into one box per insect; logs sharpness, glare, liner age and moon with each photo; flatbug adapter; our YOLO11 on overlapping tiles as `SENTINEL_DETECTOR=yolo`), `sentinel-server detect` overlays for bench checks, tracking so each insect counts once (confirmed after 2 photos; species voted only from its first 72 hours on the glue), review queue with confirm/relabel/reject, BE degree days, NEWA sustained-catch biofix, pest milestones, dashboard pages.
- ML ([ml/README.md](ml/README.md)): training set from AMI and iNaturalist, trap-style synthetic photos and, since Oct 7 2026, 2,309 real insects cropped from liner photos (other people's OFM, CM and potato tuber moth liners, and our own field cards with species read from the photos, not yet checked by an entomologist); v1 classifier (BioCLIP 2 features + logistic regression, its settings and confidence scale tuned on real-liner crops): on liners and cards it never trained on it finds 94% of 162 OFM, 92% of 37 CM, 92% of 97 non-target moths, and on held-out field cards 18 of 19 OFM, 10 of 10 CM and 14 of 14 OBLR, at 7–15 px/mm; trained and scored from the `ml/` scripts, and switched on (`SENTINEL_CLASSIFIER=bioclip-v1`) on the Pi 5 server since Oct 22 2026, though not yet scored on our own camera's photos; three fine-tuned v2 CNNs (EfficientNet-B0, ConvNeXt-T, MobileNetV3-L; Oct 8 2026, on a CUDA PC) that match v1 on the 785 held-out real-liner crops overall (0.87–0.90 right against 0.89) but find only 3–6 of the 19 OFM on the held-out field card, against v1's 18, and are wrong at ≥ 0.80 3–5 times as often, so v1 stays the classifier; a YOLO11 detector (Oct 8 2026, 31 training photos, the same 4 test photos of other people's liners: mAP50 0.51, moth precision 0.79 and recall 0.74 at its chosen confidence, debris 0 of 13; no better than the Oct 7 run on half the photos), usable in the model playground and as a server detector, not yet tried on a target-size moth from our own camera; a browser labeller for field cards and liner photos; baseline and flatbug detectors scored on other people's labelled liner photos, the classifier scored on field-card crops as moth / other insect / debris.
- ESP32 camera traps through a hub ([docs/esp32-traps.md](docs/esp32-traps.md)): the hub, a Pi with no camera running the gateway always on (`install-hub.sh`), takes photos from ESP32-S3 camera boards in Wi-Fi range and uploads them under each camera's own trap, with each camera's own key. Hubs and cameras are added and removed on the dashboard (**Set up traps**); the hub learns its cameras from the server and checks in every 30 s, so the dashboard shows whether it is online. The firmware queues photos in flash, keeps its own time against the hub's and corrects for its clock drift. Setup mode streams a live preview from the camera for 2 min after power-on (or BOOT held 3 s), listed on the hub's page, for aiming it; **Take a photo now** on a camera's dashboard page reaches it at its next check-in with the hub (every 30 min between photos). Both compile and are tested in the gateway and server code, not yet on the board. Bench runs over real Wi-Fi: Oct 8 2026 (an ESP32-S3 with an OV3660 on RedRover, through the bench Pi, to a server on the Mac) and Oct 22 2026 (the same ESP32 through the bench Pi as a camera-less hub, `apple-pi-hub`, to the Pi 5 server, `apple-pi-server`, with the v1 classifier; about 10 s awake per wake). Not yet tested: the hub on cellular, the node on the hub's own access point, clock-drift correction over real sleeps, deep-sleep current, and range in an orchard.
- Dashboard: an orchard view (traps reporting, this week's CM/OFM/OBLR across all traps, 30-day chart for the whole orchard, each hub and when it last checked in) above the per-trap table; each trap's page and a page of all its photos.
- Review: the queue also shows one in ten labels the model was sure of (a spot check, scored on the trap page), and the trap page says when a biofix rests on catches nobody has confirmed.
- Automated tests for device, server and ml, run on every pull request ([.github/workflows/tests.yml](.github/workflows/tests.yml)), plus an end-to-end run with the fake camera ([docs/server-on-mac.md](docs/server-on-mac.md#try-it-without-a-pi)). Re-run Oct 10 2026 after fixing how the grid finder settles on one spacing (6 cycles, 3 moths on the fake liner): all 6 photos read 11.5–11.6 px/mm (true: 11.6) and were used, and 2 moths were confirmed; the third lies across one of them (centres 32 px apart) and is counted with it. Before the fix the same run read 6.9–29 px/mm and confirmed 1 of 6.

## Not done yet

ArUco alignment in the pipeline · white-card calibration for the LED's new position · a diffuser for the LED (10–13% of the card is blown out) · finishing the OFM liner labels (454 boxes) ·
accuracy on our own trap's photos, on locked test cards ([docs/evaluation.md](docs/evaluation.md)) · an entomologist's check of the field-card species and of the 454 pass-1 labels Claude added · a second source of OFM on glue (every CNN learnt the one trap camera's OFM) ·
the hub on cellular, and its own access point for the cameras · a cloud server (8 GB; [docs/server-on-linux.md](docs/server-on-linux.md)) with a domain and HTTPS ·
dashboard settings page for `device_config` · alerts (including "hub offline") · Postgres/Docker for the real server.

What the insect-monitoring literature says works and fails, and what this repo does about each point, including what could not be done yet: [docs/cv-research-status.md](docs/cv-research-status.md) (imaging, detection, counting) and [docs/ml-research-status.md](docs/ml-research-status.md) (data, classification, evaluation).

## Known problems (audit, Oct 10 2026)

Fixed since the audit: the biofix now comes from the current season's catches only; the worker survives a
failed save and a failed pass, and (since Oct 22 2026) classifies before writing anything, so uploads are no
longer locked out of the database while BioCLIP runs on the Pi's CPU; a photo goes on the liner that was in
the trap when it was taken, and a late one has its liner re-run in order; an ESP32 that loses the hub keeps
to the hub's daily times, or looks for it every 30 min without photos (firmware 0.2.2); the built-in schedule
is the example config's six wakes a day, so the trap's own sensor gives degree days (ESP32 traps have no
sensor and need the NEWA import); re-running a liner (`sentinel-server reprocess`, or a late photo) classifies
every photo before writing, so it doesn't lock uploads out either (Oct 22 2026).

- The scale check trusts a liner's first photos: a liner whose first photos are misread rejects its correct ones. Fixed for cameras whose scale is set (`sentinel-server set-scale T2 10.3`, Oct 24 2026): their photos are checked against the camera instead. A camera without one still has the problem.
- The grid finder still misreads our IMX219 photos with insects on the card: 5 of 10 calibrated photos with pinned specimens read 32–63 px/mm instead of 15.3 (Oct 10 2026; all 5 of the empty liner read right). See [hardware/CAMERAS.md](hardware/CAMERAS.md).
