"""Adding and updating devices without a laptop: ESP32 firmware updates sent through the hubs, cameras that
pair with a hub and are added from the dashboard, and hubs that fetch their key with the code on their sticker.
docs/esp32-traps.md has the whole flow."""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from . import services
from .models import Event, Firmware, HubClaim, PendingCamera, Trap, utcnow
from .settings import get_settings

# ------------------------------------------------------------------ firmware

FW_MARKER = re.compile(rb"SENTINEL_FW_VERSION=([0-9A-Za-z._-]{1,32});(release|dev)\x00")
FW_VERSION = re.compile(r"[0-9A-Za-z._-]{1,32}")
MAX_FIRMWARE = 2 * 1024 * 1024  # one app slot (partitions.csv)


def firmware_dir() -> Path:
    d = get_settings().data_dir / "firmware"
    d.mkdir(parents=True, exist_ok=True)
    return d


def firmware_path(version: str) -> Path:
    if not FW_VERSION.fullmatch(version):
        raise ValueError(f"bad firmware version {version!r}")
    return firmware_dir() / f"{version}.bin"


def read_firmware_version(data: bytes) -> str:
    """The version built into an ESP32 app image (main.cpp's FW_MARKER). Only release builds are accepted:
    a dev build has one camera's trap id and key compiled in, and would give every camera that key."""
    if len(data) < 1024 or data[0] != 0xE9:
        raise ValueError("not an ESP32 firmware file: use .pio/build/release/firmware.bin")
    if len(data) > MAX_FIRMWARE:
        raise ValueError(f"firmware larger than the {MAX_FIRMWARE // 1024} kB app slot")
    m = FW_MARKER.search(data)
    if m is None:
        raise ValueError("no Sentinel version in this file: is it the camera firmware, 0.3.0 or later?")
    if m.group(2) != b"release":
        raise ValueError("this is a dev build with a trap's key in it: build it with release.sh")
    return m.group(1).decode()


def add_firmware(db: Session, data: bytes, note: str = "") -> Firmware:
    version = read_firmware_version(data)
    md5 = hashlib.md5(data).hexdigest()
    fw = db.get(Firmware, version)
    if fw is not None:
        if fw.md5 != md5:
            raise ValueError(f"firmware {version} is already here with different contents: raise FW_VERSION")
        return fw
    path = firmware_path(version)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(path)
    fw = Firmware(version=version, size=len(data), md5=md5, note=note[:200])
    db.add(fw)
    db.flush()
    return fw


def set_firmware_target(db: Session, version: str | None, trap_ids: list[str]) -> list[Trap]:
    """Ask these ESP32 cameras to install `version` (None: stop asking). Returns the cameras changed."""
    if version is not None and db.get(Firmware, version) is None:
        raise ValueError(f"no firmware {version!r} uploaded")
    changed = []
    for trap_id in trap_ids:
        trap = db.get(Trap, trap_id)
        if trap is None or trap.kind != "esp32" or trap.retired_at is not None:
            raise ValueError(f"{trap_id} is not an ESP32 camera in the orchard")
        if trap.firmware_target != version:
            trap.firmware_target = version
            changed.append(trap)
            if version:
                db.add(Event(trap_id=trap.id, kind="firmware_asked", payload={"note": f"firmware {version}"}))
    return changed


def hub_firmware(db: Session, hub_id: str) -> dict[str, dict]:
    """ESP32 cameras on this hub with firmware to install: {trap_id: {version, size, md5}}."""
    out = {}
    for t in db.scalars(select(Trap).where(Trap.hub_id == hub_id, Trap.kind == "esp32", Trap.retired_at.is_(None),
                                           Trap.firmware_target.is_not(None))):
        if t.firmware_target == t.firmware_version:
            continue
        fw = db.get(Firmware, t.firmware_target)
        if fw is not None:
            out[t.id] = {"version": fw.version, "size": fw.size, "md5": fw.md5}
    return out


def note_firmware(db: Session, trap: Trap, version: str | None) -> None:
    """A camera's photo said which firmware it runs. Note when it reached the version it was asked for."""
    if not version or not FW_VERSION.fullmatch(version) or version == trap.firmware_version:
        return
    trap.firmware_version = version
    if version == trap.firmware_target:
        db.add(Event(trap_id=trap.id, kind="firmware_updated", payload={"note": f"firmware {version}"}))


# ------------------------------------------------------------------ cameras pairing through a hub

CAMERA_CODE = re.compile(r"[0-9A-F]{6}")
PENDING_FOR = timedelta(days=1)   # a waiting camera not heard from for this long drops off the page


def normalise_code(code: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", code).upper()


def hub_pairing(db: Session, hub: Trap, waiting: list, handed: list) -> dict[str, dict]:
    """A hub's report of cameras asking to be added (waiting) and of keys it has handed over (handed).
    Returns the keys for cameras added on the dashboard since: {code: {trap_id, api_key}}."""
    now = utcnow()
    for code in handed:
        row = db.get(PendingCamera, normalise_code(str(code)))
        if row is not None and row.hub_id == hub.id and row.trap_id:
            db.delete(row)
    for w in waiting[:50]:
        if not isinstance(w, dict):
            continue
        code = normalise_code(str(w.get("code", "")))
        if not CAMERA_CODE.fullmatch(code):
            continue
        row = db.get(PendingCamera, code)
        if row is None:
            row = PendingCamera(code=code, hub_id=hub.id, first_seen_at=now)
            db.add(row)
        elif row.trap_id is None:
            row.hub_id = hub.id  # it moved to another hub before it was added
        row.last_seen_at = now
        fw = str(w.get("fw", ""))[:32]
        row.fw = fw if FW_VERSION.fullmatch(fw) else ""
        row.rssi = w.get("rssi") if isinstance(w.get("rssi"), int) else None
    db.execute(delete(PendingCamera).where(PendingCamera.trap_id.is_(None), PendingCamera.last_seen_at < now - PENDING_FOR))
    db.flush()
    return {r.code: {"trap_id": r.trap_id, "api_key": r.api_key}
            for r in db.scalars(select(PendingCamera).where(PendingCamera.hub_id == hub.id, PendingCamera.trap_id.is_not(None)))}


def waiting_cameras(db: Session) -> list[PendingCamera]:
    return list(db.scalars(select(PendingCamera).where(
        PendingCamera.trap_id.is_(None), PendingCamera.last_seen_at >= utcnow() - PENDING_FOR).order_by(PendingCamera.first_seen_at)))


def add_waiting_camera(db: Session, code: str, trap_id: str, name: str = "", block: str = "", lure: str = "CM") -> Trap:
    """Add a camera that is waiting near a hub. Its key goes to the hub, which hands it to the camera."""
    row = db.get(PendingCamera, normalise_code(code))
    if row is None or row.trap_id is not None:
        raise ValueError(f"no camera {code} is waiting to be added")
    key = services.create_trap(db, trap_id, name, block, lure, kind="esp32", hub_id=row.hub_id)
    row.trap_id, row.api_key = trap_id, key
    trap = db.get(Trap, trap_id)
    trap.firmware_version = row.fw or None
    return trap


# ------------------------------------------------------------------ hubs claiming their key

HUB_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # no 0/O, 1/I/L: read off a sticker
HUB_CODE = re.compile(f"[{HUB_CODE_ALPHABET}]{{10}}")


def new_hub_code() -> str:
    """What install-hub.sh makes (same alphabet), for tests and the CLI."""
    return "".join(secrets.choice(HUB_CODE_ALPHABET) for _ in range(10))


def add_hub_with_code(db: Session, code: str, trap_id: str, name: str = "", block: str = "") -> Trap:
    code = normalise_code(code)
    if not HUB_CODE.fullmatch(code):
        raise ValueError("a hub's pairing code is 10 letters and digits, as on its sticker (e.g. K7QM-3XTP9R)")
    if db.get(HubClaim, code) is not None:
        raise ValueError("that pairing code is already in use")
    key = services.create_trap(db, trap_id, name, block, kind="hub")
    db.add(HubClaim(code=code, trap_id=trap_id, api_key=key))
    db.flush()
    return db.get(Trap, trap_id)


def claim_hub(db: Session, code: str) -> dict | None:
    """The hub asking with its sticker's code: its trap id and key once it has been added, else None."""
    row = db.get(HubClaim, normalise_code(code))
    if row is None:
        return None
    trap = db.get(Trap, row.trap_id)
    if trap is None or trap.retired_at is not None:
        return None
    return {"trap_id": row.trap_id, "api_key": row.api_key}


def hub_key_used(db: Session, hub: Trap) -> None:
    """The hub has used its key, so it has it: forget the copy kept for its claim."""
    db.execute(delete(HubClaim).where(HubClaim.trap_id == hub.id))
