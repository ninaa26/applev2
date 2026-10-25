"""FastAPI app: device upload API + the team dashboard (open unless SENTINEL_DASHBOARD_PASSWORD is set)."""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import re
import secrets
import threading
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import __version__, fleet, services, weather
from .db import get_session, init_db
from .models import PESTS, SPECIES, SPECIES_LABELS, Capture, Detection, Event, Firmware, Review, Track, Trap, utcnow
from .settings import get_settings

HERE = Path(__file__).parent
# A capture uid becomes a file name: letters, digits, "_" and "-" only, so it can't point outside media/.
WRONG_LIMIT, WRONG_WINDOW_S = 10, 600  # dashboard: 10 wrong passwords per address in 10 minutes
SAFE_UID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")


class HubPairing(BaseModel):
    """A hub's report. Each entry is checked on its own in fleet.hub_pairing, so one camera sending
    something odd is skipped instead of failing the whole report."""

    waiting: list[Any] = Field(default=[], description="cameras asking to be added: {code, fw, rssi}", max_length=200)
    handed: list[Any] = Field(default=[], description="codes of cameras the hub has given their key", max_length=200)


class HubClaim(BaseModel):
    code: str = Field(default="", max_length=40, description="the pairing code on the hub's sticker")


templates = Jinja2Templates(directory=str(HERE / "templates"))


def _local(dt: datetime | None, fmt: str = "%b %d %H:%M") -> str:
    if dt is None:
        return "—"
    return dt.replace(tzinfo=UTC).astimezone(ZoneInfo(get_settings().timezone)).strftime(fmt)


def _ago(dt: datetime | None) -> str:
    if dt is None:
        return "never"
    s = (utcnow() - dt).total_seconds()
    if s < 90:
        return "just now"
    if s < 5400:
        return f"{int(s // 60)} min ago"
    if s < 172800:
        return f"{s / 3600:.0f} h ago"
    return f"{s / 86400:.0f} days ago"


templates.env.filters["local"] = _local
templates.env.filters["ago"] = _ago
templates.env.filters["fromiso"] = datetime.fromisoformat
# What each event means, in a grower's words (Event.kind).
EVENT_LABELS = {
    "new_card": "New liner", "new_card_ignored": "Not a new liner after all: the same insects are still there",
    "card_full": "Liner is getting full", "card_old": "Liner is old", "glare": "Glare on the liner",
    "trap_added": "Trap added", "trap_changed": "Trap changed", "trap_removed": "Trap taken out", "trap_restored": "Trap put back",
    "firmware_asked": "Camera update sent", "firmware_updated": "Camera updated",
}
# The stylesheet's URL carries a hash of its contents, so a deploy never leaves a browser on a cached old copy.
CSS_V = hashlib.sha256((HERE / "static" / "app.css").read_bytes()).hexdigest()[:12]
templates.env.globals.update(SPECIES=SPECIES, SPECIES_LABELS=SPECIES_LABELS, PESTS=PESTS, version=__version__,
                             EVENT_LABELS=EVENT_LABELS, CSS_V=CSS_V)


def create_app(start_worker: bool = False) -> FastAPI:
    stop = threading.Event()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        thread = None
        if start_worker:
            from .pipeline.worker import run_forever

            thread = threading.Thread(target=run_forever, args=(stop,), daemon=True, name="worker")
            thread.start()
        yield
        stop.set()

    app = FastAPI(title="Orchard Sentinel", version=__version__, lifespan=lifespan)
    settings = get_settings()
    app.mount("/media", StaticFiles(directory=str(settings.media_dir)), name="media")
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")

    # ---------------------------------------------------------------- forms from other sites, headers

    # The browser re-sends the dashboard password by itself, so any web page a teammate has open could post
    # the dashboard's forms (a firmware upload reaches every camera). Browsers mark a POST with the page it
    # came from: refuse it when that is another site. Traps, hubs and curl send no Origin and are let through.
    @app.middleware("http")
    async def same_site_forms(request: Request, call_next):
        if request.method not in ("GET", "HEAD", "OPTIONS") and not request.url.path.startswith("/api/"):
            origin = request.headers.get("origin") or request.headers.get("referer")
            host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
            if origin is not None and urlsplit(origin).netloc != host:
                return Response("This form must be sent from the dashboard itself.", status_code=403)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")  # no page may show the dashboard in a frame
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    # ---------------------------------------------------------------- dashboard password

    # Traps and hubs sign their requests with their own key (a hub claiming its key has the code on its
    # sticker), and /healthz says nothing worth hiding.
    no_password = {"/api/v1/captures", "/healthz"}
    # Wrong passwords per address in the last WRONG_WINDOW_S; past WRONG_LIMIT that address waits, so the
    # password can't be guessed by trying many. A browser's first visit, with no password yet, doesn't count.
    wrong: dict[str, list[float]] = {}

    @app.middleware("http")
    async def dashboard_password(request: Request, call_next):
        expected = get_settings().dashboard_password
        if expected and request.url.path not in no_password and not request.url.path.startswith("/api/v1/hub/"):
            who, now = request.client.host if request.client else "", time.monotonic()
            recent = [t for t in wrong.get(who, ()) if now - t < WRONG_WINDOW_S]
            if len(recent) >= WRONG_LIMIT:
                return Response("Too many wrong passwords. Try again in a few minutes.", status_code=429,
                                headers={"Retry-After": str(int(WRONG_WINDOW_S - (now - recent[0])) + 1)})
            header = request.headers.get("authorization", "")
            scheme, _, token = header.partition(" ")
            try:
                given = base64.b64decode(token, validate=True).decode().partition(":")[2] if scheme.lower() == "basic" else ""
            except (binascii.Error, UnicodeDecodeError):
                given = ""
            if not secrets.compare_digest(given.encode(), expected.encode()):
                if header:
                    wrong[who] = [*recent, now]
                return Response("Password needed.", status_code=401,
                                headers={"WWW-Authenticate": 'Basic realm="Orchard Sentinel", charset="UTF-8"'})
        return await call_next(request)

    # ---------------------------------------------------------------- device API

    def device_trap(authorization: str = Header(default=""), db: Session = Depends(get_session)) -> Trap:
        key = authorization.removeprefix("Bearer ").strip()
        trap = db.scalar(select(Trap).where(Trap.api_key_hash == services.hash_key(key))) if key else None
        if trap is None:
            raise HTTPException(401, "unknown or missing trap API key")
        if trap.retired_at is not None:
            raise HTTPException(410, f"trap {trap.id} was removed from the orchard on the dashboard")
        services.note_seen(trap)
        return trap

    def hub_trap(trap: Trap = Depends(device_trap), db: Session = Depends(get_session)) -> Trap:
        if trap.kind not in services.HUB_KINDS:
            raise HTTPException(403, f"{trap.id} is a camera, not a hub")
        fleet.hub_key_used(db, trap)
        return trap

    # A plain def: FastAPI runs it in a worker thread. As `async def`, its database and file work blocked the
    # event loop, and with it every other request, for as long as an upload took.
    @app.post("/api/v1/captures", status_code=201)
    def upload_capture(
        image: UploadFile = File(...),
        meta: str = Form(...),
        trap: Trap = Depends(device_trap),
        db: Session = Depends(get_session),
    ):
        try:
            m = json.loads(meta)
            captured = datetime.fromisoformat(m["captured_at"])
        except (ValueError, KeyError, TypeError) as e:
            raise HTTPException(422, f"bad meta: {e}") from e
        if m.get("trap_id") not in (None, trap.id):
            raise HTTPException(422, f"meta trap_id {m.get('trap_id')!r} does not match this key's trap {trap.id!r}")
        captured = captured.astimezone(UTC).replace(tzinfo=None) if captured.tzinfo else captured
        uid = str(m.get("capture_uid") or Path(image.filename or "capture").stem)
        if not SAFE_UID.fullmatch(uid):
            raise HTTPException(422, f"bad capture_uid {uid!r}: use letters, digits, _ and - (max 80)")

        existing = db.scalar(select(Capture).where(Capture.trap_id == trap.id, Capture.uid == uid))
        if existing is not None:
            return JSONResponse(
                {"capture_id": existing.id, "card_id": existing.card_id, "config": trap.device_config or {}, "duplicate": True},
                status_code=409,
            )

        limit = int(settings.max_upload_mb * 1_000_000)
        data = image.file.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(413, f"photo larger than {settings.max_upload_mb:g} MB")
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
        except Exception:
            raise HTTPException(422, "image is not a readable picture") from None

        # A photo goes on the liner that was in the trap when it was taken, not the one there when it arrives:
        # photos wait in the trap's (or hub's) queue while the server is out of reach, and a liner may have
        # been changed on the dashboard meanwhile. A "new liner" photo only opens one if it is the newest.
        current = services.open_card(db, trap.id)
        if current is None or (m.get("new_card") and current.installed_at < captured):
            card = services.start_new_card(db, trap.id, at=captured, note="from trap" if m.get("new_card") else "first photo")
        else:
            card = services.card_at(db, trap.id, captured)

        rel = Path(trap.id) / captured.strftime("%Y/%m/%d") / f"{uid}.jpg"
        dest = settings.media_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

        env, power = m.get("env") or {}, m.get("power") or {}
        cap = Capture(
            trap_id=trap.id, card_id=card.id, uid=uid, captured_at=captured, image_path=str(rel),
            wake_reason=m.get("wake_reason", ""), temp_c=env.get("temp_c"), rh=env.get("rh"),
            battery_v=power.get("battery_v"), meta=m, status="new",
        )
        db.add(cap)
        fleet.note_firmware(db, trap, str((m.get("device") or {}).get("sw_version") or ""))
        if trap.photo_requested_at is not None and captured >= trap.photo_requested_at:
            trap.photo_requested_at = None  # the photo asked for on the dashboard (or a newer one) is here
        db.flush()
        return {"capture_id": cap.id, "card_id": card.id, "config": trap.device_config or {}}

    @app.get("/api/v1/hub/nodes")
    def api_hub_nodes(trap: Trap = Depends(device_trap), db: Session = Depends(get_session)):
        """The ESP32 traps this hub takes photos from, with their key hashes so the hub can check them,
        which of them have a photo asked for on the dashboard, and which have firmware to install."""
        fleet.hub_key_used(db, trap)
        return {"nodes": services.hub_nodes(db, trap.id), "photo_requests": services.photo_requests(db, trap.id),
                "firmware": fleet.hub_firmware(db, trap.id)}

    @app.get("/api/v1/hub/firmware/{version}")
    def api_hub_firmware(version: str, trap: Trap = Depends(hub_trap)):
        try:
            path = fleet.firmware_path(version)
        except ValueError as e:
            raise HTTPException(404, str(e)) from e
        if not path.exists():
            raise HTTPException(404, f"no firmware {version}")
        return FileResponse(path, media_type="application/octet-stream")

    @app.post("/api/v1/hub/pairing")
    def api_hub_pairing(body: HubPairing, trap: Trap = Depends(hub_trap), db: Session = Depends(get_session)):
        """Cameras near this hub asking to be added, and keys it has handed over; replies with new keys."""
        return {"assigned": fleet.hub_pairing(db, trap, body.waiting, body.handed)}

    @app.post("/api/v1/hub/claim")
    def api_hub_claim(body: HubClaim, db: Session = Depends(get_session)):
        """A new hub with no key asks with the pairing code on its sticker; 404 until it is added on the dashboard."""
        got = fleet.claim_hub(db, body.code)
        if got is None:
            raise HTTPException(404, "not added on the dashboard yet")
        return got

    @app.get("/api/v1/traps")
    def api_traps(db: Session = Depends(get_session)):
        out = []
        for t in services.active_traps(db):
            h = services.trap_health(db, t)
            out.append({
                "id": t.id, "name": t.name, "lure": t.lure, "kind": t.kind, "hub_id": t.hub_id, "state": h["state"],
                "last_photo_at": h["last"].captured_at.isoformat() if h.get("last") else None,
                "week_counts": dict(services.week_counts(db, t.id)),
                "pending_reviews": len(services.pending_reviews(db, t.id)),
            })
        return out

    @app.get("/api/v1/traps/{trap_id}/counts")
    def api_counts(trap_id: str, days: int = 30, db: Session = Depends(get_session)):
        if db.get(Trap, trap_id) is None:
            raise HTTPException(404, "no such trap")
        return [{"date": r["date"].isoformat(), "counts": r["counts"]} for r in services.daily_counts(db, trap_id, days)]

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "version": __version__}

    # ---------------------------------------------------------------- dashboard actions

    @app.post("/traps/{trap_id}/new-card")
    def new_card(trap_id: str, note: str = Form(default="installed from dashboard"), lure: str = Form(default=""),
                 db: Session = Depends(get_session)):
        if db.get(Trap, trap_id) is None:
            raise HTTPException(404, "no such trap")
        try:
            services.start_new_card(db, trap_id, note=note, lure=lure or None)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return RedirectResponse(f"/traps/{trap_id}", status_code=303)

    @app.post("/traps/{trap_id}/biofix")
    def set_biofix(trap_id: str, date: str = Form(default=""), db: Session = Depends(get_session)):
        """Confirm the biofix, or set another date (YYYY-MM-DD); empty goes back to the one from the catches."""
        trap = db.get(Trap, trap_id)
        if trap is None:
            raise HTTPException(404, "no such trap")
        if not date.strip():
            trap.biofix_date = None
        else:
            try:
                when = datetime.strptime(date.strip(), "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(422, "biofix date must be YYYY-MM-DD") from None
            if when > services.local_date(services.utcnow()):
                raise HTTPException(422, "the biofix can't be in the future")
            trap.biofix_date = when
        return RedirectResponse(f"/traps/{trap_id}", status_code=303)

    @app.post("/traps/{trap_id}/location")
    def set_location(trap_id: str, lat: str = Form(default=""), lon: str = Form(default=""),
                     db: Session = Depends(get_session)):
        """Where a hub (or Pi trap) is, for the weather on its cameras' photos; both empty forgets it."""
        trap = db.get(Trap, trap_id)
        if trap is None:
            raise HTTPException(404, "no such trap")
        try:
            where = weather.parse_location(lat, lon)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        if where != (trap.lat, trap.lon):
            trap.lat, trap.lon = where
            weather.forget(db, trap)
        return RedirectResponse(f"/traps/{trap_id}", status_code=303)

    @app.post("/traps/{trap_id}/request-photo")
    def request_photo(trap_id: str, db: Session = Depends(get_session)):
        trap = db.get(Trap, trap_id)
        if trap is None:
            raise HTTPException(404, "no such trap")
        try:
            services.request_photo(trap)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        return RedirectResponse(f"/traps/{trap_id}", status_code=303)

    @app.post("/tracks/{track_id}/review")
    def review(track_id: int, label: str = Form(...), reviewer: str = Form(default=""), next: str = Form(default="/review"),
               count: int | None = Form(default=None), db: Session = Depends(get_session)):
        t = db.get(Track, track_id)
        if t is None:
            raise HTTPException(404, "no such insect")
        if label == "reject":
            t.review_status = "rejected"
        elif label in SPECIES:
            t.reviewed_label = label
            t.review_status = "confirmed"
            if count is not None:  # touching insects: the reviewer's count replaces the estimate
                t.n_insects = max(1, min(50, count))
        else:
            raise HTTPException(422, f"unknown label {label!r}")
        db.add(Review(track_id=t.id, label=label, reviewer=reviewer[:60]))
        return RedirectResponse(next if next.startswith("/") and next[1:2] not in ("/", "\\") else "/review", status_code=303)

    @app.get("/crops/{detection_id}.jpg")
    def crop_image(detection_id: int, db: Session = Depends(get_session)):
        d = db.get(Detection, detection_id)
        if d is None:
            raise HTTPException(404)
        from .pipeline.classify import crop

        with Image.open(settings.media_dir / d.capture.image_path) as img:
            c = crop(img, d, pad=0.6).convert("RGB")
            c.thumbnail((320, 320))
            buf = io.BytesIO()
            c.save(buf, "JPEG", quality=90)
        return Response(buf.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})

    # ---------------------------------------------------------------- dashboard pages

    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request, db: Session = Depends(get_session)):
        rows = []
        traps = services.camera_traps(db)
        now = utcnow()
        for t in traps:
            card = services.open_card(db, t.id)
            rows.append({
                "trap": t, "health": services.trap_health(db, t), "week": services.week_counts(db, t.id),
                "pending": len(services.pending_reviews(db, t.id)), "card": card,
                "liner_days": (now - card.installed_at).total_seconds() / 86400 if card else 0,
                "pheno": services.phenology_status(db, t),
            })
        events = list(db.scalars(select(Event).order_by(Event.at.desc()).limit(12)))
        hubs = [{"trap": h, "health": services.hub_health(h),
                 "cameras": sum(t.hub_id == h.id for t in traps)} for h in services.hubs(db)]
        return templates.TemplateResponse(request, "overview.html", {
            "rows": rows, "hubs": hubs, "events": events, "orchard": services.orchard_summary(db, traps),
            "today": services.local_date(now), "liner_max_days": get_settings().liner_max_days,
        })

    @app.get("/traps/{trap_id}", response_class=HTMLResponse)
    def trap_page(trap_id: str, request: Request, db: Session = Depends(get_session)):
        trap = db.get(Trap, trap_id)
        if trap is None:
            raise HTTPException(404, "no such trap")
        if trap.kind == "hub":  # no photos or liner: its status and its cameras
            cameras = [{"trap": t, "health": services.trap_health(db, t)}
                       for t in services.camera_traps(db) if t.hub_id == trap_id]
            return templates.TemplateResponse(request, "hub.html", {
                "trap": trap, "health": services.hub_health(trap), "cameras": cameras,
            })
        caps = list(db.scalars(select(Capture).where(Capture.trap_id == trap_id).order_by(Capture.captured_at.desc()).limit(40)))
        daily = services.daily_counts(db, trap_id, 30)
        peak = max([sum(r["counts"].values()) for r in daily] + [1])
        latest = caps[0] if caps else None
        tracks = {d.track_id: db.get(Track, d.track_id) for d in latest.detections if d.track_id} if latest else {}
        return templates.TemplateResponse(request, "trap.html", {
            "trap": trap, "caps": caps, "latest": latest, "tracks": tracks, "daily": daily, "peak": peak,
            "health": services.trap_health(db, trap), "card": services.open_card(db, trap_id),
            "pheno": services.phenology_status(db, trap), "pending": len(services.pending_reviews(db, trap_id)),
            "checks": services.spot_checks(db, trap_id), "today": services.local_date(utcnow()),
        })

    @app.get("/traps/{trap_id}/photos", response_class=HTMLResponse)
    def trap_photos(trap_id: str, request: Request, page: int = 1, db: Session = Depends(get_session)):
        trap = db.get(Trap, trap_id)
        if trap is None:
            raise HTTPException(404, "no such trap")
        per_page = 48
        total = db.scalar(select(func.count(Capture.id)).where(Capture.trap_id == trap_id))
        pages = max(1, -(-total // per_page))
        page = min(max(1, page), pages)
        caps = list(db.scalars(select(Capture).where(Capture.trap_id == trap_id).order_by(Capture.captured_at.desc())
                               .offset((page - 1) * per_page).limit(per_page)))
        return templates.TemplateResponse(request, "photos.html", {
            "trap": trap, "caps": caps, "page": page, "pages": pages, "total": total,
        })

    def manage_page(request: Request, db: Session, new_key: dict | None = None, error: str | None = None,
                    status_code: int = 200):
        traps = list(db.scalars(select(Trap).order_by(Trap.retired_at.is_not(None), Trap.id)))
        return templates.TemplateResponse(request, "manage.html", {
            "traps": traps, "hubs": [t for t in traps if t.kind in services.HUB_KINDS and t.retired_at is None],
            "health": {t.id: services.trap_health(db, t) for t in traps}, "suggest_id": services.next_trap_id(db),
            "kinds": services.TRAP_KINDS, "new_key": new_key, "error": error,
            "server_url": str(request.base_url).rstrip("/"), "waiting": fleet.waiting_cameras(db),
            "firmware": list(db.scalars(select(Firmware).order_by(Firmware.uploaded_at.desc()))),
            "esp32s": [t for t in traps if t.kind == "esp32" and t.retired_at is None],
        }, status_code=status_code)

    @app.get("/manage", response_class=HTMLResponse)
    def manage(request: Request, db: Session = Depends(get_session)):
        return manage_page(request, db)

    @app.post("/manage/traps", response_class=HTMLResponse)
    def manage_add(request: Request, trap_id: str = Form(...), name: str = Form(default=""), block: str = Form(default=""),
                   lure: str = Form(default="CM"), kind: str = Form(default="esp32"), hub_id: str = Form(default=""),
                   lat: str = Form(default=""), lon: str = Form(default=""), pair_code: str = Form(default=""),
                   db: Session = Depends(get_session)):
        try:
            # An ESP32 camera goes by its hub's location (see weather.location), so only Pis are asked for one.
            la, lo = weather.parse_location(lat, lon) if kind != "esp32" else (None, None)
            if kind == "hub" and pair_code.strip():  # the hub fetches its key itself with the code on its sticker
                trap = fleet.add_hub_with_code(db, pair_code, trap_id.strip(), name.strip()[:120], block.strip()[:120], la, lo)
                return manage_page(request, db, new_key={"trap": trap, "key": None, "why": "paired"})
            key = services.create_trap(db, trap_id.strip(), name.strip()[:120], block.strip()[:120], lure, kind,
                                       hub_id or None, la, lo)
        except ValueError as e:
            return manage_page(request, db, error=str(e), status_code=422)
        return manage_page(request, db, new_key={"trap": db.get(Trap, trap_id.strip()), "key": key, "why": "added"})

    @app.post("/manage/waiting/{code}", response_class=HTMLResponse)
    def manage_add_waiting(code: str, request: Request, trap_id: str = Form(...), name: str = Form(default=""),
                           block: str = Form(default=""), lure: str = Form(default="CM"), db: Session = Depends(get_session)):
        """Add a camera that powered on near a hub and is waiting: its key goes to the camera through the hub."""
        try:
            trap = fleet.add_waiting_camera(db, code, trap_id.strip(), name.strip()[:120], block.strip()[:120], lure)
        except ValueError as e:
            return manage_page(request, db, error=str(e), status_code=422)
        return manage_page(request, db, new_key={"trap": trap, "key": None, "why": "paired"})

    @app.post("/manage/firmware", response_class=HTMLResponse)
    def manage_firmware_upload(request: Request, file: UploadFile = File(...), note: str = Form(default=""),
                               db: Session = Depends(get_session)):
        try:
            fleet.add_firmware(db, file.file.read(fleet.MAX_FIRMWARE + 1), note.strip())
        except ValueError as e:
            return manage_page(request, db, error=str(e), status_code=422)
        return RedirectResponse("/manage#firmware", status_code=303)

    @app.post("/manage/firmware/target", response_class=HTMLResponse)
    def manage_firmware_target(request: Request, version: str = Form(default=""), trap_id: str = Form(default="all"),
                               db: Session = Depends(get_session)):
        """Send a firmware version to one ESP32 camera or all of them (empty version: stop sending one)."""
        ids = [t.id for t in db.scalars(select(Trap).where(Trap.kind == "esp32", Trap.retired_at.is_(None)))] \
            if trap_id == "all" else [trap_id]
        try:
            fleet.set_firmware_target(db, version or None, ids)
        except ValueError as e:
            return manage_page(request, db, error=str(e), status_code=422)
        return RedirectResponse("/manage#firmware", status_code=303)

    @app.post("/manage/traps/{trap_id}/{action}", response_class=HTMLResponse)
    def manage_action(trap_id: str, action: str, request: Request, db: Session = Depends(get_session)):
        trap = db.get(Trap, trap_id)
        if trap is None:
            raise HTTPException(404, "no such trap")
        if action == "remove":
            services.retire_trap(db, trap)
        elif action == "restore":
            services.restore_trap(db, trap)
        elif action == "new-key":
            key = services.new_api_key()
            trap.api_key_hash = services.hash_key(key)
            fleet.hub_key_used(db, trap)  # a hub's pairing claim would still hand out the old key
            return manage_page(request, db, new_key={"trap": trap, "key": key, "why": "new key"})
        else:
            raise HTTPException(404, "unknown action")
        return RedirectResponse("/manage", status_code=303)

    @app.get("/captures/{capture_id}", response_class=HTMLResponse)
    def capture_page(capture_id: int, request: Request, db: Session = Depends(get_session)):
        cap = db.get(Capture, capture_id)
        if cap is None:
            raise HTTPException(404, "no such photo")
        tracks = {d.track_id: db.get(Track, d.track_id) for d in cap.detections if d.track_id}
        trap = db.get(Trap, cap.trap_id)
        return templates.TemplateResponse(request, "capture.html", {
            "cap": cap, "tracks": tracks, "trap": trap, "located": weather.location(db, trap) is not None,
            "wx_pending": cap.captured_at >= utcnow() - weather.LOOK_BACK,
            "hub": db.get(Trap, trap.hub_id) if trap.hub_id else None,
        })

    @app.get("/review", response_class=HTMLResponse)
    def review_page(request: Request, db: Session = Depends(get_session)):
        items = []
        for t in services.pending_reviews(db)[:60]:
            det = db.scalar(select(Detection).where(Detection.track_id == t.id).order_by(Detection.det_conf.desc()))
            items.append({"track": t, "det": det, "trap": db.get(Trap, det.capture.trap_id) if det else None})
        return templates.TemplateResponse(request, "review.html", {"items": items})

    return app

