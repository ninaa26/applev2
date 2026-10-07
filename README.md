# Orchard Sentinel

A camera inside a pheromone delta trap that photographs its sticky liner, identifies and counts
codling moth, oriental fruit moth and obliquebanded leafroller, and turns the counts into the
biofix and degree-day timings from the NEWA guide. Cornell capstone, fall 2026.

Planning pages: [spec](https://claude.ai/artifact/GaBWYoqoXfmxyqFotrfH41) ·
[architecture](https://claude.ai/artifact/2WRtPNZk5ZcjBQNcR3oqus) ·
[build plan & tracker](https://claude.ai/artifact/VYyBzxuE8YnGAWV8XVyej5)

```
device/     Raspberry Pi 5 software: wake → LED → photo → queue → upload → set RTC alarm → power off
server/     FastAPI + SQLite (Postgres later): upload API, detection/tracking/counting worker, dashboard
ml/         training photos (AMI, iNaturalist, trap-style synthetic), labelling tool, detector and classifier training and scoring
hardware/   trap dimensions (TRAP.md), mockup trap template, 3D-printable camera mount + liner tray, calibration prints
docs/       bring-up, wiring, running the server on the Mac, camera bench test, measuring accuracy
```

## Quick start (no hardware needed)

```bash
cd server && uv venv --python 3.12 .venv && uv pip install -p .venv/bin/python -e '.[dev]'
.venv/bin/sentinel-server init && .venv/bin/sentinel-server add-trap T1 --lure CM --name Bench
.venv/bin/sentinel-server serve          # http://localhost:8000
```

Then run the device software with the fake camera ([docs/server-on-mac.md](docs/server-on-mac.md#try-it-without-a-pi)).
With the Pi and camera: [docs/bring-up.md](docs/bring-up.md). Choosing between cameras: [docs/camera-bench.md](docs/camera-bench.md).

## What works today

- Device cycle: capture with locked focus/exposure/white balance, SHT45 + INA219 readings, offline queue, upload, next-wake scheduling (DST-safe), RTC alarm + power-off, "new liner" by power-button wake; focus-sweep tool. Tested on a Mac with the fake camera. On a Pi so far: capture and white-card calibration with the wide-angle IMX219 on a bench Pi 5 ([hardware/CAMERAS.md](hardware/CAMERAS.md)); **the full cycle has not yet run on the Pi**.
- Server: authenticated uploads (duplicate-safe), new-liner handling, lure masking, detection (OpenCV baseline that measures the liner grid for scale and removes grid lines; corrects wide/fisheye lens distortion by straightening the grid, estimated once per liner; on empty-liner photos, re-run Oct 6 2026: 1 false box on a grid crossing in the Oct 1 webcam photo, and 7 on the IMX219 photo, all on the trap walls outside the card; ignores everything off the card when the lens also sees the trap's walls; leaves out a photo that is blurred or whose scale disagrees with its liner's other photos; folds part-boxes into one box per insect; logs sharpness, glare, liner age and moon with each photo; flatbug adapter; our YOLO11 on overlapping tiles as `SENTINEL_DETECTOR=yolo`), `sentinel-server detect` overlays for bench checks, tracking so each insect counts once (confirmed after 2 photos; species voted only from its first 72 hours on the glue), review queue with confirm/relabel/reject, BE degree days, NEWA sustained-catch biofix, pest milestones, dashboard pages.
- ML ([ml/README.md](ml/README.md)): training set from AMI and iNaturalist plus trap-style synthetic photos; v1 classifier (BioCLIP 2 features + logistic regression), trained and scored from the `ml/` scripts but not yet switched on in the server (it runs with no species ID); a v2 training script (fine-tuned EfficientNet-B0) that has not been run; a YOLO11 detector with its first held-out score (Oct 7 2026, 4 test photos of other people's liners: mAP50 0.52, moth 0.82, debris not found), usable in the model playground and as a server detector, not yet tried on a target-size moth from our own camera; a browser labeller for field cards and liner photos; baseline and flatbug detectors scored on other people's labelled liner photos, the classifier scored on field-card crops as moth / other insect / debris.
- Automated tests for device, server and ml, run on every pull request ([.github/workflows/tests.yml](.github/workflows/tests.yml)), plus an end-to-end run: 6 fake-camera cycles → 3 moths detected, 2 confirmed, 1 candidate, which matches the fake camera's ground truth.

## Not done yet

ArUco alignment in the pipeline · white-card calibration for the LED's new position · a diffuser for the LED (10–13% of the card is blown out) · finishing the OFM liner labels (454 boxes) ·
accuracy on our own trap's photos, on locked test cards ([docs/evaluation.md](docs/evaluation.md)) ·
dashboard settings page for `device_config` · alerts · Postgres/Docker for the real server.

What the insect-monitoring literature says works and fails, and what this repo does about each point, including what could not be done yet: [docs/cv-research-status.md](docs/cv-research-status.md) (imaging, detection, counting) and [docs/ml-research-status.md](docs/ml-research-status.md) (data, classification, evaluation).
