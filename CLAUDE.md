# Orchard Sentinel

Camera in a pheromone delta trap: photographs the sticky liner, counts codling moth (CM), oriental
fruit moth (OFM) and obliquebanded leafroller (OBLR), and derives NEWA biofix and degree-day timings.
Cornell capstone, fall 2026. Start with [README.md](README.md); details live in `docs/`, `ml/README.md`
and `hardware/CAMERAS.md`.

## Layout

- `device/`: Raspberry Pi package `sentinel_device`: the hub gateway for the ESP32 cameras (`gateway.py`, `install-hub.sh`), and the Pi camera trap (capture, queue, upload, wake scheduling, bench tools); `device/esp32-node/` is the ESP32-S3 camera firmware (PlatformIO)
- `server/`: FastAPI + SQLite package `sentinel_server` (upload API, detect/track/classify pipeline, dashboard, `evaluate`)
- `ml/`: standalone scripts run from inside `ml/` (fetch, build dataset, label, train, score); no package. Folder names for `ml/data/` and `ml/models/` are in `ml/paths.py`; the map is `ml/data/README.md`
- `hardware/`: trap dimensions, camera notes, printable parts
- `field-tests/`: self-contained test runs on the real hardware, separate from the regular code (e.g. `esp32-window-day/`: scripts to start, check, fail, finish and report a day-long run; run output goes to its gitignored `runs/`)
- `docs/code-review/`: the review ledger. `LEDGER.md` holds checked findings (to-dos, facts, wrong claims); `UNVERIFIED.md` holds Gemini claims nobody has checked yet. `gemini-raw/` has the raw Gemini output, and `gemini-upload/` has the brief and the read-only live-snapshot scripts. Rebuild the page with `python3 docs/code-review/make_unverified.py && python3 docs/code-review/build_ledger.py`
- `docs/`: ESP32 traps and the hub, server on Linux (the Pi 5) or the Mac, Pi camera bring-up, wiring, camera bench, measuring accuracy

## Team conventions

How the team works (setting up, `make check`, branches and commit prefixes, data rules, the hardware,
deploying) is in CONTRIBUTING.md, imported here:

@CONTRIBUTING.md

## Claude-specific

- Run checks with `make check` (or one part, such as `make test-server`) from the repo root, or the
  per-folder commands it runs. Server tests take about a minute.
- The labeller, model playground and dashboard are preview servers in `.claude/launch.json`
  (`field-labeler`, `ofm-labeler`, `model-playground`, `server-dashboard`).
- `.claude/rules/ml.md` loads when files under `ml/` are in play.
- CI also runs CodeQL on the Python and the workflows, and Dependabot opens weekly PRs for the locked
  versions and monthly ones for the Actions.
