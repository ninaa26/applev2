"""Server settings from environment variables (or a .env file next to where you run it).

Everything machine-specific lives here, so moving from the team Mac to a real
server is: copy the database + media folder, set these variables, start.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv(path: Path = Path(".env")) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            value = value.strip()
            if value[:1] in ('"', "'"):
                value = value[1:].partition(value[0])[0]
            else:
                value = re.split(r"\s+#", value, maxsplit=1)[0].strip()  # inline comment
            os.environ.setdefault(key.strip(), value)


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("SENTINEL_DATA_DIR", "data")))
    database_url: str = ""
    timezone: str = field(default_factory=lambda: os.environ.get("SENTINEL_TZ", "America/New_York"))
    detector: str = field(default_factory=lambda: os.environ.get("SENTINEL_DETECTOR", "baseline"))
    classifier: str = field(default_factory=lambda: os.environ.get("SENTINEL_CLASSIFIER", "none"))
    # Spacing of the liner's printed grid; the baseline detector uses it to work out the image scale.
    grid_mm: float = field(default_factory=lambda: float(os.environ.get("SENTINEL_GRID_MM", "25.4")))
    worker_poll_s: float = field(default_factory=lambda: float(os.environ.get("SENTINEL_WORKER_POLL_S", "3")))
    offline_after_h: float = field(default_factory=lambda: float(os.environ.get("SENTINEL_OFFLINE_AFTER_H", "12")))

    def __post_init__(self):
        self.data_dir = self.data_dir.resolve()
        self.database_url = os.environ.get("SENTINEL_DATABASE_URL") or f"sqlite:///{self.data_dir / 'sentinel.db'}"

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "media"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _load_dotenv()
        _settings = Settings()
        _settings.media_dir.mkdir(parents=True, exist_ok=True)
    return _settings


def reset_settings() -> None:
    """For tests: re-read the environment."""
    global _settings
    _settings = None
