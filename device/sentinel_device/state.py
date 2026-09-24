"""Small JSON state file that survives shutdowns (last config from server, expected wake)."""

from __future__ import annotations

import json
import os
from pathlib import Path


class State:
    def __init__(self, data_dir: Path):
        self.path = data_dir / "state.json"
        self.data: dict = {}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text())
            except json.JSONDecodeError:
                self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value) -> None:
        self.data[key] = value

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True))
        os.replace(tmp, self.path)
