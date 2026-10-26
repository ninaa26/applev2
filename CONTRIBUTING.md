# Working on Orchard Sentinel

How the team works in this repo. Start with the [README](README.md) for what the project is and
[docs/](docs/README.md) for setting up and running the hardware.

## Set up a clone

Each of `server/`, `device/` and `ml/` is its own Python project with its own `.venv` (Python 3.12,
made with [uv](https://docs.astral.sh/uv/)). Use that folder's `.venv/bin/python`, not the system
Python.

```bash
make setup                 # server/.venv and device/.venv at the versions in uv.lock
uvx pre-commit install     # once: runs Ruff and checks for large files and keys before each commit
```

`server/` and `device/` lock every package in `uv.lock`. After changing a `pyproject.toml`, run
`uv lock` in that folder and commit both files. `ml/` uses `requirements.txt` (see
[ml/README.md](ml/README.md)).

## Check your work

```bash
make check       # what CI runs: Ruff, mypy, and the server, device and ml tests (a few minutes)
make test-server # or one part: lint, types, test, test-server, test-device, test-ml
```

The device's camera-bench tests need OpenCV, which `make setup` installs (the `bench` extra).

## Branches, commits and pull requests

- Work on a branch and merge to `master` by pull request. `master` is protected: a PR can merge
  once the `lint`, `server`, `device` and `ml` checks pass (and `types` should pass too, though
  branch protection doesn't require it yet). No approval is required, but
  ask the other person to look at anything that changes how the traps or the server behave.
- Start each commit subject with the area: `Server:`, `Device:`, `ML:`, `Docs:` or `CI:`
  (`Server, Device:` when it spans two).
- Fill in the PR template: what changed, how you checked it, and what you didn't test (for
  example "not run on the Pis").
- Merged branches are deleted on GitHub automatically.

## Data and results

- What is where in the ML data and models: [ml/data/README.md](ml/data/README.md). Which photos are held out
  from training is in git, in `ml/data/training/held_out/`.
- Photos, datasets, model weights and run outputs are gitignored (`ml/data/`, `ml/models/`,
  `server/data/`, `device/data/`, `*.pt`, firmware `.bin` files). The scripts and READMEs are the
  record of how they were made, so keep them in step.
- Class labels everywhere: `CM`, `OFM`, `OBLR`, `other_moth`, `other_insect`, `debris`.
- Measured results go in the READMEs with their date and what they were measured on.
- Dataset, labelling and result-reporting rules for `ml/` are in
  [.claude/rules/ml.md](.claude/rules/ml.md).

## The hardware

- How it runs (since Oct 22 2026): ESP32 cameras → hub Pi with no camera (`apple-pi-hub`, the bench
  Pi; gateway only) → server on a Pi 5 (`apple-pi-server`, a stand-in for a cloud server). Both are
  on the team Tailscale.
- The bench Pi is shared. Ask before running anything on it, and don't run `device/install.sh`
  there.
- Camera settings and the white-card correction (`flatfield.npz`) belong to one Pi, camera position
  and lighting setup. Redo the calibration when any of them changes.

## Deploying

| What | How | Tag it leaves |
|---|---|---|
| Server | `server/deploy.sh` from the Mac, on the merged commit | `server-<date>-<time>` |
| A hub | `device/deploy-hub.sh pi@<hub>` | `hub-<hub>-<date>-<time>` |
| Camera firmware | raise `FW_VERSION` in `src/main.cpp`, build with `device/esp32-node/release.sh`, upload on the dashboard (Set up traps → Camera firmware) | `fw-<version>` |

All three go back to the old version by themselves if the new one doesn't come up
([docs/esp32-traps.md](docs/esp32-traps.md#fixing-and-updating-in-the-field)). Tags are pushed to
GitHub only for commits on `master`, so `git tag -l 'server-*'` lists what the server ran and when,
and `git diff server-A server-B` shows what changed between two deploys.

## Security

Report a vulnerability privately as described in [SECURITY.md](SECURITY.md).
