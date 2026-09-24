"""Offline-first upload queue.

Every capture is written to queue/ as <stem>.jpg + <stem>.json before any
network call. Uploads drain the queue oldest first; a photo only moves to
sent/ after the server confirms it, so nothing is lost if the Mac is asleep
or the orchard has no signal.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import requests

log = logging.getLogger(__name__)


class Queue:
    def __init__(self, data_dir: Path, keep_sent: int = 200):
        self.queue_dir = data_dir / "queue"
        self.sent_dir = data_dir / "sent"
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.sent_dir.mkdir(parents=True, exist_ok=True)
        self.keep_sent = keep_sent

    def add(self, image: Path, meta: dict) -> Path:
        stem = image.stem
        dest = self.queue_dir / image.name
        if image.resolve() != dest.resolve():
            shutil.move(str(image), dest)
        (self.queue_dir / f"{stem}.json").write_text(json.dumps(meta, indent=2))
        return dest

    def pending(self) -> list[Path]:
        return sorted(p for p in self.queue_dir.glob("*.jpg") if p.with_suffix(".json").exists())

    def mark_sent(self, image: Path) -> None:
        for p in (image, image.with_suffix(".json")):
            shutil.move(str(p), self.sent_dir / p.name)
        self._prune()

    def _prune(self) -> None:
        sent = sorted(self.sent_dir.glob("*.jpg"))
        for old in sent[: max(0, len(sent) - self.keep_sent)]:
            old.unlink(missing_ok=True)
            old.with_suffix(".json").unlink(missing_ok=True)


def upload_one(server_url: str, api_key: str, image: Path, timeout_s: float) -> dict:
    meta = image.with_suffix(".json").read_text()
    with open(image, "rb") as f:
        r = requests.post(
            f"{server_url.rstrip('/')}/api/v1/captures",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"image": (image.name, f, "image/jpeg")},
            data={"meta": meta},
            timeout=timeout_s,
        )
    if r.status_code == 409:  # server already has this capture (a retry after a lost reply)
        return r.json()
    r.raise_for_status()
    return r.json()


def drain(queue: Queue, server_url: str, api_key: str, timeout_s: float, max_items: int) -> tuple[int, dict | None, str | None]:
    """Upload up to max_items. Returns (uploaded, last server reply, error message)."""
    uploaded, reply = 0, None
    for image in queue.pending()[:max_items]:
        try:
            reply = upload_one(server_url, api_key, image, timeout_s)
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status is not None and 400 <= status < 500 and status not in (408, 429):
                # The server will never accept this file (bad metadata, unknown trap): park it.
                bad = queue.queue_dir / "rejected"
                bad.mkdir(exist_ok=True)
                for p in (image, image.with_suffix(".json")):
                    shutil.move(str(p), bad / p.name)
                log.error("server rejected %s: %s", image.name, e.response.text[:200])
                continue
            return uploaded, reply, f"upload failed: {e}"
        except requests.RequestException as e:
            return uploaded, reply, f"server unreachable: {e.__class__.__name__}"
        queue.mark_sent(image)
        uploaded += 1
    return uploaded, reply, None
