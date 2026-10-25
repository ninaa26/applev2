# Code Review: `server/` (Chunk 1 of 5)

**Files in scope for this chunk:**
- `CLAUDE.md`
- `README.md`
- `server/.env.example`
- `server/launchd/org.orchardsentinel.server.plist`
- `server/pyproject.toml`
- `server/sentinel_server/__init__.py`
- `server/sentinel_server/app.py`
- `server/sentinel_server/cli.py`
- `server/sentinel_server/db.py`

---

## 1. Bugs

### 1.1 Worker thread is abruptly terminated on server shutdown without joining
- **File & Line:** `server/sentinel_server/app.py:67-73`
- **Severity:** High
- **Code:**
  ```python
  67|         if start_worker:
  68|             from .pipeline.worker import run_forever
  69| 
  70|             thread = threading.Thread(target=run_forever, args=(stop,), daemon=True, name="worker")
  71|             thread.start()
  72|         yield
  73|         stop.set()
  ```
- **Concrete Failure Scenario:**
  The server starts the background pipeline worker as a daemon thread. When the FastAPI application shuts down (e.g., during deployment, restart, or `SIGTERM`/`SIGINT`), the lifespan exits after calling `stop.set()`, but it never invokes `thread.join(timeout=...)`. Because the thread is marked `daemon=True`, Python immediately terminates the thread mid-execution. If the worker is halfway through processing a photo, updating database records, or writing bounding boxes, the database transaction or image file is aborted abruptly, leaving captures in `status="processing"` indefinitely and risking SQLite journal corruption.
- **Suggested Fix:**
  Wait for the worker thread to finish its current iteration gracefully before exiting:
  ```python
  yield
  stop.set()
  if thread is not None:
      thread.join(timeout=10.0)
  ```

---

### 1.2 `_add_missing_columns` silently skips non-nullable columns lacking server defaults
- **File & Line:** `server/sentinel_server/db.py:66-70`
- **Severity:** High
- **Code:**
  ```python
  66|                 ddl = col.type.compile(eng.dialect)
  67|                 if col.server_default is not None:
  68|                     conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl} '
  69|                                       f"NOT NULL DEFAULT '{col.server_default.arg}'"))
  70|                 elif col.nullable:
  71|                     conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl}"))
  ```
- **Concrete Failure Scenario:**
  If a new column is added to any model in `models.py` that is `nullable=False` and lacks a `server_default` (or relies on a Python-side default like `default=...`), `_add_missing_columns` silently ignores it because it matches neither condition (`server_default is not None` nor `col.nullable`). The table schema is never updated. At runtime, standard queries (`SELECT` or `INSERT`) referencing the model fail with `sqlite3.OperationalError: no such column: <table>.<column>`.
- **Suggested Fix:**
  Either require migration scripts or explicitly log an error / raise an exception when a non-nullable column lacks a database-level `server_default`:
  ```python
  if col.server_default is not None:
      default_val = col.server_default.arg if hasattr(col.server_default, "arg") else str(col.server_default)
      conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl} NOT NULL DEFAULT '{default_val}'"))
  elif col.nullable:
      conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl}"))
  else:
      raise RuntimeError(f"Cannot auto-migrate non-nullable column '{table.name}.{col.name}' without server_default")
  ```

---

### 1.3 Timezone mismatch and `TypeError` on naive/aware datetime operations
- **File & Line:** `server/sentinel_server/app.py:45`, `server/sentinel_server/app.py:148`, `server/sentinel_server/app.py:165`
- **Severity:** High
- **Code:**
  ```python
  45|     s = (utcnow() - dt).total_seconds()
  ...
  148|         if current is None or (m.get("new_card") and current.installed_at < captured):
  ...
  165|         if trap.photo_requested_at is not None and captured >= trap.photo_requested_at:
  ```
- **Concrete Failure Scenario:**
  At line 125, `captured` is stripped of timezone info (`captured.astimezone(timezone.utc).replace(tzinfo=None) if captured.tzinfo else captured`). However, if `trap.photo_requested_at` or `current.installed_at` is stored or populated with a timezone-aware datetime (or when running against PostgreSQL with timezone-aware datetimes via psycopg), comparing `captured >= trap.photo_requested_at` or `current.installed_at < captured` immediately raises `TypeError: can't compare offset-naive and offset-aware datetimes`. Likewise, in `_ago(dt)`, if `dt` is timezone-aware and `utcnow()` is naive (or vice versa), `utcnow() - dt` crashes with `TypeError: can't subtract offset-naive and offset-aware datetimes`, rendering pages like `/` or `/traps/{id}` inaccessible (HTTP 500).
- **Suggested Fix:**
  Normalize all timestamps to timezone-aware UTC or strip tzinfo uniformly before comparison:
  ```python
  def _ensure_naive_utc(dt: datetime | None) -> datetime | None:
      if dt is None:
          return None
      return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
  ```

---

### 1.4 `_local` template filter corrupts time by overriding tzinfo instead of converting
- **File & Line:** `server/sentinel_server/app.py:36-39`
- **Severity:** Medium
- **Code:**
  ```python
  36| def _local(dt: datetime | None, fmt: str = "%b %d %H:%M") -> str:
  37|     if dt is None:
  38|         return "—"
  39|     return dt.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(get_settings().timezone)).strftime(fmt)
  ```
- **Concrete Failure Scenario:**
  `dt.replace(tzinfo=timezone.utc)` unconditionally replaces the timezone object on `dt`. If `dt` is already timezone-aware (e.g., loaded from PostgreSQL or constructed with local offset), `.replace(tzinfo=timezone.utc)` changes its timezone tag without adjusting its clock time. For instance, `10:00-04:00` becomes `10:00+00:00`. When subsequently converted to `ZoneInfo(get_settings().timezone)` (e.g. `America/New_York`, -4), it displays `06:00` instead of `10:00`—an error of 4 hours.
- **Suggested Fix:**
  Check whether `dt.tzinfo` is present before replacing:
  ```python
  def _local(dt: datetime | None, fmt: str = "%b %d %H:%M") -> str:
      if dt is None:
          return "—"
      if dt.tzinfo is None:
          dt = dt.replace(tzinfo=timezone.utc)
      return dt.astimezone(ZoneInfo(get_settings().timezone)).strftime(fmt)
  ```

---

### 1.5 Unhandled `AttributeError` when `services.card_at` returns `None`
- **File & Line:** `server/sentinel_server/app.py:151-160`
- **Severity:** Medium
- **Code:**
  ```python
  151|             card = services.card_at(db, trap.id, captured)
  ...
  160|             trap_id=trap.id, card_id=card.id, uid=uid, captured_at=captured, image_path=str(rel),
  ```
- **Concrete Failure Scenario:**
  If an out-of-order or queued photo arrives with a `captured_at` timestamp earlier than the installation date of any registered card for that trap, `services.card_at(db, trap.id, captured)` returns `None`. Line 160 immediately accesses `card.id`, triggering `AttributeError: 'NoneType' object has no attribute 'id'` and failing the upload with an unhandled HTTP 500 error instead of linking to an existing card or initiating an initial card.
- **Suggested Fix:**
  Handle the fallback when `card` is `None`:
  ```python
  card = services.card_at(db, trap.id, captured)
  if card is None:
      card = services.open_card(db, trap.id) or services.start_new_card(db, trap.id, at=captured, note="retroactive first photo")
  ```

---

### 1.6 Race condition in `db.py:engine()` during multi-threaded initialization
- **File & Line:** `server/sentinel_server/db.py:20-33`
- **Severity:** Medium
- **Code:**
  ```python
  20| def engine():
  21|     global _engine, _SessionLocal
  22|     if _engine is None:
  23|         url = get_settings().database_url
  ...
  32|         _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
  33|     return _engine
  ```
- **Concrete Failure Scenario:**
  There is no mutex lock protecting `engine()`. If `create_app(start_worker=True)` starts the worker thread and simultaneous HTTP requests arrive before `_engine` is created, both threads enter `if _engine is None:` concurrently. Two separate database engine instances and connection pools are created, and `_sqlite_pragmas` event listeners are bound multiple times, creating orphaned connection pools and unpredictable session bindings.
- **Suggested Fix:**
  Use a module-level `threading.Lock()`:
  ```python
  _lock = threading.Lock()

  def engine():
      global _engine, _SessionLocal
      if _engine is None:
          with _lock:
              if _engine is None:
                  ...
  ```

---

### 1.7 `cmd_detect` crashes with unhandled exception on missing or corrupted image files
- **File & Line:** `server/sentinel_server/cli.py:139-146`
- **Severity:** Medium
- **Code:**
  ```python
  139|         boxes = det.detect(path)
  140|         img = cv2.imread(str(path))
  141|         info = getattr(det, "last", {})
  142|         if info.get("card") is not None:
  143|             cv2.polylines(img, [info["card"].astype("int32")], True, (0, 255, 0), 2)
  144|         for b in boxes:
  145|             cv2.rectangle(img, (int(b.x1), int(b.y1)), (int(b.x2), int(b.y2)), (255, 255, 0), 2)
  ```
- **Concrete Failure Scenario:**
  If any image path provided to `sentinel-server detect <images...>` cannot be decoded by OpenCV (e.g. invalid format, permission error, or file deleted), `cv2.imread()` returns `None`. It does not raise an exception. Lines 143 and 145 then pass `img` (`None`) into `cv2.polylines()` or `cv2.rectangle()`, resulting in a fatal OpenCV C++ exception: `cv2.error: OpenCV(4.x) ... :-1: error: (-5:Bad argument) in function 'rectangle'`.
- **Suggested Fix:**
  Validate `img is not None` before drawing:
  ```python
  img = cv2.imread(str(path))
  if img is None:
      print(f"Error: failed to load image {path}", file=sys.stderr)
      continue
  ```

---

### 1.8 `cmd_import_weather` crashes on common non-ISO date formats or missing sensor data
- **File & Line:** `server/sentinel_server/cli.py:182-183`
- **Severity:** Medium
- **Code:**
  ```python
  182|             day = date.fromisoformat(row["date"].strip()[:10])
  183|             tmax, tmin = float(row["tmax_f"]), float(row["tmin_f"])
  ```
- **Concrete Failure Scenario:**
  NEWA weather data exports commonly contain empty strings, `"M"` (missing), or dates formatted as `MM/DD/YYYY`. `date.fromisoformat` only supports `YYYY-MM-DD`. Any invalid date string or missing sensor reading (`float("")`) raises `ValueError`. Because all processing is enclosed in a single `session_scope()`, a single malformed row aborts the entire command and rolls back all previously imported days.
- **Suggested Fix:**
  Add date format handling and skip invalid/missing temperature readings with a warning:
  ```python
  try:
      date_str = row["date"].strip()[:10]
      try:
          day = date.fromisoformat(date_str)
      except ValueError:
          day = datetime.strptime(date_str, "%m/%d/%Y").date()
      tmax, tmin = float(row["tmax_f"]), float(row["tmin_f"])
  except (ValueError, KeyError) as e:
      logging.warning("Skipping invalid weather row %s: %s", row, e)
      continue
  ```

---

### 1.9 `cmd_rotate_key` and `cmd_set_mask` omit database initialization
- **File & Line:** `server/sentinel_server/cli.py:73-82`, `server/sentinel_server/cli.py:161-174`
- **Severity:** Low
- **Code:**
  ```python
  73| def cmd_rotate_key(args) -> int:
  74|     key = new_api_key()
  75|     with session_scope() as db:
  ...
  161| def cmd_set_mask(args) -> int:
  162|     """Areas the detector ignores (the lure), as fractions of the photo: x1 y1 x2 y2."""
  163|     with session_scope() as db:
  ```
- **Concrete Failure Scenario:**
  Unlike `cmd_init`, `cmd_add_trap`, `cmd_set_kind`, `cmd_list`, `cmd_serve`, `cmd_worker`, `cmd_reprocess`, `cmd_import_weather`, and `cmd_evaluate`, neither `cmd_rotate_key` nor `cmd_set_mask` calls `init_db()`. If either command is run against a fresh database or an upgraded database requiring schema additions, it fails with table or column not found errors.
- **Suggested Fix:**
  Call `init_db()` at the beginning of `cmd_rotate_key` and `cmd_set_mask`.

---

### 1.10 Rejecting an insect does not clear stale `reviewed_label`
- **File & Line:** `server/sentinel_server/app.py:225-226`
- **Severity:** Low
- **Code:**
  ```python
  225|         if label == "reject":
  226|             t.review_status = "rejected"
  227|         elif label in SPECIES:
  228|             t.reviewed_label = label
  229|             t.review_status = "confirmed"
  ```
- **Concrete Failure Scenario:**
  If an insect track was previously confirmed as a species (e.g. `reviewed_label = "CM"`) and a reviewer later rejects it, `t.review_status` is updated to `"rejected"`, but `t.reviewed_label` remains `"CM"`. Any query or export aggregating catches that filters by `reviewed_label` without checking `review_status != 'rejected'` will count the rejected insect.
- **Suggested Fix:**
  Explicitly clear `reviewed_label` upon rejection:
  ```python
  if label == "reject":
      t.review_status = "rejected"
      t.reviewed_label = None
  ```

---

## 2. Security Issues

### 2.1 Unbounded image upload allows Denial of Service (DoS) via memory exhaustion
- **File & Line:** `server/sentinel_server/app.py:113`, `server/sentinel_server/app.py:137`
- **Severity:** High
- **Code:**
  ```python
  113|         image: UploadFile = File(...),
  ...
  137|         data = await image.read()
  ```
- **Concrete Failure Scenario:**
  `upload_capture` reads the entire uploaded file into memory in a single call (`await image.read()`) with no size constraint. A malicious trap client or attacker on the local network sending a multi-gigabyte payload will force the Python process to allocate massive buffers, causing an Out-Of-Memory (OOM) crash that terminates the server on resource-constrained hardware like the Raspberry Pi 5.
- **Suggested Fix:**
  Enforce a maximum upload size limit (e.g., 20 MB) while reading in chunks:
  ```python
  MAX_UPLOAD_BYTES = 20 * 1024 * 1024
  data = bytearray()
  while chunk := await image.read(1024 * 1024):
      data.extend(chunk)
      if len(data) > MAX_UPLOAD_BYTES:
          raise HTTPException(413, "Uploaded image exceeds size limit (20MB)")
  ```

---

### 2.2 Direct string interpolation in DDL (`_add_missing_columns`)
- **File & Line:** `server/sentinel_server/db.py:67-69`
- **Severity:** High
- **Code:**
  ```python
  67|                 if col.server_default is not None:
  68|                     conn.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl} '
  69|                                       f"NOT NULL DEFAULT '{col.server_default.arg}'"))
  ```
- **Concrete Failure Scenario:**
  `col.server_default.arg` is interpolated directly into raw SQL text enclosed in single quotes. If a model defines a server default that contains quotes or is an expression (e.g., `text("0")` or `text("'val'")`), `col.server_default.arg` produces SQL syntax errors. Furthermore, interpolating raw metadata strings directly into DDL is a security hazard if table or column names are ever dynamically constructed.
- **Suggested Fix:**
  Sanitize or properly compile default clauses through SQLAlchemy's dialect compiler rather than manual f-string formatting.

---

### 2.3 State-changing dashboard POST endpoints lack CSRF protection
- **File & Line:** `server/sentinel_server/app.py:201-236`, `server/sentinel_server/app.py:322-348`
- **Severity:** High
- **Code:**
  ```python
  201|     @app.post("/traps/{trap_id}/new-card")
  ...
  208|     @app.post("/traps/{trap_id}/request-photo")
  ...
  219|     @app.post("/tracks/{track_id}/review")
  ...
  322|     @app.post("/manage/traps", response_class=HTMLResponse)
  ...
  332|     @app.post("/manage/traps/{trap_id}/{action}", response_class=HTMLResponse)
  ```
- **Concrete Failure Scenario:**
  All dashboard modification actions rely on standard browser form POSTs without CSRF tokens. If a logged-in user visits a malicious website (or an attacker sends a crafted link on the orchard network), an attacker-controlled page can silently submit forms to `http://localhost:8000/manage/traps/T1/new-key` or `/remove`, resetting API keys (which permanently locks ESP32 traps out of uploading) or retiring traps.
- **Suggested Fix:**
  Implement CSRF tokens for all state-changing HTML form submissions (e.g., using `starlette-csrf` or setting `SameSite=Strict` cookies if cookie session authentication is introduced).

---

### 2.4 Unvalidated `trap_id` parameter presents path traversal risk
- **File & Line:** `server/sentinel_server/app.py:153-156`
- **Severity:** Medium
- **Code:**
  ```python
  153|         rel = Path(trap.id) / captured.strftime("%Y/%m/%d") / f"{uid}.jpg"
  154|         dest = settings.media_dir / rel
  155|         dest.parent.mkdir(parents=True, exist_ok=True)
  156|         dest.write_bytes(data)
  ```
- **Concrete Failure Scenario:**
  While `uid` is checked against `SAFE_UID` (`[A-Za-z0-9][A-Za-z0-9_-]{0,79}`), `trap_id` is never validated with a regex when created in `cmd_add_trap` or `manage_add`. If an administrator registers a trap ID containing path traversal characters like `../../etc`, `dest` resolves outside `settings.media_dir`, causing arbitrary file writes when photos are uploaded.
- **Suggested Fix:**
  Enforce the same safe identifier regex on `trap_id` upon creation:
  ```python
  if not SAFE_UID.fullmatch(trap_id):
      raise ValueError(f"Invalid trap_id {trap_id!r}: use letters, digits, _ and -")
  ```

---

### 2.5 Insecure default network binding without mandatory authentication
- **File & Line:** `server/sentinel_server/cli.py:100-105`, `server/sentinel_server/cli.py:238`
- **Severity:** Medium
- **Code:**
  ```python
  100|     app = create_app(start_worker=not args.no_worker)
  101|     print(f"Dashboard: http://{'localhost' if args.host in ('0.0.0.0', '127.0.0.1') else args.host}:{args.port}")
  102|     if not get_settings().dashboard_password and args.host not in ("127.0.0.1", "localhost", "::1"):
  103|         print("No dashboard password: anyone who can reach this machine on its network...")
  ...
  238|     p.add_argument("--host", default="0.0.0.0")
  ```
- **Concrete Failure Scenario:**
  By default, `sentinel-server serve` binds to `0.0.0.0:8000` with no password configured. Anyone on the same Wi-Fi network, local subnet, or Tailscale network can view all orchard imagery, retire active traps, and rotate credentials without authentication.
- **Suggested Fix:**
  Default `--host` to `127.0.0.1` unless explicitly requested, or refuse to bind to `0.0.0.0` without `SENTINEL_DASHBOARD_PASSWORD` set unless a `--dev-insecure` flag is provided.

---

## 3. Deprecated APIs / Outdated Patterns

### 3.1 Deprecated `datetime.utcnow()` pattern
- **File & Line:** `server/sentinel_server/app.py:27`, `server/sentinel_server/app.py:45`
- **Severity:** Medium
- **Code:**
  ```python
  27| from .models import PESTS, SPECIES, SPECIES_LABELS, Capture, Detection, Event, Review, Track, Trap, utcnow
  ...
  45|     s = (utcnow() - dt).total_seconds()
  ```
- **Concrete Failure Scenario:**
  In Python 3.12+, `datetime.utcnow()` emits a `DeprecationWarning` and is slated for removal in future Python versions. The project specifies `requires-python = ">=3.11"`.
- **Suggested Fix:**
  Use timezone-aware `datetime.now(timezone.utc)`.

---

### 3.2 Mixing synchronous database calls and file I/O inside `async def` route
- **File & Line:** `server/sentinel_server/app.py:112-168`
- **Severity:** Medium
- **Code:**
  ```python
  112|     async def upload_capture(
  ...
  130|         existing = db.scalar(select(Capture).where(Capture.trap_id == trap.id, Capture.uid == uid))
  ...
  156|         dest.write_bytes(data)
  ...
  167|         db.flush()
  ```
- **Concrete Failure Scenario:**
  In FastAPI, declaring an endpoint as `async def` runs the entire function directly on the asyncio event loop. Calling synchronous SQLAlchemy queries (`db.scalar`, `db.flush`) and synchronous filesystem writes (`dest.write_bytes(data)`) freezes the single-threaded event loop for the duration of the disk write and database lock. Concurrent requests (such as `/healthz` or dashboard page loads) are completely blocked until the file is written.
- **Suggested Fix:**
  Offload the blocking file write and DB operations to a threadpool via `anyio.to_thread.run_sync` or Starlette's `run_in_threadpool`.

---

## 4. Inconsistencies

### 4.1 Hub trap initialized with pheromone lure `"CM"`
- **File & Line:** `server/sentinel_server/cli.py:47`, `server/sentinel_server/app.py:324`
- **Severity:** Low
- **Code:**
  ```python
  # cli.py
  47|             key = create_trap(db, args.trap_id, args.name, args.block, args.lure or "CM", args.kind, args.hub)
  ...
  # app.py
  324|                    lure: str = Form(default="CM"), kind: str = Form(default="esp32"), hub_id: str = Form(default=""),
  ```
- **Concrete Failure Scenario:**
  `README.md` and `CLAUDE.md` state that hubs have no cameras and no lures. `cmd_list` even masks the lure for hubs (`'-' if t.kind == 'hub' else t.lure:5`). However, `cmd_add_trap` and `manage_add` fall back to `"CM"` when registering a hub, storing a bogus codling moth lure in the database.
- **Suggested Fix:**
  Set `lure = None` whenever `kind == "hub"`.

---

### 4.2 Non-POSIX path separators on Windows in `image_path`
- **File & Line:** `server/sentinel_server/app.py:153-160`
- **Severity:** Low
- **Code:**
  ```python
  153|         rel = Path(trap.id) / captured.strftime("%Y/%m/%d") / f"{uid}.jpg"
  ...
  160|             trap_id=trap.id, card_id=card.id, uid=uid, captured_at=captured, image_path=str(rel),
  ```
- **Concrete Failure Scenario:**
  On Windows systems, `str(rel)` produces backslashes (e.g. `T1\2026\10\23\uid.jpg`). When mounted under `/media` and referenced in HTML templates (`/media/{{ cap.image_path }}`), image URLs break or fail static file lookups.
- **Suggested Fix:**
  Store normalized POSIX paths:
  ```python
  image_path = rel.as_posix()
  ```

---

## 5. Dead Code, Duplication & Code Organization

### 5.1 Package data wildcard does not include subdirectories
- **File & Line:** `server/pyproject.toml:36`
- **Severity:** Medium
- **Code:**
  ```toml
  36| sentinel_server = ["templates/*.html", "static/*"]
  ```
- **Concrete Failure Scenario:**
  In setuptools, `static/*` matches only immediate child files inside `sentinel_server/static/`. If CSS, JS, or images are placed in nested subfolders (e.g. `static/css/*.css` or `static/js/*.js`), they are omitted when building a wheel or installing via pip, causing 404s for static assets in production deployments.
- **Suggested Fix:**
  Use recursive globbing:
  ```toml
  sentinel_server = ["templates/*.html", "static/**/*", "static/*"]
  ```

---

### 5.2 Hardcoded developer paths in launchd plist
- **File & Line:** `server/launchd/org.orchardsentinel.server.plist:13, 17, 25, 27`
- **Severity:** Low
- **Code:**
  ```xml
  13|         <string>/Users/ninaiscool/Developer/Active/applev2/server/.venv/bin/sentinel-server</string>
  ...
  17|     <string>/Users/ninaiscool/Developer/Active/applev2/server</string>
  ...
  25|     <string>/Users/ninaiscool/Developer/Active/applev2/server/data/server.log</string>
  ```
- **Concrete Failure Scenario:**
  The launchd configuration is hardcoded to a specific developer's personal macOS path. Any other team member or server attempting to use this plist will fail to start the service.
- **Suggested Fix:**
  Provide an install script or template placeholder (e.g. `__SERVER_DIR__`) that populates the active environment path upon installation.

---

### 5.3 Launchd stdout and stderr point to the same uncoordinated file
- **File & Line:** `server/launchd/org.orchardsentinel.server.plist:25-27`
- **Severity:** Low
- **Code:**
  ```xml
  25|     <key>StandardOutPath</key>
  26|     <string>/Users/ninaiscool/Developer/Active/applev2/server/data/server.log</string>
  27|     <key>StandardErrorPath</key>
  28|     <string>/Users/ninaiscool/Developer/Active/applev2/server/data/server.log</string>
  ```
- **Concrete Failure Scenario:**
  In launchd, opening the same file path for both `StandardOutPath` and `StandardErrorPath` results in two separate unbuffered file descriptors writing to the same file without synchronization. Concurrent writes to stdout and stderr lead to interleaved and corrupted log messages.
- **Suggested Fix:**
  Direct stderr to a separate log file (`server.err.log`) or use a unified logging wrapper.

---

## 6. Performance & Optimization Opportunities

### 6.1 Severe N+1 query cascades in dashboard templates
- **File & Line:** `server/sentinel_server/app.py:257-262`, `server/sentinel_server/app.py:285`, `server/sentinel_server/app.py:354`, `server/sentinel_server/app.py:360-362`
- **Severity:** Medium
- **Code:**
  ```python
  # overview (app.py:257-262)
  for t in traps:
      rows.append({
          "trap": t, "health": services.trap_health(db, t), "week": services.week_counts(db, t.id),
          "pending": len(services.pending_reviews(db, t.id)), "card": services.open_card(db, t.id),
          "pheno": services.phenology_status(db, t),
      })

  # trap_page & capture_page (app.py:285, 354)
  tracks = {d.track_id: db.get(Track, d.track_id) for d in latest.detections if d.track_id}

  # review_page (app.py:360-362)
  for t in services.pending_reviews(db)[:60]:
      det = db.scalar(select(Detection).where(Detection.track_id == t.id).order_by(Detection.det_conf.desc()))
  ```
- **Concrete Failure Scenario:**
  Rendering the overview page with 20 active traps runs over 100 separate SQL queries. Furthermore, `len(services.pending_reviews(db, t.id))` fetches full object records merely to take their count. On a Raspberry Pi 5 with SQLite or network latency to Postgres, this causes high page load latency.
- **Suggested Fix:**
  Use eager joins (`joinedload`, `selectinload`), a `COUNT()` aggregation query for pending reviews, and batch fetches for tracks and detections (`select(Track).where(Track.id.in_(...))`).

---

### 6.2 Full image re-decoding and resizing on every crop request
- **File & Line:** `server/sentinel_server/app.py:244-248`
- **Severity:** Medium
- **Code:**
  ```python
  244|         with Image.open(settings.media_dir / d.capture.image_path) as img:
  245|             c = crop(img, d, pad=0.6).convert("RGB")
  246|             c.thumbnail((320, 320))
  247|             buf = io.BytesIO()
  248|             c.save(buf, "JPEG", quality=90)
  ```
- **Concrete Failure Scenario:**
  The review page loads up to 60 insect crops at once. Each request to `/crops/{detection_id}.jpg` opens a full-resolution (3–12 megapixel) camera JPEG from disk, decompresses it into RAM, crops it, scales it down, and encodes it to JPEG. 60 concurrent requests on a Raspberry Pi CPU spike CPU usage to 100% and consume large amounts of memory.
- **Suggested Fix:**
  Cache cropped thumbnails on disk under `media_dir / "crops" / f"{detection_id}.jpg"`. If the file already exists, serve it directly without opening and re-processing the parent image.

---

### 6.3 Reprocessing a card holds SQLite write transaction for entire batch
- **File & Line:** `server/sentinel_server/cli.py:122-124`
- **Severity:** Medium
- **Code:**
  ```python
  122|     with session_scope() as db:
  123|         n = pipeline.reprocess_card(db, args.card)
  ```
- **Concrete Failure Scenario:**
  `sentinel-server reprocess --card <id>` wraps the entire reprocessing of all photos on a liner inside a single `with session_scope() as db:`. If a liner has dozens of photos, detection and inference take several minutes, holding an open SQLite write transaction the entire time. During this period, incoming camera uploads from the field will fail with database lock timeouts (`sqlite3.OperationalError: database is locked`).
- **Suggested Fix:**
  Manage transactions per-photo or batch within `pipeline.reprocess_card()` rather than enclosing the entire command in a single session scope.

---

## 7. Test Coverage Gaps

Based on the files provided in this chunk:
1. **No test for lifespan shutdown**: The lack of thread joining in `app.py:lifespan` indicates shutdown edge cases are not exercised in automated tests.
2. **Missing tests for `upload_capture` duplicate race conditions and large payload limits**: Concurrent uploads and payload limits are untested.
3. **No tests for `_add_missing_columns` failure paths**: Non-nullable columns without defaults and quoted default values in SQLite/Postgres have not been validated.
4. **Missing tests for CLI error paths**: `cmd_import_weather` with malformed CSVs, `cmd_detect` with non-existent or unreadable images, and `cmd_set_mask`/`cmd_rotate_key` without initial database tables are not covered.

---

## 8. Prioritized Next Steps

1. **Fix Lifespan Shutdown:** Update `app.py:lifespan` to join the background worker thread on exit to prevent data corruption.
2. **Add Upload Size Limits and Async Offloading:** Restrict maximum payload size in `upload_capture` and offload synchronous file writes to avoid freezing the event loop.
3. **Correct Datetime Comparisons and `_local` Filter:** Ensure all datetime calculations and comparisons are uniformly timezone-aware or naive before arithmetic, and prevent `_local` from clobbering existing timezones.
4. **Fix Schema Migration DDL Injection:** Address raw string interpolation and non-nullable handling in `db.py:_add_missing_columns`.
5. **Implement Thumbnail Caching:** Save generated detection crops to disk so repeated review views avoid re-decoding raw full-resolution photos.
6. **Add CSRF Protection:** Protect dashboard POST actions from cross-site request forgery.
