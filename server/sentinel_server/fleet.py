"""Adding and updating devices without a laptop: ESP32 firmware updates sent through the hubs, cameras that
pair with a hub and are added from the dashboard, and hubs that fetch their key with the code on their sticker.
docs/esp32-traps.md has the whole flow."""

from __future__ import annotations

import hashlib
import hmac
import json
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


SIG_MAGIC = b"SNTLSIG1"  # release.sh appends: SIG_MAGIC, 2-byte length, ECDSA P-256 signature (DER) of the image


def split_signature(data: bytes) -> tuple[bytes, bytes]:
    """A signed firmware file from release.sh: (the app image, its signature). The cameras check the signature
    against the public key built into them (include/firmware_key.h), so only builds signed with the team's
    private key are installed. The server only checks one is there."""
    at = data.rfind(SIG_MAGIC, max(0, len(data) - 200))
    if at < 0 or len(data) < at + 10:
        raise ValueError("this firmware isn't signed: build it with release.sh, which signs it")
    n = int.from_bytes(data[at + 8:at + 10], "big")
    sig = data[at + 10:]
    if len(sig) != n or not 8 <= n <= 72 or sig[0] != 0x30:
        raise ValueError("this firmware's signature is damaged: build it again with release.sh")
    return data[:at], sig


def add_firmware(db: Session, data: bytes, note: str = "") -> Firmware:
    data, sig = split_signature(data)
    version = read_firmware_version(data)
    md5 = hashlib.md5(data, usedforsecurity=False).hexdigest()  # the ESP32's Update checks MD5
    fw = db.get(Firmware, version)
    if fw is not None:
        if fw.md5 != md5:
            raise ValueError(f"firmware {version} is already here with different contents: raise FW_VERSION")
        return fw
    path = firmware_path(version)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(path)
    fw = Firmware(version=version, size=len(data), md5=md5, sig=sig.hex(), note=note[:200])
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
    """ESP32 cameras on this hub with firmware to install: {trap_id: {version, size, md5, sig}}."""
    out = {}
    for t in db.scalars(select(Trap).where(Trap.hub_id == hub_id, Trap.kind == "esp32", Trap.retired_at.is_(None),
                                           Trap.firmware_target.is_not(None))):
        if t.firmware_target == t.firmware_version:
            continue
        fw = db.get(Firmware, t.firmware_target)
        if fw is not None:
            out[t.id] = {"version": fw.version, "size": fw.size, "md5": fw.md5, "sig": fw.sig}
    return out


def note_firmware(db: Session, trap: Trap, version: str | None) -> None:
    """A camera's photo said which firmware it runs. Note when it reached the version it was asked for."""
    if not version or not FW_VERSION.fullmatch(version) or version == trap.firmware_version:
        return
    trap.firmware_version = version
    if version == trap.firmware_target:
        db.add(Event(trap_id=trap.id, kind="firmware_updated", payload={"note": f"firmware {version}"}))


# ------------------------------------------------------------------ cameras pairing through a hub
#
# A camera's sticker has two parts: its code (the last 6 hex digits of its MAC, which it sends openly) and a
# secret it made on its first boot (flash-camera.sh reads it off the serial port), which it never sends.
# From the secret both sides derive a pairing key K. The camera asks to be added with a proof (HMAC of K), so
# the dashboard can tell the secret typed in is the right one. The trap key then goes to the camera sealed
# with K: the hub, and anyone else on its Wi-Fi, only ever sees the sealed copy. main.cpp (pairingKey,
# openKey) does the same steps; keep the two in step.

CAMERA_CODE = re.compile(r"[0-9A-F]{6}")
CAMERA_SECRET = re.compile(r"[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{16}")  # HUB_CODE_ALPHABET: about 79 bits
PROOF = re.compile(r"[0-9a-f]{32}")
PAIR_ITERATIONS = 20_000          # PBKDF2 rounds: about 1 s on the camera, done once per pairing
PENDING_FOR = timedelta(days=1)   # a waiting camera not heard from for this long drops off the page
REBIND_AFTER = timedelta(minutes=30)  # a waiting camera stays with the hub that reported it while still heard


def normalise_code(code: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", code).upper()


def pairing_key(code: str, secret: str) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", secret.encode(), b"orchard-sentinel-pair:" + code.encode(), PAIR_ITERATIONS, 32)


def pairing_proof(k: bytes) -> str:
    return hmac.new(k, b"proof", "sha256").hexdigest()[:32]


def _keystream(k: bytes, nonce: bytes, n: int) -> bytes:
    return b"".join(hmac.new(k, b"enc" + nonce + bytes([i]), "sha256").digest() for i in range((n + 31) // 32))[:n]


def _tag(k: bytes, nonce: bytes, trap_id: str, box: bytes) -> str:
    return hmac.new(k, b"tag" + nonce + bytes([len(trap_id)]) + trap_id.encode() + box, "sha256").hexdigest()[:32]


def seal_key(k: bytes, trap_id: str, api_key: str, nonce: bytes | None = None) -> dict[str, str]:
    """The trap key encrypted for the camera: HMAC-SHA256 keystream, then an HMAC tag over the result.
    (A fixed nonce is only for the test vector the firmware is checked against.)"""
    nonce, data = nonce or secrets.token_bytes(16), api_key.encode()
    box = bytes(a ^ b for a, b in zip(data, _keystream(k, nonce, len(data)), strict=True))
    return {"nonce": nonce.hex(), "box": box.hex(), "tag": _tag(k, nonce, trap_id, box)}


def open_key(k: bytes, trap_id: str, sealed: dict) -> str | None:
    """What the camera does with a sealed key (the tests use it). None if it doesn't check out."""
    nonce, box = bytes.fromhex(sealed["nonce"]), bytes.fromhex(sealed["box"])
    if not hmac.compare_digest(_tag(k, nonce, trap_id, box), sealed["tag"]):
        return None
    return bytes(a ^ b for a, b in zip(box, _keystream(k, nonce, len(box)), strict=True)).decode()


def hub_pairing(db: Session, hub: Trap, waiting: list, handed: list) -> dict[str, dict]:
    """A hub's report of cameras asking to be added (waiting) and of keys it has handed over (handed).
    Returns the sealed keys for cameras added on the dashboard since: {code: {trap_id, key_hash, nonce, box, tag}}."""
    now = utcnow()
    for code in handed:
        row = db.get(PendingCamera, normalise_code(str(code)))
        if row is not None and row.hub_id == hub.id and row.trap_id:
            db.delete(row)
    for w in waiting[:50]:
        if not isinstance(w, dict):
            continue
        code, proof = normalise_code(str(w.get("code", ""))), str(w.get("proof", ""))
        if not CAMERA_CODE.fullmatch(code) or not PROOF.fullmatch(proof):
            continue
        row = db.get(PendingCamera, code)
        if row is None:
            row = PendingCamera(code=code, hub_id=hub.id, proof=proof, first_seen_at=now)
            db.add(row)
        elif (row.hub_id, row.proof) != (hub.id, proof):
            # Another hub, or another device using this code. The first stays while it is still heard from,
            # so a report can't move a camera to a hub it didn't pair at; one heard from no longer can move.
            if row.trap_id is not None or row.last_seen_at >= now - REBIND_AFTER:
                continue
            row.hub_id, row.proof, row.first_seen_at = hub.id, proof, now
        elif row.trap_id is not None:
            continue
        row.last_seen_at = now
        fw = str(w.get("fw", ""))[:32]
        row.fw = fw if FW_VERSION.fullmatch(fw) else ""
        row.rssi = w.get("rssi") if isinstance(w.get("rssi"), int) else None
    db.execute(delete(PendingCamera).where(PendingCamera.trap_id.is_(None), PendingCamera.last_seen_at < now - PENDING_FOR))
    db.flush()
    out = {}
    for r in db.scalars(select(PendingCamera).where(PendingCamera.hub_id == hub.id, PendingCamera.trap_id.is_not(None))):
        trap = db.get(Trap, r.trap_id)
        # Not once the camera is removed or given another key: the sealed key would no longer work.
        if r.sealed and trap is not None and trap.retired_at is None and trap.api_key_hash == r.key_hash:
            out[r.code] = {"trap_id": r.trap_id, "key_hash": r.key_hash, **json.loads(r.sealed)}
    return out


def waiting_cameras(db: Session) -> list[PendingCamera]:
    return list(db.scalars(select(PendingCamera).where(
        PendingCamera.trap_id.is_(None), PendingCamera.last_seen_at >= utcnow() - PENDING_FOR).order_by(PendingCamera.first_seen_at)))


def add_waiting_camera(db: Session, code: str, secret: str, trap_id: str, name: str = "", block: str = "",
                       lure: str = "CM") -> Trap:
    """Add a camera that is waiting near a hub, with the secret from its sticker. Its key goes to the camera
    through the hub, sealed with that secret. An existing camera's id pairs that camera again (a new key,
    and the hub it is near now), keeping its photos and counts."""
    code = normalise_code(code)
    row = db.get(PendingCamera, code)
    if row is None or row.trap_id is not None:
        raise ValueError(f"no camera {code} is waiting to be added")
    secret = normalise_code(secret)
    if not CAMERA_SECRET.fullmatch(secret):
        raise ValueError("the camera's secret is the 16 letters and digits on its sticker after its code")
    k = pairing_key(code, secret)
    if not hmac.compare_digest(pairing_proof(k), row.proof):
        raise ValueError(f"that secret isn't the one camera {code} has: check the sticker")
    trap = db.get(Trap, trap_id)
    if trap is None:
        key = services.create_trap(db, trap_id, name, block, lure, kind="esp32", hub_id=row.hub_id)
        trap = db.get_one(Trap, trap_id)  # create_trap just added it
    elif trap.kind == "esp32" and trap.retired_at is None:
        hub = db.get(Trap, row.hub_id)
        if hub is None or hub.retired_at is not None or hub.kind not in services.HUB_KINDS:
            raise ValueError(f"hub {row.hub_id} is not in the orchard")
        key = services.new_api_key()
        trap.api_key_hash, trap.hub_id = services.hash_key(key), row.hub_id
        db.add(Event(trap_id=trap.id, kind="trap_changed", payload={"note": f"paired again, near hub {row.hub_id}"}))
    else:
        raise ValueError(f"{trap_id} is already a trap that isn't an ESP32 camera in the orchard")
    row.trap_id, row.key_hash, row.sealed = trap_id, trap.api_key_hash, json.dumps(seal_key(k, trap_id, key))
    trap.firmware_version = row.fw or None
    return trap


# ------------------------------------------------------------------ hubs claiming their key

HUB_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # no 0/O, 1/I/L: read off a sticker
HUB_CODE = re.compile(f"[{HUB_CODE_ALPHABET}]{{10}}")


def new_hub_code() -> str:
    """What install-hub.sh makes (same alphabet), for tests and the CLI."""
    return "".join(secrets.choice(HUB_CODE_ALPHABET) for _ in range(10))


def add_hub_with_code(db: Session, code: str, trap_id: str, name: str = "", block: str = "",
                      lat: float | None = None, lon: float | None = None) -> Trap:
    code = normalise_code(code)
    if not HUB_CODE.fullmatch(code):
        raise ValueError("a hub's pairing code is 10 letters and digits, as on its sticker (e.g. K7QM-3XTP9R)")
    if db.get(HubClaim, code) is not None:
        raise ValueError("that pairing code is already in use")
    key = services.create_trap(db, trap_id, name, block, kind="hub", lat=lat, lon=lon)
    db.add(HubClaim(code=code, trap_id=trap_id, api_key=key))
    db.flush()
    return db.get_one(Trap, trap_id)  # create_trap just added it


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
