# Code Review Report: Orchard Sentinel (Chunk 3 of 3)

**Scope Reviewed**:
- `device/sentinel_device/tools/camfeed.py`
- `device/sentinel_device/tools/flatfield.py`
- `device/sentinel_device/tools/focus_sweep.py`
- `device/sentinel_device/uploader.py`
- `device/systemd/sentinel-cycle.service`
- `device/systemd/sentinel-gateway.service`
- `device/tests/test_camera_bench.py`
- `device/tests/test_device.py`
- `device/tests/test_gateway.py`
- `server/sentinel_server/api.py`
- `server/sentinel_server/app.py`
- `server/sentinel_server/static/app.css`

---

## 1. Protocol & Architectural Alignment (ESP32 Node ↔ Gateway ↔ Server)

The capture-forward flow works as follows:
1. **ESP32 Node → Gateway**: The node sends `POST /node/v1/captures` with `Authorization: Bearer <node_key>`, header `X-Sentinel-Meta` (containing `node_capture_id`, `clock_synced`, `captured_at` or `age_s`, `device`, `env`, `power`), and binary JPEG body. The gateway caches the node's plaintext key in `nodes/<node_id>/key` upon receipt.
2. **Gateway → Server**: The gateway queues photos and metadata (`<uid>.jpg` + `<uid>.json`), and forwards them via `uploader.drain()` calling `POST /api/v1/captures` using multipart/form-data (`image` file + `meta` JSON form field) signed with the node's cached Bearer key.
3. **Gateway Sync with Server**: The gateway polls `GET /api/v1/hub/nodes` using the hub's key to fetch node hashes and active `photo_requests`.

Several subtle integration issues exist in this chain (detailed below): case-sensitive auth token extraction on the server, naive local datetime handling causing liner misattribution, and unhandled `None` cards triggering infinite 500-retry loops on the gateway/uploader.

---

## 2. Findings by Category

### Category 1: Bugs (Correctness, Crashes, Race Conditions, Timezones, Error Handling)

#### 1. Server crashes on startup if `media_dir` does not exist
- **File**: `server/sentinel_server/app.py:76-78`
- **Severity**: High
- **Relevant Code**:
  ```python
  76|     settings = get_settings()
  77|     app.mount("/media", StaticFiles(directory=str(settings.media_dir)), name="media")
  78|     app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
  ```
- **Concrete Failure Scenario**: Starlette's `StaticFiles` checks `os.path.isdir(directory)` during instantiation. On a clean deployment, container build, or fresh server setup where `settings.media_dir` has not been pre-created on disk, calling `create_app()` raises `RuntimeError: Directory '.../media' does not exist`, crashing the application immediately upon boot before it can bind or serve traffic.
- **Suggested Fix**: Create the directory before mounting:
  ```python
  settings.media_dir.mkdir(parents=True, exist_ok=True)
  app.mount("/media", StaticFiles(directory=str(settings.media_dir)), name="media")
  ```

---

#### 2. Naive datetime comparison causes liner misattribution or 500 error
- **File**: `server/sentinel_server/app.py:120-125, 148`
- **Severity**: High
- **Relevant Code**:
  ```python
  120|             captured = datetime.fromisoformat(m["captured_at"])
  ...
  125|         captured = captured.astimezone(timezone.utc).replace(tzinfo=None) if captured.tzinfo else captured
  ...
  148|         if current is None or (m.get("new_card") and current.installed_at < captured):
  ```
- **Concrete Failure Scenario**: If an ESP32 or client sends an ISO timestamp without timezone offset (e.g. `"2026-10-05T19:30:00"` naive local time), `captured.tzinfo` is `None`. Line 125 leaves `captured` as naive without converting it to UTC. When line 148 executes:
  1. If `current.installed_at` in SQLite is UTC-based, `current.installed_at < captured` compares local time directly against UTC. In Eastern Daylight Time (UTC-4), a capture at 19:30 EDT (23:30 UTC) is compared as 19:30 against a card installed at 21:00 UTC (17:00 EDT). The check `21:00 < 19:30` evaluates to `False`, failing to open the new card.
  2. If `current.installed_at` is timezone-aware and `captured` is naive, Python raises `TypeError: can't compare offset-naive and offset-aware datetimes`, crashing `upload_capture` with a 500 error.
- **Suggested Fix**: Explicitly convert naive input timestamps to UTC:
  ```python
  if captured.tzinfo is None:
      captured = captured.replace(tzinfo=timezone.utc)
  captured = captured.astimezone(timezone.utc).replace(tzinfo=None)
  ```

---

#### 3. Unhandled `None` card from `services.card_at` causes 500 crash and infinite retry loop
- **File**: `server/sentinel_server/app.py:147-151, 160`
- **Severity**: High
- **Relevant Code**:
  ```python
  147|         current = services.open_card(db, trap.id)
  148|         if current is None or (m.get("new_card") and current.installed_at < captured):
  149|             card = services.start_new_card(db, trap.id, at=captured, note="from trap" if m.get("new_card") else "first photo")
  150|         else:
  151|             card = services.card_at(db, trap.id, captured)
  ...
  160|             trap_id=trap.id, card_id=card.id, uid=uid, captured_at=captured, image_path=str(rel),
  ```
- **Concrete Failure Scenario**: If a trap uploads a backlog of photos taken prior to any registered liner, or at a timestamp where `services.card_at` finds no covering liner, `card` is `None`. Line 160 then calls `card.id`, triggering `AttributeError: 'NoneType' object has no attribute 'id'` and returning HTTP 500. Because 500 is not in `uploader.py`'s `PARK_STATUSES`, the device queue considers it a transient server problem and retries the same photo on every single cycle, permanently wedging the queue.
- **Suggested Fix**: Provide a fallback to attach to the current or oldest card if no matching card is found:
  ```python
  if card is None:
      card = current or services.start_new_card(db, trap.id, at=captured, note="retroactive fallback")
  ```

---

#### 4. Malformed `env` or `power` payloads crash `upload_capture` with 500
- **File**: `server/sentinel_server/app.py:158-162`
- **Severity**: Medium
- **Relevant Code**:
  ```python
  158|         env, power = m.get("env") or {}, m.get("power") or {}
  159|         cap = Capture(
  160|             trap_id=trap.id, card_id=card.id, uid=uid, captured_at=captured, image_path=str(rel),
  161|             wake_reason=m.get("wake_reason", ""), temp_c=env.get("temp_c"), rh=env.get("rh"),
  162|             battery_v=power.get("battery_v"), meta=m, status="new",
  163|         )
  ```
- **Concrete Failure Scenario**: If metadata contains `"env": 24.5` or `"power": 3.8` (floats instead of dicts), `env or {}` evaluates to `24.5` because non-zero numbers are truthy. Line 161 then executes `env.get("temp_c")`, raising `AttributeError: 'float' object has no attribute 'get'` and returning 500.
- **Suggested Fix**: Type-check mappings before calling `.get()`:
  ```python
  env = m.get("env") if isinstance(m.get("env"), dict) else {}
  power = m.get("power") if isinstance(m.get("power"), dict) else {}
  ```

---

#### 5. `ZeroDivisionError` in focus sweep when optimal focus is at infinity (`pos = 0.0`)
- **File**: `device/sentinel_device/tools/focus_sweep.py:70-71`
- **Severity**: Medium
- **Relevant Code**:
  ```python
  70|     best_pos, best = max(results, key=lambda r: min(r[1].values()))
  71|     print(f"\nBest lens_position = {best_pos:.2f}  (≈ {100 / best_pos:.1f} cm to the liner)")
  ```
- **Concrete Failure Scenario**: Lens focus in diopters measures $1/\text{distance in meters}$. 0.0 diopters corresponds to infinity focus. If a user runs `--start 0.0` and the highest sharpness score is at 0.0, line 71 executes `100 / best_pos`, raising `ZeroDivisionError: float division by zero`. In addition, if `--start` > `--stop`, `results` is empty and line 70 raises `ValueError: max() arg is an empty sequence`.
- **Suggested Fix**:
  ```python
  if not results:
      raise SystemExit("No positions scored.")
  best_pos, best = max(results, key=lambda r: min(r[1].values()))
  dist_text = f"≈ {100 / best_pos:.1f} cm" if best_pos > 0 else "infinity"
  print(f"\nBest lens_position = {best_pos:.2f}  ({dist_text} to the liner)")
  ```

---

#### 6. Segfault race condition on camera release and unhandled exception killing grab thread
- **File**: `device/sentinel_device/tools/camfeed.py:80-92, 129-134`
- **Severity**: Medium
- **Relevant Code**:
  ```python
  83|             ok, frame = cap.read()
  ...
  88|                     cap.release()
  89|                     time.sleep(1.0)
  90|                     cap = open_camera()
  ...
  129|     try:
  130|         server.serve_forever()
  131|     except KeyboardInterrupt:
  132|         pass
  133|     finally:
  134|         cap.release()
  ```
- **Concrete Failure Scenario**:
  1. On Ctrl-C, `main()` enters `finally: cap.release()`. The background daemon thread `grab()` is concurrently running `cap.read()`. In OpenCV, calling `.read()` on a `VideoCapture` while another thread calls `.release()` causes memory corruption and segmentation faults in libv4l2.
  2. If the USB camera glitches and re-enumerates slowly, `open_camera()` in line 90 can raise an exception (e.g. device path missing). Because line 90 is not wrapped in `try/except`, the grab thread terminates silently, leaving the browser stream permanently frozen.
- **Suggested Fix**: Use a `threading.Event()` shutdown flag to cleanly terminate `grab()` before releasing `cap`, and wrap `open_camera()` in `try/except Exception` inside `grab()`.

---

#### 7. `flatfield.py` raises `KeyError` when run on USB cameras or minimal configs
- **File**: `device/sentinel_device/tools/flatfield.py:75, 79`
- **Severity**: Low
- **Relevant Code**:
  ```python
  75|     gains = tuple(float(g) for g in cfg["camera"]["colour_gains"])
  ...
  79|     path = flatfield.save(data_dir, gain, exposure_us=cfg["camera"]["exposure_us"], colour_gains=gains)
  ```
- **Concrete Failure Scenario**: USB camera configurations specify `usb_controls` or `usb_wb_temperature` and do not define `colour_gains` or `exposure_us` under `[camera]`. When `sentinel-flatfield` is run on such a setup, it captures and averages the white-card shots, but crashes with `KeyError: 'colour_gains'` before saving `flatfield.npz`.
- **Suggested Fix**:
  ```python
  raw_gains = cfg["camera"].get("colour_gains", (1.0, 1.0))
  gains = tuple(float(g) for g in raw_gains)
  exp = cfg["camera"].get("exposure_us", 0)
  ```

---

#### 8. Lack of failure/timeout power-off leaves Pi battery draining to 0V
- **File**: `device/systemd/sentinel-cycle.service:11-15`
- **Severity**: Medium
- **Relevant Code**:
  ```python
  11| ExecStart=/opt/sentinel/venv/bin/sentinel-cycle --config /etc/sentinel/config.toml
  ...
  15| TimeoutStartSec=600
  ```
- **Concrete Failure Scenario**: If `sentinel-cycle` hangs (e.g. hung I2C bus read, Picamera2 deadlock, DNS resolution freeze), systemd kills the service after 600s. Because the process is killed before scheduling the next RTC wake or executing poweroff, the Pi stays awake and idle, draining the battery completely in the field.
- **Suggested Fix**: Add `FailureAction=poweroff` to `[Unit]` or an `ExecStopPost=/usr/bin/systemctl poweroff` backstop.

---

### Category 2: Security Issues

#### 1. Case-sensitive Bearer token extraction breaks RFC 7235 and rejects valid devices
- **File**: `server/sentinel_server/app.py:101-105`
- **Severity**: Medium
- **Relevant Code**:
  ```python
  101|     def device_trap(authorization: str = Header(default=""), db: Session = Depends(get_session)) -> Trap:
  102|         key = authorization.removeprefix("Bearer ").strip()
  103|         trap = db.scalar(select(Trap).where(Trap.api_key_hash == services.hash_key(key))) if key else None
  104|         if trap is None:
  105|             raise HTTPException(401, "unknown or missing trap API key")
  ```
- **Concrete Failure Scenario**: Per RFC 7235 §2.1, auth schemes are case-insensitive. If an ESP32 firmware or client sends `Authorization: bearer <key>` (lowercase), `removeprefix("Bearer ")` does not remove the prefix. `key` becomes `"bearer <key>"`. The server hashes `"bearer <key>"` instead of `<key>`, rejects the valid device with 401, and drops legitimate orchard captures.
- **Suggested Fix**:
  ```python
  scheme, _, key = authorization.partition(" ")
  if scheme.lower() != "bearer" or not key.strip():
      raise HTTPException(401, "unknown or missing trap API key")
  key = key.strip()
  ```

---

#### 2. Missing CSRF protection on state-changing dashboard POST endpoints
- **File**: `server/sentinel_server/app.py:201, 209, 219, 322, 332`
- **Severity**: High
- **Relevant Code**:
  ```python
  201|     @app.post("/traps/{trap_id}/new-card")
  ...
  209|     @app.post("/traps/{trap_id}/request-photo")
  ...
  219|     @app.post("/tracks/{track_id}/review")
  ...
  322|     @app.post("/manage/traps", response_class=HTMLResponse)
  ...
  332|     @app.post("/manage/traps/{trap_id}/{action}", response_class=HTMLResponse)
  ```
- **Concrete Failure Scenario**: The dashboard uses HTTP Basic Authentication. Browsers automatically attach Basic auth credentials to cross-origin requests. An attacker hosting a malicious site can embed an auto-submitting form targeting `POST /manage/traps/T1/remove` or `POST /manage/traps/T1/new-key`. If an authenticated dashboard user visits the page, the trap is retired or its API key is silently changed, severing communication with the trap in the field.
- **Suggested Fix**: Introduce CSRF tokens for all HTML form POST actions, or set `SameSite=Strict` cookie-based authentication.

---

#### 3. Trailing slash bypass in `dashboard_password` middleware blocks trap uploads
- **File**: `server/sentinel_server/app.py:83-88`
- **Severity**: Medium
- **Relevant Code**:
  ```python
  83|     no_password = {"/api/v1/captures", "/api/v1/hub/nodes", "/healthz"}
  84| 
  85|     @app.middleware("http")
  86|     async def dashboard_password(request: Request, call_next):
  87|         expected = get_settings().dashboard_password
  88|         if expected and request.url.path not in no_password:
  ```
- **Concrete Failure Scenario**: If a client POSTs to `/api/v1/captures/` (with a trailing slash), `request.url.path` is `"/api/v1/captures/"`. Because `"/api/v1/captures/" not in no_password`, the middleware requires Basic auth before Starlette routing can redirect, returning 401 to the trap and dropping its uploads. Furthermore, public data endpoints like `/api/v1/traps` and `/api/v1/traps/{trap_id}/counts` are left unauthenticated when `dashboard_password` is unset.
- **Suggested Fix**: Normalize paths with `request.url.path.rstrip("/")` in the middleware.

---

#### 4. Unrestricted hub endpoint allows any camera trap to query node hashes
- **File**: `server/sentinel_server/app.py:170-174`
- **Severity**: Low
- **Relevant Code**:
  ```python
  170|     @app.get("/api/v1/hub/nodes")
  171|     def api_hub_nodes(trap: Trap = Depends(device_trap), db: Session = Depends(get_session)):
  172|         """The ESP32 traps this hub takes photos from, with their key hashes so the hub can check them,
  173|         and which of them have a photo asked for on the dashboard."""
  174|         return {"nodes": services.hub_nodes(db, trap.id), "photo_requests": services.photo_requests(db, trap.id)}
  ```
- **Concrete Failure Scenario**: `device_trap` only validates that the key belongs to a valid trap, but `api_hub_nodes` does not verify that `trap.kind in services.HUB_KINDS`. Non-hub traps can query hub credential endpoints.
- **Suggested Fix**: Verify `if trap.kind not in services.HUB_KINDS: raise HTTPException(403, "only hubs may query node hashes")`.

---

### Category 3: Deprecated APIs & Outdated Patterns

#### 1. Path text reads/writes lack explicit UTF-8 encoding
- **File**: `device/sentinel_device/uploader.py:40, 59`
- **Severity**: Low
- **Relevant Code**:
  ```python
  40|         (self.queue_dir / f"{stem}.json").write_text(json.dumps(meta, indent=2))
  ...
  59|     meta = image.with_suffix(".json").read_text()
  ```
- **Concrete Failure Scenario**: `Path.read_text()` and `write_text()` default to the system locale. In minimal environments (systemd units or containers running with `LANG=C`), reading metadata with non-ASCII characters (e.g. `°C` in sensor notes or non-English trap names) raises `UnicodeDecodeError`.
- **Suggested Fix**: Pass `encoding="utf-8"` explicitly to `read_text()` and `write_text()`.

---

### Category 4: Inconsistencies

#### 1. Inconsistent HTTP status codes between hub and server for invalid images
- **File**: `server/sentinel_server/app.py:141-142` vs `device/tests/test_gateway.py:67`
- **Severity**: Low
- **Relevant Code**:
  `app.py`:
  ```python
  141|         except Exception:
  142|             raise HTTPException(422, "image is not a readable picture")
  ```
  `test_gateway.py`:
  ```python
  67|     assert gw.capture("Bearer key2", _meta(), JPEG[:50])[0] == 415  # cut off mid-transfer
  ```
- **Concrete Failure Scenario**: The hub gateway returns 415 ("Unsupported Media Type") on truncated/unreadable images, while the server returns 422 ("Unprocessable Entity"). While `uploader.py` includes both in `PARK_STATUSES`, the error contract is inconsistent across tiers.
- **Suggested Fix**: Standardize on 422 across both the gateway and server endpoints.

---

#### 2. Non-PRG pattern on `action == "new-key"` triggers accidental key regeneration on refresh
- **File**: `server/sentinel_server/app.py:341-347`
- **Severity**: Low
- **Relevant Code**:
  ```python
  341|         elif action == "new-key":
  342|             key = services.new_api_key()
  343|             trap.api_key_hash = services.hash_key(key)
  344|             return manage_page(request, db, new_key={"trap": trap, "key": key, "why": "new key"})
  ...
  347|         return RedirectResponse("/manage", status_code=303)
  ```
- **Concrete Failure Scenario**: Unlike `"remove"` and `"restore"` which redirect via 303, `"new-key"` renders HTML directly in response to the POST request. If the user refreshes the page, the browser re-submits the POST, regenerating the key again and invalidating the key just displayed.
- **Suggested Fix**: Follow the Post/Redirect/Get pattern or use session flash data to display the one-time key.

---

### Category 5: Dead Code & Organization

#### 1. Empty `api.py` module
- **File**: `server/sentinel_server/api.py:1`
- **Severity**: Low
- **Relevant Code**:
  ```python
  ===== FILE: server/sentinel_server/api.py =====
  (empty)
  ```
- **Concrete Failure Scenario**: Unused placeholder module. All routes are located in `app.py`.
- **Suggested Fix**: Extract the REST API routes (`/api/v1/...`) from `app.py` into `api.py` using a FastAPI `APIRouter`, or remove the empty file.

---

### Category 6: Performance & Optimization Opportunities

#### 1. Synchronous I/O in `async def upload_capture` blocks the asyncio event loop
- **File**: `server/sentinel_server/app.py:112, 139-140, 156, 167`
- **Severity**: High
- **Relevant Code**:
  ```python
  112|     async def upload_capture(
  ...
  139|             with Image.open(io.BytesIO(data)) as im:
  140|                 im.verify()
  ...
  156|         dest.write_bytes(data)
  ...
  167|         db.flush()
  ```
- **Concrete Failure Scenario**: Because `upload_capture` is defined as `async def`, FastAPI executes it directly on the main event loop thread. Synchronous calls like PIL image verification, writing file bytes to disk, and synchronous SQLAlchemy queries block the event loop for tens of milliseconds per capture. Concurrent uploads freeze the event loop, causing latency spikes for all other dashboard requests and health checks.
- **Suggested Fix**: Change the handler definition from `async def upload_capture(...)` to `def upload_capture(...)`. FastAPI automatically offloads synchronous `def` routes to its worker thread pool (`anyio.to_thread.run_sync`).

---

#### 2. On-the-fly full-resolution image decompression on `/crops/{detection_id}.jpg`
- **File**: `server/sentinel_server/app.py:244-249`
- **Severity**: Medium
- **Relevant Code**:
  ```python
  244|         with Image.open(settings.media_dir / d.capture.image_path) as img:
  245|             c = crop(img, d, pad=0.6).convert("RGB")
  246|             c.thumbnail((320, 320))
  247|             buf = io.BytesIO()
  248|             c.save(buf, "JPEG", quality=90)
  ```
- **Concrete Failure Scenario**: When an operator opens `/review`, the browser requests up to 60 crop images simultaneously. For each request, the server reads and decompresses the full 12MP original JPEG into raw memory. Decompressing 60 full-resolution images concurrently consumes over 2 GB of RAM and spikes CPU to 100%, risking an Out Of Memory crash on small server instances.
- **Suggested Fix**: Crop and save 320x320 thumbnails to a cache folder during the worker inference pipeline, and have `crop_image` serve the pre-generated file directly via `FileResponse`.

---

#### 3. N+1 query cascades on dashboard pages (`/`, `/review`, `/manage`)
- **File**: `server/sentinel_server/app.py:257-262, 313, 360-362`
- **Severity**: Medium
- **Relevant Code**:
  ```python
  257|         for t in traps:
  258|             rows.append({
  259|                 "trap": t, "health": services.trap_health(db, t), "week": services.week_counts(db, t.id),
  ...
  360|         for t in services.pending_reviews(db)[:60]:
  361|             det = db.scalar(select(Detection).where(Detection.track_id == t.id).order_by(Detection.det_conf.desc()))
  ```
- **Concrete Failure Scenario**: Rendering the overview page issues 5+ queries per trap sequentially. Rendering the review page issues 60 individual `Detection` queries. As the orchard grows, page generation time degrades linearly.
- **Suggested Fix**: Batch-load detection records using `IN (...)` or SQLAlchemy `selectinload`/`joinedload`, and aggregate counts with `GROUP BY` queries.

---

### Category 7: Test Coverage Gaps

#### 1. Missing test skip guard for board image in `test_camera_bench.py`
- **File**: `device/tests/test_camera_bench.py:10, 14`
- **Severity**: Low
- **Relevant Code**:
  ```python
  10| BOARD = Path(__file__).resolve().parents[2] / "hardware" / "print" / "checkerboard.png"  # 300 dpi
  ...
  14|     board = cv2.resize(cv2.imread(str(BOARD), 0), None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
  ```
- **Concrete Failure Scenario**: If tests run in an isolated environment where the `hardware/` assets are omitted, `cv2.imread()` returns `None` and `cv2.resize()` crashes with an obscure OpenCV C++ assertion failure instead of skipping gracefully.
- **Suggested Fix**: Add `if not BOARD.exists(): pytest.skip("checkerboard.png hardware asset missing")`.

---

## 3. Prioritized Next Steps

1. **Fix Server Startup & Event Loop Starvation (`server/sentinel_server/app.py`)**:
   - Add `settings.media_dir.mkdir(parents=True, exist_ok=True)` before `app.mount("/media", ...)`.
   - Change `async def upload_capture(...)` to `def upload_capture(...)` so image decoding and disk writes do not block the asyncio event loop.
2. **Correct Date/Timezone Handling & Liner Resolution (`server/sentinel_server/app.py`)**:
   - Normalize naive `captured_at` timestamps to UTC before liner comparisons.
   - Guard against `None` return values from `services.card_at()` to prevent infinite upload retry loops.
3. **Resolve Authentication & Security Vulnerabilities (`server/sentinel_server/app.py`)**:
   - Update Bearer token parsing to be case-insensitive (`scheme.lower() == "bearer"`).
   - Implement CSRF protection for dashboard state modifications.
   - Normalize URLs in `dashboard_password` middleware to handle trailing slashes cleanly.
4. **Fix Edge-Case Crashes in Tools & Services (`focus_sweep.py`, `camfeed.py`, `sentinel-cycle.service`)**:
   - Guard against `ZeroDivisionError` on 0 diopter focus positions in `focus_sweep.py`.
   - Add thread shutdown coordination and camera reconnect exception handling in `camfeed.py`.
   - Add `FailureAction=poweroff` to `sentinel-cycle.service` to protect field batteries against systemd execution timeouts.
