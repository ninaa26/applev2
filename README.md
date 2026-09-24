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
ml/         training-data tools (AMI fetch) and model notes
hardware/   mockup trap template, 3D-printable camera mount + liner tray, calibration prints
docs/       bring-up, wiring, running the server on the Mac
```

## Quick start (no hardware needed)

```bash
cd server && uv venv --python 3.12 .venv && uv pip install -p .venv/bin/python -e '.[dev]'
.venv/bin/sentinel-server init && .venv/bin/sentinel-server add-trap T1 --lure CM --name Bench
.venv/bin/sentinel-server serve          # http://localhost:8000
```

Then run the device software with the fake camera ([docs/server-on-mac.md](docs/server-on-mac.md#try-it-without-a-pi)).
With the Pi and camera: [docs/bring-up.md](docs/bring-up.md).

## What works today

- Device cycle: capture with locked focus/exposure/white balance, SHT45 + INA219 readings, offline queue, upload, next-wake scheduling (DST-safe), RTC alarm + power-off, "new liner" by power-button wake; focus-sweep tool. Tested on a Mac with the fake camera; **not yet run on the Pi**.
- Server: authenticated uploads (duplicate-safe), new-liner handling, lure masking, detection (OpenCV baseline; flatbug adapter), tracking so each insect counts once (confirmed after 2 photos), review queue with confirm/relabel/reject, BE degree days, NEWA sustained-catch biofix, pest milestones, dashboard pages.
- 16 automated tests (device 6, server 10), plus an end-to-end run: 6 fake-camera cycles → 3 moths detected, 2 confirmed, 1 candidate, which matches the fake camera's ground truth.

## Not done yet

ArUco alignment and lens-distortion correction in the pipeline · BioCLIP/flatbug run on real photos · v1 classifier training ·
dashboard settings page for `device_config` · alerts · Postgres/Docker for the real server.
