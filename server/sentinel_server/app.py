"""FastAPI app: device upload API + the team dashboard (no login; reach it over Tailscale)."""

from __future__ import annotations

import io
import json
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import __version__, services
from .db import get_session, init_db
from .models import PESTS, SPECIES, SPECIES_LABELS, Capture, Detection, Event, Review, Track, Trap, utcnow
from .settings import get_settings

HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(HERE / "templates"))


def _local(dt: datetime | None, fmt: str = "%b %d %H:%M") -> str:
    if dt is None:
        return "—"
    return dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(get_settings().timezone)).strftime(fmt)


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
templates.env.globals.update(SPECIES=SPECIES, SPECIES_LABELS=SPECIES_LABELS, PESTS=PESTS, version=__version__)


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

    # ---------------------------------------------------------------- device API

    def device_trap(authorization: str = Header(default=""), db: Session = Depends(get_session)) -> Trap:
        key = authorization.removeprefix("Bearer ").strip()
        trap = db.scalar(select(Trap).where(Trap.api_key_hash == services.hash_key(key))) if key else None
        if trap is None:
            raise HTTPException(401, "unknown or missing trap API key")
        return trap

    @app.post("/api/v1/captures", status_code=201)
    async def upload_capture(
        image: UploadFile = File(...),
        meta: str = Form(...),
        trap: Trap = Depends(device_trap),
        db: Session = Depends(get_session),
    ):
        try:
            m = json.loads(meta)
            captured = datetime.fromisoformat(m["captured_at"])
        except (ValueError, KeyError, TypeError) as e:
            raise HTTPException(422, f"bad meta: {e}")
        if m.get("trap_id") not in (None, trap.id):
            raise HTTPException(422, f"meta trap_id {m.get('trap_id')!r} does not match this key's trap {trap.id!r}")
        captured = captured.astimezone(timezone.utc).replace(tzinfo=None) if captured.tzinfo else captured
        uid = str(m.get("capture_uid") or Path(image.filename or "capture").stem)

        existing = db.scalar(select(Capture).where(Capture.trap_id == trap.id, Capture.uid == uid))
        if existing is not None:
            return JSONResponse(
                {"capture_id": existing.id, "card_id": existing.card_id, "config": trap.device_config or {}, "duplicate": True},
                status_code=409,
            )

        data = await image.read()
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
        except Exception:
            raise HTTPException(422, "image is not a readable picture")

        card = services.open_card(db, trap.id)
        if card is None or m.get("new_card"):
            card = services.start_new_card(db, trap.id, at=captured, note="from trap" if m.get("new_card") else "first photo")

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
        db.flush()
        return {"capture_id": cap.id, "card_id": card.id, "config": trap.device_config or {}}

    @app.get("/api/v1/traps")
    def api_traps(db: Session = Depends(get_session)):
        out = []
        for t in db.scalars(select(Trap).order_by(Trap.id)):
            h = services.trap_health(db, t)
            out.append({
                "id": t.id, "name": t.name, "lure": t.lure, "state": h["state"],
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
    def new_card(trap_id: str, note: str = Form(default="installed from dashboard"), db: Session = Depends(get_session)):
        if db.get(Trap, trap_id) is None:
            raise HTTPException(404, "no such trap")
        services.start_new_card(db, trap_id, note=note)
        return RedirectResponse(f"/traps/{trap_id}", status_code=303)

    @app.post("/tracks/{track_id}/review")
    def review(track_id: int, label: str = Form(...), reviewer: str = Form(default=""), next: str = Form(default="/review"),
               db: Session = Depends(get_session)):
        t = db.get(Track, track_id)
        if t is None:
            raise HTTPException(404, "no such insect")
        if label == "reject":
            t.review_status = "rejected"
        elif label in SPECIES:
            t.reviewed_label = label
            t.review_status = "confirmed"
        else:
            raise HTTPException(422, f"unknown label {label!r}")
        db.add(Review(track_id=t.id, label=label, reviewer=reviewer[:60]))
        return RedirectResponse(next if next.startswith("/") else "/review", status_code=303)

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
        for t in db.scalars(select(Trap).order_by(Trap.id)):
            rows.append({
                "trap": t, "health": services.trap_health(db, t), "week": services.week_counts(db, t.id),
                "pending": len(services.pending_reviews(db, t.id)), "card": services.open_card(db, t.id),
                "pheno": services.phenology_status(db, t),
            })
        events = list(db.scalars(select(Event).order_by(Event.at.desc()).limit(12)))
        return templates.TemplateResponse(request, "overview.html", {"rows": rows, "events": events})

    @app.get("/traps/{trap_id}", response_class=HTMLResponse)
    def trap_page(trap_id: str, request: Request, db: Session = Depends(get_session)):
        trap = db.get(Trap, trap_id)
        if trap is None:
            raise HTTPException(404, "no such trap")
        caps = list(db.scalars(select(Capture).where(Capture.trap_id == trap_id).order_by(Capture.captured_at.desc()).limit(40)))
        daily = services.daily_counts(db, trap_id, 30)
        peak = max([sum(r["counts"].values()) for r in daily] + [1])
        latest = caps[0] if caps else None
        tracks = {d.track_id: db.get(Track, d.track_id) for d in latest.detections if d.track_id} if latest else {}
        return templates.TemplateResponse(request, "trap.html", {
            "trap": trap, "caps": caps, "latest": latest, "tracks": tracks, "daily": daily, "peak": peak,
            "health": services.trap_health(db, trap), "card": services.open_card(db, trap_id),
            "pheno": services.phenology_status(db, trap), "pending": len(services.pending_reviews(db, trap_id)),
        })

    @app.get("/captures/{capture_id}", response_class=HTMLResponse)
    def capture_page(capture_id: int, request: Request, db: Session = Depends(get_session)):
        cap = db.get(Capture, capture_id)
        if cap is None:
            raise HTTPException(404, "no such photo")
        tracks = {d.track_id: db.get(Track, d.track_id) for d in cap.detections if d.track_id}
        return templates.TemplateResponse(request, "capture.html", {"cap": cap, "tracks": tracks, "trap": db.get(Trap, cap.trap_id)})

    @app.get("/review", response_class=HTMLResponse)
    def review_page(request: Request, db: Session = Depends(get_session)):
        items = []
        for t in services.pending_reviews(db)[:60]:
            det = db.scalar(select(Detection).where(Detection.track_id == t.id).order_by(Detection.det_conf.desc()))
            items.append({"track": t, "det": det})
        return templates.TemplateResponse(request, "review.html", {"items": items})

    return app

