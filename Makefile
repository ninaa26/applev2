# The checks CI runs (.github/workflows/tests.yml), from the repo root in one step.
#   make check     everything below
#   make lint      Ruff over the whole repo
#   make types     mypy for server/ and device/
#   make test      the server, device and ml test suites
#   make setup     make server/.venv and device/.venv at the locked versions (once, and after uv.lock changes)
# Each package keeps its own environment, so these just run the per-folder commands in turn.

.PHONY: check lint types test test-server test-device test-ml setup

check: lint types test

lint:
	uvx ruff@0.17.2 check .

types: setup
	cd server && uv run --no-sync mypy
	cd device && uv run --no-sync mypy

test: test-server test-device test-ml

test-server: setup
	cd server && uv run --no-sync pytest -q

test-device: setup
	cd device && uv run --no-sync pytest -q

test-ml:
	cd ml && uv run --no-project --python 3.12 --with numpy --with pillow python -m unittest discover tests

setup:
	cd server && uv sync --locked --python 3.12 --extra dev -q
	cd device && uv sync --locked --python 3.12 --extra dev --extra bench -q
