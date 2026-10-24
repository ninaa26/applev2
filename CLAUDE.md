# Orchard Sentinel

Camera in a pheromone delta trap: photographs the sticky liner, counts codling moth (CM), oriental
fruit moth (OFM) and obliquebanded leafroller (OBLR), and derives NEWA biofix and degree-day timings.
Cornell capstone, fall 2026. Start with [README.md](README.md); details live in `docs/`, `ml/README.md`
and `hardware/CAMERAS.md`.

## Layout

- `device/`: Raspberry Pi package `sentinel_device`: the hub gateway for the ESP32 cameras (`gateway.py`, `install-hub.sh`), and the Pi camera trap (capture, queue, upload, wake scheduling, bench tools); `device/esp32-node/` is the ESP32-S3 camera firmware (PlatformIO)
- `server/`: FastAPI + SQLite package `sentinel_server` (upload API, detect/track/classify pipeline, dashboard, `evaluate`)
- `ml/`: standalone scripts run from inside `ml/` (fetch, build dataset, label, train, score); no package
- `hardware/`: trap dimensions, camera notes, printable parts
- `field-tests/`: self-contained test runs on the real hardware, separate from the regular code (e.g. `esp32-window-day/`: scripts to start, check, fail, finish and report a day-long run; run output goes to its gitignored `runs/`)
- `code-review/`: the review ledger. `LEDGER.md` holds checked findings (to-dos, facts, wrong claims); `UNVERIFIED.md` holds Gemini claims nobody has checked yet. `gemini-raw/` has the raw Gemini output, and `gemini-upload/` has the brief and the read-only live-snapshot scripts. Rebuild the page with `python3 code-review/make_unverified.py && python3 code-review/build_ledger.py`
- `docs/`: ESP32 traps and the hub, server on Linux (the Pi 5) or the Mac, Pi camera bring-up, wiring, camera bench, measuring accuracy

## Environments and tests

Each of `server/`, `device/` and `ml/` has its own `.venv` (Python 3.12, made with `uv`). Use that
folder's `.venv/bin/python`, not the system Python.

```bash
cd server && .venv/bin/python -m pytest -q            # about a minute
cd device && .venv/bin/python -m pytest -q            # camera-bench tests skip without OpenCV
cd ml && .venv/bin/python -m unittest discover tests
```

CI runs the same three suites on every pull request (`.github/workflows/tests.yml`).

The labeller and model playground are preview servers in `.claude/launch.json`
(`field-labeler`, `ofm-labeler`, `model-playground`).

## Conventions

- Work on a branch and merge to `master` by pull request. Commit subjects start with the area: `Device:`, `Server:`, `ML:`, `Docs:`.
- Photos, datasets, model weights and run outputs are gitignored (`ml/data/`, `ml/models/`, `server/data/`, `device/data/`, `*.pt`). The scripts and READMEs are the record of how they were made, so keep them in step.
- Class labels everywhere: `CM`, `OFM`, `OBLR`, `other_moth`, `other_insect`, `debris`.
- Measured results go in the READMEs with their date and what they were measured on.
- Dataset, labelling and result-reporting rules for `ml/` are in `.claude/rules/ml.md`, loaded when files under `ml/` are in play.
- Camera settings and the white-card correction (`flatfield.npz`) belong to one Pi, camera position and lighting setup. Redo the calibration when any of them changes.
- How it runs (since Oct 22 2026): ESP32 cameras → hub Pi with no camera (`apple-pi-hub`, the bench Pi; gateway only) → server on a Pi 5 (`apple-pi-server`, a stand-in for a cloud server). Both are on the team Tailscale.
- The bench Pi is shared. Ask before running anything on it, and do not run `device/install.sh` there.
