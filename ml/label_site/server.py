"""The labelling site's web server (standard library http.server; Pillow + OpenCV only for re-cropping moved boxes
and click-to-box). Run with `python -m label_site serve`; see label_site/__main__.py.

Every page but /login needs a login (auth.py). Labellers see their own tasks only; admins (users.json "admin")
also review, see the dashboard and export. Hidden test photos and double-labelled photos look like any other
task to the labeller.
"""

from __future__ import annotations

import io
import json
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import workflow
from .auth import COOKIE, Auth, read_cookie
from .db import ATTRS, TAGS, Conflict, Store

STATIC = Path(__file__).parent / "static"
STATIC_TYPES = {".js": "text/javascript", ".css": "text/css", ".html": "text/html; charset=utf-8", ".woff2": "font/woff2"}


def static_files() -> dict[str, Path]:
    """The files the site serves under /static/, by name (read each time, so a font dropped in shows up)."""
    return {f.name: f for f in STATIC.iterdir() if f.is_file() and f.suffix in STATIC_TYPES}
LABELS = {"", "moth", "other_insect", "debris", "skip", "CM", "OFM", "OBLR", "lookalike_RBLR", "lookalike_LAW",
          "other_tortricid", "other_moth"}
MAX_BODY = 2_000_000
ISSUE_KINDS = {"wrong_label", "missed_insect", "loose_box", "not_insect", "species", "other", "disagree"}
PUBLIC_KIND = {"label": "label", "double": "label", "gold_check": "label", "tiebreak": "tiebreak",
               "gold_truth": "reference", "species": "species"}  # what the labeller is told


def clean_boxes(boxes, size: tuple[int, int] | None = None) -> list[dict]:
    """The page's boxes, checked. A box dragged partly off the photo is pulled back onto it (one bad corner must
    never stop a whole photo from saving, which it did on Oct 26 2026); only garbage raises ValueError."""
    if not isinstance(boxes, list) or len(boxes) > 5000:
        raise ValueError("boxes")
    W, H = size or (1e5, 1e5)
    out = []
    for b in boxes:
        if not isinstance(b, dict) or b.get("label", "") not in LABELS:
            raise ValueError("label")
        c = {k: float(b[k]) for k in ("x1", "y1", "x2", "y2")}
        if not all(abs(v) < 1e6 for v in c.values()):
            raise ValueError("box")
        x1, x2 = sorted((min(max(c["x1"], 0.0), W - 1), min(max(c["x2"], 0.0), W)))
        y1, y2 = sorted((min(max(c["y1"], 0.0), H - 1), min(max(c["y2"], 0.0), H)))
        c = {"x1": x1, "y1": y1, "x2": max(x2, x1 + 1), "y2": max(y2, y1 + 1)}
        attrs = sorted(a for a in str(b.get("attrs", "")).split(",") if a)
        if not set(attrs) <= ATTRS:
            raise ValueError("attrs")
        bid = b.get("id")
        out.append({**c, "id": int(bid) if bid is not None else None, "label": b.get("label", ""),
                    "attrs": ",".join(attrs), "locked": 1 if b.get("locked") else 0,
                    "confirm": bool(b.get("confirm")), "unlock": bool(b.get("unlock"))})
    return out


_sizes: dict[str, tuple[int, int]] = {}


def photo_size(site: Path, photo: str) -> tuple[int, int]:
    """Width, height as the page shows the photo (EXIF rotation applied), read from the header only."""
    if photo not in _sizes:
        from PIL import Image

        with Image.open(site / "inbox" / photo) as im:
            w, h = im.size
            if im.getexif().get(274) in (5, 6, 7, 8):  # rotated 90 or 270 degrees
                w, h = h, w
        _sizes[photo] = (w, h)
    return _sizes[photo]


class Images:
    """The last few photos opened, decoded, for re-cropping and click-to-box."""

    def __init__(self, site: Path, keep: int = 3):
        self.site, self.keep, self.cache = site, keep, {}

    def get(self, photo: str):
        from PIL import Image, ImageOps

        if photo not in self.cache:
            with Image.open(self.site / "inbox" / photo) as im:
                self.cache[photo] = ImageOps.exif_transpose(im).convert("RGB")
            while len(self.cache) > self.keep:
                self.cache.pop(next(iter(self.cache)))
        return self.cache[photo]


def make_remeasure(site: Path, images: Images):
    def remeasure(row: dict, photo: str | None = None) -> dict:
        from crop_field_cards import box_lengths, server_crop

        photo = photo or row["photo"]
        img = images.get(photo)
        box = [int(round(float(row[k]))) for k in ("x1", "y1", "x2", "y2")]
        stem = Path(photo).stem
        crop = site / "crops" / stem / f"{stem}_s{int(time.time() * 1000) % 10**9}.jpg"
        crop.parent.mkdir(parents=True, exist_ok=True)
        server_crop(img, box).save(crop, quality=90)
        return {"crop": str(crop), **box_lengths(img, {**row, "x1": box[0], "y1": box[1], "x2": box[2], "y2": box[3]})}
    return remeasure


def grab_box(img, x: float, y: float, ppm: float | None) -> dict | None:
    """Click-to-box: GrabCut in a window around the click (about 24 mm, or 300 px without a scale); the piece
    under the click, as a box. None if there's nothing there."""
    import cv2
    import numpy as np

    half = int((12 * ppm) if ppm else 150)
    x0, y0 = max(0, int(x) - half), max(0, int(y) - half)
    x1, y1 = min(img.width, int(x) + half), min(img.height, int(y) + half)
    region = np.asarray(img.crop((x0, y0, x1, y1)))
    s = min(1.0, 300 / max(region.shape[:2]))
    small = cv2.resize(region, None, fx=s, fy=s, interpolation=cv2.INTER_AREA) if s < 1 else region
    h, w = small.shape[:2]
    mask = np.full((h, w), cv2.GC_PR_BGD, np.uint8)
    mask[:3, :] = mask[-3:, :] = mask[:, :3] = mask[:, -3:] = cv2.GC_BGD
    cx, cy = int((x - x0) * s), int((y - y0) * s)
    r = max(2, int(min(h, w) * 0.04))
    mask[max(0, cy - r):cy + r, max(0, cx - r):cx + r] = cv2.GC_FGD
    try:
        cv2.grabCut(cv2.cvtColor(small, cv2.COLOR_RGB2BGR), mask, None, np.zeros((1, 65)), np.zeros((1, 65)), 5,
                    cv2.GC_INIT_WITH_MASK)
    except cv2.error:
        return None
    fg = ((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD)).astype(np.uint8)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(fg)
    k = lab[min(h - 1, cy), min(w - 1, cx)]
    if n < 2 or k == 0:
        return None
    bx, by, bw, bh = stats[k, :4]
    return {"x1": x0 + bx / s, "y1": y0 + by / s, "x2": x0 + (bx + bw) / s, "y2": y0 + (by + bh) / s}


def coco_export(store: Store) -> dict:
    cats = ["moth", "other_insect", "debris"]
    images, anns = [], []
    for i, p in enumerate(store.q("SELECT * FROM photos ORDER BY name"), 1):
        images.append({"id": i, "file_name": p["source"], "site_name": p["name"], "set": p["set_name"]})
        for b in store.boxes(p["name"], "main"):
            lab = "moth" if b["label"] not in ("other_insect", "debris", "skip", "") else b["label"]
            if lab not in cats:
                continue
            w, h = float(b["x2"]) - float(b["x1"]), float(b["y2"]) - float(b["y1"])
            anns.append({"id": len(anns) + 1, "image_id": i, "category_id": cats.index(lab) + 1,
                         "bbox": [float(b["x1"]), float(b["y1"]), w, h], "area": w * h, "iscrowd": 0,
                         "species": b["label"] if lab == "moth" else "", "checked_by": b["by"],
                         "attributes": b["attrs"]})
    return {"images": images, "annotations": anns,
            "categories": [{"id": i + 1, "name": c} for i, c in enumerate(cats)]}


def yolo_export(store: Store, site: Path) -> bytes:
    """One .txt per photo (class cx cy w h, normalised), classes.txt and images.txt (source paths, from ml/)."""
    from PIL import Image

    cats = ["moth", "other_insect", "debris"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("classes.txt", "\n".join(cats) + "\n")
        lines = []
        for p in store.q("SELECT * FROM photos ORDER BY name"):
            with Image.open(site / "inbox" / p["name"]) as im:
                from PIL import ImageOps

                W, H = ImageOps.exif_transpose(im).size
            rows = []
            for b in store.boxes(p["name"], "main"):
                lab = "moth" if b["label"] not in ("other_insect", "debris", "skip", "") else b["label"]
                if lab not in cats:
                    continue
                x1, y1, x2, y2 = (float(b[k]) for k in ("x1", "y1", "x2", "y2"))
                rows.append(f"{cats.index(lab)} {(x1 + x2) / 2 / W:.6f} {(y1 + y2) / 2 / H:.6f} {(x2 - x1) / W:.6f} {(y2 - y1) / H:.6f}")
            z.writestr(f"labels/{Path(p['name']).stem}.txt", "\n".join(rows) + ("\n" if rows else ""))
            lines.append(f"{p['name']}\t{p['source']}")
        z.writestr("images.txt", "\n".join(lines) + "\n")
    return buf.getvalue()


def handler(store: Store, auth: Auth, secure: bool, species_experts: list[str]):
    images = Images(store.site)
    remeasure = make_remeasure(store.site, images)

    class H(BaseHTTPRequestHandler):
        server_version = "labels"
        sys_version = ""

        def log_message(self, *a):
            pass

        def send(self, body: bytes, ctype: str, code: int = 200, headers: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store" if not ctype.startswith("image/") else "private, max-age=3600")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' blob: data:; "
                             "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
                             "script-src 'self'; frame-ancestors 'none'; form-action 'self'")  # Lora from Google Fonts
            if secure:
                self.send_header("Strict-Transport-Security", "max-age=31536000")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def json(self, obj, code: int = 200):
            self.send(json.dumps(obj).encode(), "application/json", code)

        def cookie(self):
            return read_cookie(self.headers.get("Cookie"), COOKIE)

        def user(self) -> str:
            return auth.user_of(self.cookie()) or ""

        def set_cookie(self, value: str, max_age: int) -> str:
            return f"{COOKIE}={value}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Strict" + ("; Secure" if secure else "")

        def body(self) -> bytes:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ValueError("too big")
            return self.rfile.read(n)

        def admin_post(self, path: str, body: dict, user: str):
            """Assignment changes from the dashboard: move one photo, pause or resume a person, hand out their photos."""
            who = str(body.get("user", "")).lower()
            labellers = sorted(u for u in auth.users if not auth.is_admin(u))
            try:
                if path == "/api/admin/reassign":
                    t = store.task(int(body["task"]))
                    to = str(body.get("to", "")).lower()
                    if not t or to not in auth.users:
                        return self.send(b"unknown task or person", "text/plain", 400)
                    if t["kind"] == "gold_truth" and not auth.is_admin(to):
                        return self.send(b"reference photos are labelled by admins only", "text/plain", 409)
                    return self.json({"message": workflow.reassign(store, t, to, user)})
                if path == "/api/admin/panels":
                    w = [int(body["left"]), int(body["right"])]
                    if not all(170 <= x <= 640 for x in w):
                        return self.send(b"widths must be 170-640 px", "text/plain", 400)
                    store.set_setting("panels", w)
                    return self.json({"message": f"default widths for everyone: left {w[0]} px, right {w[1]} px"})
                if path == "/api/admin/pause":
                    if who not in auth.users:
                        return self.send(b"unknown person", "text/plain", 400)
                    if body.get("on") and body.get("release"):
                        got = workflow.release(store, who, labellers, user)
                        return self.json({"message": f"{who} paused: {got['moved']} photos handed out, "
                                                     f"{got['dropped_tests']} hidden tests dropped, {got['kept_started']} started ones kept"})
                    workflow.set_paused(store, who, bool(body.get("on")))
                    return self.json({"message": f"{who} {'paused' if body.get('on') else 'resumed'}"})
            except (ValueError, KeyError, TypeError) as e:
                return self.send(str(e).encode(), "text/plain", 409)
            return self.send(b"not found", "text/plain", 404)

        def my_task(self, user: str, task_id) -> dict | None:
            """A task the user may open: their own, or any for an admin (to review)."""
            try:
                t = store.task(int(task_id))
            except (TypeError, ValueError):
                return None
            if t and (t["user"] == user or auth.is_admin(user)):
                return t
            return None

        # -- GET
        def do_GET(self):
            url = urlparse(self.path)
            path, qs = url.path, parse_qs(url.query)
            if path == "/login":
                return self.send((STATIC / "login.html").read_text().replace("__MSG__", "").encode(), "text/html; charset=utf-8")
            if path in ("/static/login.css", "/static/login.js"):  # the login page's own files, before logging in
                name = path[8:]
                return self.send((STATIC / name).read_bytes(), "text/css" if name.endswith(".css") else "text/javascript")
            user = self.user()
            if not user:
                if path in ("/", "/dashboard"):
                    return self.send(b"", "text/plain", 303, {"Location": "/login"})
                return self.send(b"log in first", "text/plain", 401)
            admin = auth.is_admin(user)
            if path == "/":
                return self.send((STATIC / "app.html").read_bytes(), "text/html; charset=utf-8")
            if path == "/dashboard" and admin:
                return self.send((STATIC / "dashboard.html").read_bytes(), "text/html; charset=utf-8")
            if path.startswith("/static/"):
                f = static_files().get(unquote(path[8:]))  # looked up by name: the URL never becomes a path
                if f:
                    return self.send(f.read_bytes(), STATIC_TYPES[f.suffix])
            if path.startswith("/guide/"):
                guide = (store.site / "guide").resolve()
                f = (guide / Path(unquote(path[7:])).name).resolve()
                if f.parent == guide and f.is_file() and f.suffix.lower() in (".jpg", ".png"):
                    return self.send(f.read_bytes(), "image/jpeg" if f.suffix.lower() == ".jpg" else "image/png")
            if path == "/api/me":
                return self.json({"user": user, "admin": admin, "species": user in species_experts,
                                  "csrf": auth.csrf(self.cookie() or ""), "panels": store.setting("panels")})
            if path == "/api/queue":
                mine = store.q("SELECT t.*, (SELECT count(*) FROM boxes b WHERE b.photo=t.photo AND b.copy=t.copy AND b.label!='skip') AS n,"
                               " (SELECT count(*) FROM boxes b WHERE b.photo=t.photo AND b.copy=t.copy AND b.label!='skip' AND (b.by='' OR b.label='')) AS unchecked,"
                               " (SELECT count(*) FROM issues i WHERE i.photo=t.photo AND i.copy=t.copy AND i.resolved_at IS NULL) AS issues"
                               " FROM tasks t WHERE t.user=? ORDER BY CASE t.status WHEN 'returned' THEN 0 WHEN 'open' THEN 1"
                               " WHEN 'done' THEN 2 ELSE 3 END, t.priority DESC, t.id", user)
                items = [{"id": t["id"], "photo": t["photo"], "kind": PUBLIC_KIND[t["kind"]], "status": t["status"],
                          "n": t["n"], "unchecked": t["unchecked"], "issues": t["issues"], "note": t["note"]} for t in mine]
                review = []
                if admin:
                    review = [{"id": t["id"], "photo": t["photo"], "kind": t["kind"], "user": t["user"], "status": t["status"]}
                              for t in store.q("SELECT * FROM tasks WHERE status='done' AND kind IN ('label','tiebreak','species')"
                                               " ORDER BY done_at")]
                return self.json({"tasks": items, "review": review, "paused": user in workflow.paused(store)})
            if path == "/api/photo":
                t = self.my_task(user, (qs.get("task") or [None])[0])
                if not t:
                    return self.send(b"not your task", "text/plain", 403)
                p = store.q("SELECT * FROM photos WHERE name=?", t["photo"])[0]
                boxes = store.boxes(t["photo"], t["copy"])
                issues = store.q("SELECT * FROM issues WHERE photo=? AND copy=? ORDER BY at", t["photo"], t["copy"])
                tags = [r["tag"] for r in store.q("SELECT tag FROM tags WHERE photo=? AND user=?", t["photo"], user)]
                shots = [r["name"] for r in store.q("SELECT name FROM photos WHERE card=? AND set_name=? AND name!=?",
                                                    p["card"], p["set_name"], p["name"])]
                return self.json({"task": {"id": t["id"], "kind": PUBLIC_KIND[t["kind"]], "status": t["status"],
                                           "note": t["note"], "user": t["user"]},
                                  "photo": {"name": p["name"], "set": p["set_name"], "px_per_mm": p["px_per_mm"],
                                            "why": p["why"], "other_shots": shots},
                                  "boxes": [view(b) for b in boxes], "version": store.version(t["photo"], t["copy"]),
                                  "issues": issues, "tags": tags})
            if path.startswith("/img/"):
                name = Path(unquote(path[5:])).name
                if store.q("SELECT 1 FROM photos WHERE name=?", name):
                    if not admin and not store.q("SELECT 1 FROM tasks WHERE photo=? AND user=?", name, user):
                        return self.send(b"not your photo", "text/plain", 403)
                    return self.send((store.site / "inbox" / name).read_bytes(), "image/jpeg")
            if path == "/api/dashboard" and admin:
                d = workflow.dashboard(store, sorted(auth.users))
                d["admins"] = sorted(u for u in auth.users if auth.is_admin(u))
                return self.json(d)
            if path == "/api/export/coco.json" and admin:
                return self.send(json.dumps(coco_export(store)).encode(), "application/json",
                                 headers={"Content-Disposition": "attachment; filename=labels-coco.json"})
            if path == "/api/export/yolo.zip" and admin:
                return self.send(yolo_export(store, store.site), "application/zip",
                                 headers={"Content-Disposition": "attachment; filename=labels-yolo.zip"})
            self.send(b"not found", "text/plain", 404)

        # -- POST
        def do_POST(self):
            path = urlparse(self.path).path
            try:
                raw = self.body()
            except ValueError:
                return self.send(b"too big", "text/plain", 413)
            if path == "/login":
                form = parse_qs(raw.decode("utf-8", "replace"))
                name, pw = (form.get("name") or [""])[0][:64], (form.get("password") or [""])[0][:256]
                if auth.locked(name.strip().lower()):
                    msg = "Too many wrong tries for that name. Wait 15 minutes."
                elif who := auth.login(name, pw):
                    return self.send(b"", "text/plain", 303, {"Location": "/",
                                     "Set-Cookie": self.set_cookie(auth.make_cookie(who), 14 * 24 * 3600)})
                else:
                    msg = "Wrong name or password."
                page = (STATIC / "login.html").read_text().replace("__MSG__", msg)
                return self.send(page.encode(), "text/html; charset=utf-8", 401)
            user = self.user()
            if not user:
                return self.send(b"log in first", "text/plain", 401)
            if not auth.csrf_ok(self.cookie(), self.headers.get("X-CSRF")):
                return self.send(b"bad request token: reload the page", "text/plain", 403)
            if path == "/logout":
                return self.send(b"", "text/plain", 303, {"Location": "/login", "Set-Cookie": self.set_cookie("", 0)})
            try:
                body = json.loads(raw or b"{}")
            except ValueError:
                return self.send(b"bad request", "text/plain", 400)
            if path.startswith("/api/admin/"):
                if not auth.is_admin(user):
                    return self.send(b"admins only", "text/plain", 403)
                return self.admin_post(path, body, user)
            t = self.my_task(user, body.get("task"))
            if not t:
                return self.send(b"not your task", "text/plain", 403)
            admin = auth.is_admin(user)
            if path == "/api/save":
                if t["status"] == "accepted" and not admin:
                    return self.send(b"this photo was accepted; ask a reviewer to reopen it", "text/plain", 409)
                try:
                    boxes = clean_boxes(body.get("boxes"), photo_size(store.site, t["photo"]))
                except (ValueError, KeyError, TypeError) as e:
                    return self.send(f"the server refused this save ({e}); tell nina".encode(), "text/plain", 400)
                try:
                    rows = store.save(t["photo"], t["copy"], boxes, user, body.get("base"), remeasure)
                except Conflict:
                    return self.json({"boxes": [view(b) for b in store.boxes(t["photo"], t["copy"])],
                                      "version": store.version(t["photo"], t["copy"])}, 409)
                if t["status"] == "returned" and t["user"] == user:
                    pass  # stays returned until they press Done again
                return self.json({"boxes": [view(b) for b in rows], "version": store.version(t["photo"], t["copy"])})
            if path == "/api/done":
                if t["user"] != user:
                    return self.send(b"only the person it's assigned to can finish it", "text/plain", 403)
                return self.json({"message": workflow.done(store, t, user)})
            if path == "/api/review":
                if not admin:
                    return self.send(b"admins only", "text/plain", 403)
                workflow.review(store, t, user, bool(body.get("accept")), str(body.get("note", "")), species_experts)
                return self.json({"ok": True})
            if path == "/api/issue":
                kind = body.get("kind")
                if kind not in ISSUE_KINDS:
                    return self.send(b"bad kind", "text/plain", 400)
                bid = body.get("box_id")
                iid = store.add_issue(t["photo"], t["copy"], int(bid) if bid is not None else None, float(body["x"]),
                                      float(body["y"]), kind, str(body.get("text", ""))[:1000], user)
                return self.json({"id": iid})
            if path == "/api/issue/resolve":
                store.resolve_issue(int(body["id"]), user)
                return self.json({"ok": True})
            if path == "/api/tag":
                if body.get("tag") not in TAGS:
                    return self.send(b"bad tag", "text/plain", 400)
                store.set_tag(t["photo"], user, body["tag"], bool(body.get("on")))
                return self.json({"ok": True})
            if path == "/api/grab":
                p = store.q("SELECT px_per_mm FROM photos WHERE name=?", t["photo"])[0]
                box = grab_box(images.get(t["photo"]), float(body["x"]), float(body["y"]), p["px_per_mm"])
                return self.json({"box": box})
            self.send(b"not found", "text/plain", 404)

    return H


def view(b: dict) -> dict:
    return {"id": b["id"], "label": b["label"], "source": b["source"], "x1": float(b["x1"]), "y1": float(b["y1"]),
            "x2": float(b["x2"]), "y2": float(b["y2"]), "conf": b["conf"], "detector_label": b["detector_label"],
            "model_label": b["model_label"], "model_conf": b["model_conf"], "old_label": b["old_label"],
            "by": b["by"], "attrs": b["attrs"] or "", "locked": bool(b["locked"]), "length_mm": b["length_mm"],
            "body_mm": b["body_mm"], "length_from": b["length_from"]}


def serve(site: Path, auth_dir: Path, host: str, port: int, secure: bool, species_experts: list[str]) -> None:
    store = Store(site)
    auth = Auth(auth_dir / "users.json", auth_dir / "secret")
    srv = ThreadingHTTPServer((host, port), handler(store, auth, secure, species_experts))
    n = store.q("SELECT count(*) AS n FROM photos")[0]["n"]
    print(f"Labelling site: {n} photos, {len(auth.users)} logins, http://{host}:{port}  (Ctrl+C to stop)", flush=True)
    srv.serve_forever()
