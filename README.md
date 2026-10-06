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
- Server: authenticated uploads (duplicate-safe), new-liner handling, lure masking, detection (OpenCV baseline that measures the liner grid for scale and removes grid lines; corrects wide/fisheye lens distortion by straightening the grid, estimated once per liner; 0 false detections on real empty-liner photos from the USB webcam and a wide lens; flatbug adapter), `sentinel-server detect` overlays for bench checks, tracking so each insect counts once (confirmed after 2 photos), review queue with confirm/relabel/reject, BE degree days, NEWA sustained-catch biofix, pest milestones, dashboard pages.
- ML ([ml/README.md](ml/README.md)): training set from AMI and iNaturalist plus trap-style synthetic photos; v1 classifier (BioCLIP 2 features + logistic regression) and v2 (fine-tuned EfficientNet-B0); a browser labeller for field cards and liner photos; baseline and flatbug detectors scored on other people's labelled liner photos, the classifier scored on field-card crops.
- Automated tests for device, server and ml, run on every pull request ([.github/workflows/tests.yml](.github/workflows/tests.yml)), plus an end-to-end run: 6 fake-camera cycles → 3 moths detected, 2 confirmed, 1 candidate, which matches the fake camera's ground truth.

## Not done yet

ArUco alignment in the pipeline · ignoring everything outside the card (the IMX219 sees the trap walls) · white-card calibration for the LED's new position ·
accuracy on our own trap's photos, on locked test cards ([docs/evaluation.md](docs/evaluation.md)) ·
dashboard settings page for `device_config` · alerts · Postgres/Docker for the real server.
