# Architecture Review & Modernization Plan: Orchard Sentinel Monorepo

## 1. Current State

The current repository reflects a classic stage of multi-disciplinary student prototype growth: functional domain code spanning backend, edge robotics, embedded firmware, and computer vision, but fragmented by disconnected tooling and missing boundary contracts.

* **Environment & Package Fragmentation:** `server/` and `device/` maintain isolated `pyproject.toml` files using legacy `setuptools` backends and flat source layouts without a root coordinator. `ml/` is not a Python package at all—it relies on loose scripts and split requirements (`requirements.txt`, `requirements-train.txt`).
* **Non-Deterministic CI:** No `uv.lock` exists in source control. The GitHub Actions workflow (`tests.yml`) calls `uv run --no-project --python 3.12 --with-editable` or ad-hoc `--with` arguments on every run, re-resolving dependency trees dynamically from PyPI on every commit.
* **Ignored Embedded Stack in CI:** The ESP32-S3 firmware in `device/esp32-node/` has no continuous integration. Pull requests can silently break C++ compilation. There are no host-side native unit tests for embedded parsing or logic.
* **Absence of Shared Schemas:** The communication payload between the ESP32 node, Raspberry Pi gateway (`sentinel_device/gateway.py`), and FastAPI backend (`sentinel_server/`) is implicitly coupled. Changes to endpoint JSON payloads require manually synchronized edits across C++ and Python files.
* **Ad-Hoc Quality Control & Config:** Linting, code formatting, and static typing are completely unconfigured (no Ruff, no Mypy/Pyright, no `pre-commit`). Configuration is scattered across unvalidated files (`.env.example`, `config.example.toml`, `hub.example.toml`, `node_config.example.h`).
* **Unstructured ML & Assets:** `ml/` contains 19 root-level scripts with hardcoded model weights (`.pt` files excluded only via `.gitignore`). There is no dataset lineage tracking, parameter configuration system, or experiment versioning.
* **Flat Documentation & Repository Governance:** `docs/` is a flat folder mixing hardware wiring, bring-up instructions, and ML research notes. There is no `CODEOWNERS` file or automated dependency update automation (Dependabot/Renovate).

---

## 2. What Professionals Do (with URLs)

### Monorepo Workspaces, `src/` Layout, and Lockfiles
Professional multi-project Python repositories leverage [Astral uv Workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/) to unify all sub-projects under a single repository-level `pyproject.toml`. Instead of maintaining multiple disconnected virtual environments, `uv` computes a single, globally resolvable [committed `uv.lock`](https://docs.astral.sh/uv/concepts/projects/dependencies/#the-lockfile), while keeping local packages editable and independently deployable. 

Professional libraries and applications universally adopt the [src layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/) (e.g., `src/sentinel_server/`). Placing packages inside a `src/` subdirectory prevents accidental imports against dirty root working directories during test execution and guarantees that test suites run against the installed package distribution.

### Shared Contracts: Pydantic, JSON Schema, and Protobuf
In IoT and edge-to-cloud systems, teams eliminate duplicate schema definitions through shared protocol packages:
* **Python Edge to Python Cloud:** Internal workspace packages (e.g., `packages/protocol`) expose shared [Pydantic](https://docs.pydantic.dev/) models utilized by both FastAPI and edge client daemons.
* **Microcontroller to Cloud (ESP32 <-> Python):** Teams either compile binary contracts with [Protocol Buffers](https://protobuf.dev/) using [Nanopb](https://jpa.kapsi.fi/nanopb/) on the microcontroller and standard protobuf bindings in Python, or share data models by generating [JSON Schema](https://json-schema.org/) from Pydantic models to validate payloads parsed by [ArduinoJson](https://arduinojson.org/) on the ESP32.

### Code Hygiene: Ruff, Static Typing, and Pre-Commit
Modern high-velocity teams replace disparate tools (Flake8, Black, isort) with [Ruff](https://docs.astral.sh/ruff/), running linting and formatting in tens of milliseconds. Strict typing is enforced via [Pyright](https://microsoft.github.io/pyright/) or [Mypy](https://mypy.readthedocs.io/) across CI pipelines. [pre-commit](https://pre-commit.com/) runs these checks locally prior to git commits, preventing syntax, typing, and formatting failures before hitting remote CI runners.

### CI Matrix, PlatformIO Builds, and Native Unit Testing
Production monorepos use GitHub Actions with a matrix strategy to test modules concurrently. By using the official [astral-sh/setup-uv](https://github.com/astral-sh/setup-uv) action with `enable-cache: true` and running `uv sync --frozen`, dependencies install in seconds without external network flakiness.

Firmware is tested automatically using [PlatformIO GitHub Actions CI](https://docs.platformio.org/en/latest/integration/ci/github-actions.html) with cached toolchains (`~/.platformio/.cache`). Furthermore, teams decouple hardware drivers from embedded business logic, running unit tests on the native x86/ARM host runner via [PlatformIO Native Unit Testing (`pio test -e native`)](https://docs.platformio.org/en/latest/advanced/unit-testing/index.html) using frameworks like Unity or GoogleTest.

### Firmware Versioning and Continuous Delivery
Firmware binaries are versioned following [Semantic Versioning (SemVer)](https://semver.org/). Build numbers and Git commit SHAs are dynamically injected at compile time via PlatformIO dynamic build flags (`build_flags = -DAPP_VERSION=\"...\"`). Stable tags automatically trigger GitHub Actions to compile and attach release binaries (`firmware.bin`, `bootloader.bin`, `partitions.bin`) directly to [GitHub Releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases) for Over-The-Air (OTA) flashing.

### Config Management and 12-Factor Design
Hardcoded TOML and C header files are replaced by [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/). Pydantic Settings dynamically reads and validates configuration from environment variables and `.env` files with strict runtime type casting, failing fast at application boot when required keys are missing or malformed.

### Data Science & ML Conventions
Industrial ML projects follow structured conventions like [Cookiecutter Data Science (CCDS)](https://cookiecutter-data-science.drivendata.org/), cleanly separating data pipelines (`data/raw/` immutable, `data/processed/`), reusable model code (`src/`), and exploratory notebooks. Large training artifacts and datasets are decoupled from Git using [Data Version Control (DVC)](https://dvc.org/doc/start), which stores data hashes in Git and offloads binary blobs to cloud remotes (S3/GCS). Instead of ad-hoc script flags, experiment parameters are configured declaratively using [Hydra](https://hydra.cc/) or YAML config files.

### Repository Governance and Diataxis Documentation
* **Maintenance & Governance:** Multi-language monorepos use [Renovate](https://docs.renovatebot.com/) over Dependabot because of its native support for `uv` workspaces and customizable regex managers for `platformio.ini` dependencies. Code review ownership is codified with [GitHub CODEOWNERS](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners).
* **Documentation Architecture:** Documentation is categorized using the [Diátaxis Framework](https://diataxis.fr/) into Tutorials, How-To Guides, Technical Reference, and Explanations. Major design decisions and architectural trade-offs are preserved through [Architecture Decision Records (ADRs)](https://adr.github.io/).

---

## 3. Recommended Reorganization and Tooling Changes

### Priority 1: Foundation & Deterministic CI (Effort: S)
1. **Root `uv` Workspace:** Create a virtual workspace root `pyproject.toml` grouping `apps/*`, `packages/*`, and `ml/`. Run `uv lock` and commit `uv.lock`.
2. **Deterministic CI Workflows:** Update `.github/workflows/ci.yml` using `astral-sh/setup-uv` with `enable-cache: true`. Replace ad-hoc installation flags with `uv sync --frozen --all-packages` and matrix-scoped test runs.
3. **PlatformIO CI Job:** Add a build step in CI running `pio run` on `device/esp32-node/` with `~/.platformio/.cache` action caching to guarantee firmware builds never break unexpectedly.
4. **Code Quality Baseline:** Add root `ruff` configuration (lint + format) and `.pre-commit-config.yaml` to enforce standards across Python modules.
5. **Governance:** Add `.github/CODEOWNERS` mapping embedded, server, ML, and CAD areas to respective team members, and configure `renovate.json` for monorepo dependency PRs.

### Priority 2: Architecture & Contracts (Effort: M)
6. **Shared Protocol Package (`packages/protocol`):** Extract API payloads and telemetry structures into a dedicated workspace package. Generate JSON schemas for the ESP32 node and use shared Pydantic models between `apps/device` and `apps/server`.
7. **Migrate to `src/` Layout:** Relocate `server/sentinel_server/` to `apps/server/src/sentinel_server/` and `device/sentinel_device/` to `apps/device/src/sentinel_device/`.
8. **Adopt `pydantic-settings`:** Standardize server and device configuration parsing onto `BaseSettings`, validating environment variables with `.env` support.
9. **Native Firmware Unit Testing:** Separate hardware drivers from state machine / protocol serialization logic in `esp32-node`, adding desktop-executable unit tests via `pio test -e native`.
10. **Static Type Checking:** Add `pyright` or `mypy` checks to pre-commit and CI matrix for `apps/server`, `apps/device`, and `packages/protocol`.

### Priority 3: ML Engineering, Firmware Releases, & Docs (Effort: M–L)
11. **Package ML Codebase:** Convert `ml/` into a standard workspace package (`apps/ml` or `packages/ml`) with a `pyproject.toml` supporting GPU optional dependencies (`[project.optional-dependencies] cuda = [...]`). Reorganize scripts into modular datasets, training, and evaluation pipelines (CCDS pattern).
12. **DVC Asset Management (Effort: M):** Track dataset versions and `.pt` model weights with DVC backed by cloud storage (S3/GCS), eliminating untracked binary dependencies.
13. **Experiment Configuration (Effort: S):** Replace ad-hoc script constants with YAML/Hydra configuration files for reproducible hyperparameter tracking.
14. **Firmware Release Automation (Effort: M):** Automate SemVer tagging via Git tags and configure CI to attach compiled `firmware.bin` binaries to GitHub Releases for field deployment.
15. **Diataxis & ADR Documentation Restructuring (Effort: S):** Reorganize `docs/` into Diátaxis quadrants (`tutorials/`, `how-to/`, `reference/`, `explanation/`) and establish `docs/adr/` for key technical decisions.

---

## 4. Proposed Target Directory Tree

```text
orchard-sentinel/
├── .github/
│   ├── CODEOWNERS
│   └── workflows/
│       ├── ci.yml                 # Matrix: ruff, mypy, pytest (server/device/ml), pio run/test
│       └── release-firmware.yml   # Builds & uploads firmware.bin to GitHub Releases on tag
├── .pre-commit-config.yaml        # Ruff lint/format, check-yaml, validate-pyproject
├── renovate.json                  # Monorepo dependency management
├── pyproject.toml                 # Root virtual workspace & shared tool config (ruff, mypy)
├── uv.lock                        # Single unified lockfile for all Python packages
│
├── apps/
│   ├── server/                    # FastAPI backend application
│   │   ├── pyproject.toml         # Member package
│   │   ├── src/
│   │   │   └── sentinel_server/   # Server application code
│   │   └── tests/
│   │
│   └── device/                    # Raspberry Pi hub & camera trap daemon
│       ├── pyproject.toml         # Member package
│       ├── systemd/               # Service unit files
│       ├── src/
│       │   └── sentinel_device/   # Capture cycles, gateway, camera bench
│       └── tests/
│
├── firmware/
│   └── esp32-node/                # ESP32-S3 PlatformIO firmware
│       ├── platformio.ini         # Includes [env:node] and [env:native]
│       ├── partitions.csv
│       ├── include/
│       ├── src/                   # C++ application source
│       └── test/                  # pio test -e native (host-compiled Unity/GTest unit tests)
│
├── packages/
│   └── protocol/                  # Shared communication contracts
│       ├── pyproject.toml         # Workspace library package
│       ├── schemas/               # Generated JSON schemas or .proto definitions
│       ├── src/
│       │   └── sentinel_protocol/ # Shared Pydantic models for Pi <-> Server payloads
│       └── tests/
│
├── ml/                            # Machine learning & computer vision
│   ├── pyproject.toml             # Member package with optional GPU extras
│   ├── configs/                   # Hydra / YAML experiment configurations
│   ├── data/                      # DVC-tracked dataset pointers (.dvc)
│   ├── models/                    # DVC-tracked model checkpoints (.dvc)
│   ├── notebooks/                 # Exploratory Jupyter notebooks
│   ├── src/
│   │   └── sentinel_ml/           # Modular data processing, training, and evaluation
│   └── tests/
│
├── hardware/                      # Mechanical and electrical engineering assets
│   ├── cad/                       # OpenSCAD models (camera_mount, liner_tray)
│   ├── schematics/                # Trap schematics and wiring diagrams
│   └── calibration/               # Print targets (checkerboard, tray markers)
│
├── field-tests/                   # Endurance and multi-day field validation scripts
│   └── esp32-window-day/
│
└── docs/                          # Diataxis structured documentation
    ├── adr/                       # Architecture Decision Records
    ├── tutorials/                 # Getting started and hardware assembly
    ├── how-to/                    # Deployment on Linux/Mac, camera bring-up, flashing
    ├── reference/                 # API schema, pinouts, wiring specifications
    └── explanation/               # Computer vision pipelines, phenology math, optical design
```
