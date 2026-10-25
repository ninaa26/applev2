"""trained_on.json: what a model was made from, written next to it by train_v1.py, train_v2.py and train_yolo.py.

metrics.json says how well a model did; this says on what. With more than one version of the trap-style fakes
(data/trap_style/<version>/), the held-out lists in git and the dataset rebuilt now and then, a model folder
on its own can't tell you which of them it saw.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import paths

HERE = Path(__file__).resolve().parent
TRAP_STYLE_IN_PATH = re.compile(rf"{paths.TRAP_STYLE}/([^/]+)/")


def git_commit() -> str:
    """HEAD's hash, with "+changes" when the working tree differs from it (the run used uncommitted code)."""
    try:
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "."], cwd=HERE, capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return head + ("+changes" if dirty else "")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def summary(data: Path, base_model: str, dataset: Path | None = None, rows: list[dict] | None = None,
            **extra) -> dict:
    """`dataset` is the csv the model read (fingerprinted); `rows` the rows it used (counted by source, split
    and trap-style version). Anything in `extra` (photo lists, settings) is stored as given."""
    held = data / paths.HELD_OUT
    out: dict = {
        "trained": datetime.now(UTC).isoformat(timespec="seconds"),
        "command": " ".join([Path(sys.argv[0]).name, *sys.argv[1:]]),
        "git_commit": git_commit(),
        "base_model": base_model,
        "held_out_lists": {p.name: paths.held_out_list(data, p.name) for p in sorted(held.glob("*.txt"))},
    }
    if dataset is not None and dataset.exists():
        out["dataset"] = {"path": str(dataset), "sha256": sha256(dataset)}
        if rows is None:
            with open(dataset, newline="") as f:
                rows = list(csv.DictReader(f))
    if rows is not None:
        out["rows"] = len(rows)
        out["by_source_and_split"] = dict(sorted(Counter(f"{r.get('source', '?')} {r.get('split', '?')}"
                                                         for r in rows).items()))
        versions = Counter(m.group(1) for r in rows if (m := TRAP_STYLE_IN_PATH.search(r.get("path", ""))))
        out["trap_style_versions"] = dict(versions)
    return out | extra


def write(folder: Path, info: dict) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "trained_on.json"
    path.write_text(json.dumps(info, indent=2) + "\n")
    return path
