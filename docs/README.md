# Docs

What each page is for. How the team works (branches, checks, deploying) is in
[CONTRIBUTING.md](../CONTRIBUTING.md); model training is in [ml/README.md](../ml/README.md).

## Setting up and running

| Page | For |
|---|---|
| [esp32-traps.md](esp32-traps.md) | ESP32 camera traps and the hub they send through: adding them, firmware, fixing and updating in the field |
| [server-on-linux.md](server-on-linux.md) | The server on the Pi 5 (and later a cloud machine): install, Tailscale, backups and restoring |
| [server-on-mac.md](server-on-mac.md) | The server on the team Mac, and trying everything without a Pi |
| [bring-up.md](bring-up.md) | A Pi with its own camera, from a blank card to photos on the dashboard (the first design, and the bench rig) |
| [wiring.md](wiring.md) | Wiring one trap unit |

## Checking it works

| Page | For |
|---|---|
| [evaluation.md](evaluation.md) | Measuring the pipeline's counts against a person's, with `sentinel-server evaluate` |
| [camera-bench.md](camera-bench.md) | Comparing cameras on the same printed checkerboard |

## Background

These are records, each dated at its top, not instructions to follow.

| Page | For |
|---|---|
| [cv-research-status.md](cv-research-status.md) | What the imaging, detection and counting literature says, and what the repo did about each point (as of Oct 8 2026) |
| [ml-research-status.md](ml-research-status.md) | The same for data, classification and evaluation (as of Oct 8 2026) |
| [backend-practices.md](backend-practices.md) | Python backend and GitHub repo practices, each checked against this repo, with what's done |
| [security-and-privacy.md](security-and-privacy.md) | Threat model, the standards that apply, what's done and what to change before growers use it (as of Oct 25 2026) |
| [code-review/](code-review/) | The review ledger: checked findings from the code reviews, and the raw review output |
