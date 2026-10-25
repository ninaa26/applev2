## Scope & Files Reviewed

This review covers **Chunk 3 of 3** of the Orchard Sentinel repository:
- `field-tests/esp32-window-day/report.py`
- `field-tests/esp32-window-day/start.sh`
- `hardware/CAMERAS.md`
- `hardware/README.md`
- `hardware/TRAP.md`
- `hardware/make_markers.py`
- `hardware/mockup_template.py`
- `hardware/scad/camera_mount.scad`
- `hardware/scad/liner_tray.scad`
- `device/esp32-node/platformio.ini`
- `device/install-hub.sh`
- `device/install.sh`
- `device/pyproject.toml`
- `server/pyproject.toml`

---

## 1. Bugs (Correctness, Crashes, Resource Leaks, Off-by-One)

### [CRITICAL] `field-tests/esp32-window-day/start.sh:40, 43, 44` — Script crashes on healthy Pi status under `set -e`
- **Severity**: Critical
- **Quoted Code**:
  ```bash
  40| grep -q "synchronized: no" "$RUN/health-start.txt" && { echo "!! a Pi's clock is not synchronised (timedatectl)"; warn=1; }
  ...
  42| for v in $(grep -o "throttled=0x[0-9a-f]*" "$RUN/health-start.txt" | cut -d= -f2); do
  43|   (( v & 0xf )) && { echo "!! a Pi is under-voltage or throttled right now ($v)"; warn=1; }
  44|   (( v & 0xf0000 )) && echo "note: a Pi was under-voltage or throttled earlier since boot ($v); the loggers record it"
  45| done
  ```
- **Concrete Failure Scenario**: `start.sh` sets `set -euo pipefail` on line 4. In Bash, an AND-list `cmd1 && cmd2` evaluated at the statement level yields the returncode of `cmd1` if `cmd1` is falsy (exit code != 0). When a Pi's clock is synchronized (the normal, healthy state), `grep -q "synchronized: no"` exits with status 1. Because it is not enclosed in an `if` statement or terminated with `|| true`, the entire list exits with status 1, causing Bash's `set -e` to abort the script immediately on line 40 before any setup occurs. Even if line 40 were bypassed, lines 43 and 44 evaluate `(( v & 0xf ))` and `(( v & 0xf0000 ))`; when the Pi is unthrottled (`v=0`), the arithmetic expression evaluates to 0, which returns exit code 1 in Bash and crashes the script.
- **Suggested Fix**: Replace one-line `&&` constructs with standard `if` statements:
  ```bash
  if grep -q "synchronized: no" "$RUN/health-start.txt"; then
    echo "!! a Pi's clock is not synchronised (timedatectl)"
    warn=1
  fi
  for v in $(grep -o "throttled=0x[0-9a-f]*" "$RUN/health-start.txt" | cut -d= -f2); do
    if (( (v & 0xf) != 0 )); then
      echo "!! a Pi is under-voltage or throttled right now ($v)"
      warn=1
    fi
    if (( (v & 0xf0000) != 0 )); then
      echo "note: a Pi was under-voltage or throttled earlier since boot ($v); the loggers record it"
    fi
  done
  ```

---

### [HIGH] `hardware/mockup_template.py:62, 67–71` — Main SVG cut line severs end flaps from floor
- **Severity**: High
- **Quoted Code**:
  ```python
  62|     f'<rect class="cut" x="{xs[0]}" y="{y0}" width="{xs[-1] - xs[0]}" height="{length}"/>',
  ...
  67|     if flap:
  68|         for fy, ly in ((y0 - flap, y0), (y1, y1)):
  69|             out.append(f'<rect class="cut" x="{xs[3]}" y="{fy}" width="{floor_w}" height="{flap}"/>')
  70|             out.append(f'<line class="fold" x1="{xs[3]}" y1="{ly}" x2="{xs[4]}" y2="{ly}"/>')
  71|             out.append(f'<text class="txt" x="{xs[3] + 4}" y="{fy + flap / 2 + 2}">end flap (folds up)</text>')
  ```
- **Concrete Failure Scenario**: Line 62 draws a single black perimeter cut line (`class="cut"`) spanning from `xs[0]` to `xs[-1]` along `y0` and `y1`. The end flaps (lines 68–71) are positioned above `y0` and below `y1` adjacent to the floor panel (`xs[3]` to `xs[4]`). Because line 62 cuts straight across `y0` from `xs[0]` to `xs[-1]`, any vinyl cutter, laser cutter, or person cutting along the black cut lines will cut straight through the junction between the floor and the end flaps, detaching both flaps completely.
- **Suggested Fix**: When `flap > 0`, do not draw a continuous rectangle across `y0` and `y1`. Instead, draw cut lines only along the outer edges and along `y0` and `y1` where flaps are *not* present (`xs[0]` to `xs[3]` and `xs[4]` to `xs[-1]`), leaving only fold lines (`class="fold"`) at the flap boundaries (`xs[3]` to `xs[4]`).

---

### [HIGH] `hardware/make_markers.py:44–50` — ArUco corner marker IDs are transposed on the printed sheet
- **Severity**: High
- **Quoted Code**:
  ```python
  22| TRAY_IDS = (0, 1, 2, 3)  # top-left, top-right, bottom-right, bottom-left
  ...
  44|     for i, mid in enumerate(TRAY_IDS):
  45|         m = cv2.aruco.generateImageMarker(d, mid, px)
  46|         r, c = divmod(i, 2)
  47|         y, x = r * cell + pad, c * cell + pad
  48|         sheet[y : y + px, x : x + px] = m
  49|         cv2.putText(sheet, f"id {mid}", (x, y + px + round(5 * MM)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, 0, 2)
  50|     for k, line in enumerate((f"ArUco 4x4_50, {size_mm:g} mm", "Glue to tray corners: 0 TL, 1 TR, 2 BR, 3 BL")):
  ```
- **Concrete Failure Scenario**: In `divmod(i, 2)`:
  - `i = 0 -> r = 0, c = 0` (Top-Left): `mid = 0`
  - `i = 1 -> r = 0, c = 1` (Top-Right): `mid = 1`
  - `i = 2 -> r = 1, c = 0` (Bottom-Left): `mid = 2`
  - `i = 3 -> r = 1, c = 1` (Bottom-Right): `mid = 3`
  The layout arranges Marker 2 at Bottom-Left and Marker 3 at Bottom-Right. However, line 22, line 50, and `hardware/README.md` line 24 explicitly specify `0 TL, 1 TR, 2 BR, 3 BL` (Marker 2 at Bottom-Right, Marker 3 at Bottom-Left). A user cutting out markers will either follow the visual grid position and swap bottom-left with bottom-right, or follow the text and invert OpenCV's perspective transform during tray alignment.
- **Suggested Fix**: Explicitly map `i` to clockwise coordinates:
  ```python
  GRID_POS = [(0, 0), (0, 1), (1, 1), (1, 0)]  # TL, TR, BR, BL
  for i, mid in enumerate(TRAY_IDS):
      r, c = GRID_POS[i]
      ...
  ```

---

### [MEDIUM] `field-tests/esp32-window-day/report.py:124, 126, 173` — Unhandled `None` in `c["meta"]` causes `AttributeError`
- **Severity**: Medium
- **Quoted Code**:
  ```python
  124|         hub = (c["meta"].get("hub") or {}).get("received_at")
  ...
  126|         c["dev"] = c["meta"].get("device") or {}
  ...
  173|     dup = [k for k, n in Counter(c["meta"].get("node_capture_id") for c in caps).items() if k and n > 1]
  ```
- **Concrete Failure Scenario**: If a capture record exported to `captures.json` has `meta: null` (which occurs when a capture is uploaded without metadata or before enrichment), `c["meta"]` evaluates to `None`. Calling `.get()` on `None` throws `AttributeError: 'NoneType' object has no attribute 'get'` and aborts report generation.
- **Suggested Fix**: Guard with `(c.get("meta") or {})`:
  ```python
  meta = c.get("meta") or {}
  hub = (meta.get("hub") or {}).get("received_at")
  c["dev"] = meta.get("device") or {}
  ...
  dup = [k for k, n in Counter((c.get("meta") or {}).get("node_capture_id") for c in caps).items() if k and n > 1]
  ```

---

### [MEDIUM] `field-tests/esp32-window-day/report.py:287, 288` — Unspecified encoding with Unicode glyphs crashes on non-UTF-8 locales
- **Severity**: Medium
- **Quoted Code**:
  ```python
  287|     (run / "report.html").write_text("\n".join(page))
  288|     (run / "summary.md").write_text("\n".join(f"- **{k}:** {v}" for k, v in summary) + "\n")
  ```
- **Concrete Failure Scenario**: `write_text()` without an `encoding` argument defaults to `locale.getpreferredencoding(False)`. On headless servers, remote SSH runs, or cron environments where `LANG=C` or `POSIX`, this defaults to ASCII. `summary` contains Unicode characters including `°C` (line 228), `±` / `−` (U+2212, lines 223, 224), `×` (U+00D7, line 230), `…` (U+2026, line 220), `→` (U+2192, line 234), and `—` (U+2014, line 227). Executing `report.py` in such environments crashes with `UnicodeEncodeError`.
- **Suggested Fix**: Explicitly pass `encoding="utf-8"` to all `write_text()` and `read_text()` calls:
  ```python
  (run / "report.html").write_text("\n".join(page), encoding="utf-8")
  (run / "summary.md").write_text("\n".join(f"- **{k}:** {v}" for k, v in summary) + "\n", encoding="utf-8")
  ```

---

### [MEDIUM] `field-tests/esp32-window-day/report.py:42, 133` — Unclosed file descriptors in CSV readers
- **Severity**: Medium
- **Quoted Code**:
  ```python
  42| def rows(path: Path) -> list[dict]:
  43|     return list(csv.DictReader(path.open())) if path.exists() else []
  ...
  133|     events = [(utc(r[0]), r[1] + (f": {r[2]}" if len(r) > 2 and r[2] else "")) for r in csv.reader((run / "events.csv").open())] \
  134|         if (run / "events.csv").exists() else []
  ```
- **Concrete Failure Scenario**: `path.open()` opens file descriptors without closing them or using a context manager. In repeated invocations or long-running scripts, this leaks file descriptors.
- **Suggested Fix**: Use `with path.open(encoding="utf-8") as f:` context managers.

---

### [MEDIUM] `field-tests/esp32-window-day/report.py:184, 185` — "Take photo now" latency calculation picks wrong capture if `caps` is unordered
- **Severity**: Medium
- **Quoted Code**:
  ```python
  180|     requested = [c for c in caps if c["wake_reason"] == "requested"]
  ...
  184|             got = next((c for c in requested if c["t"] >= when), None)
  185|             asks.append((when, got, (got["server_at"] - when).total_seconds() / 60 if got else None))
  ```
- **Concrete Failure Scenario**: `captures.json` loaded from the database or API is typically sorted reverse-chronologically (`ORDER BY captured_at DESC`). Because `requested` is not sorted chronologically, `next((c for c in requested if c["t"] >= when), None)` picks the first record in arbitrary or reverse order rather than the earliest capture immediately following `when`, reporting inaccurate latencies (e.g. hundreds of minutes instead of 1–2 minutes).
- **Suggested Fix**: Sort `requested` by timestamp:
  ```python
  requested = sorted([c for c in caps if c["wake_reason"] == "requested"], key=lambda c: c["t"])
  ```

---

### [LOW] `hardware/mockup_template.py:30–32, 40` — `ZeroDivisionError` when `cam_drop == apex`
- **Severity**: Low
- **Quoted Code**:
  ```python
  30|     h = apex - cam_drop
  31|     along, across = coverage(h)  # wide axis runs along the trap's length
  32|     mm_per_px = across / SENSOR_PX[1]
  ...
  40|         f"Resolution ≈ {mm_per_px:.3f} mm/px (≈ {1 / mm_per_px:.0f} px per mm): OFM (~6 mm) ≈ {6 / mm_per_px:.0f} px long.",
  ```
- **Concrete Failure Scenario**: If `--cam-drop` equals `--apex` (e.g. `python mockup_template.py --cam-drop 110 --apex 110`), `h = 0`, `across = 0.0`, and `mm_per_px = 0.0`. Line 40 raises `ZeroDivisionError: float division by zero`.
- **Suggested Fix**: Guard against `mm_per_px <= 0`:
  ```python
  res_str = f"≈ {1 / mm_per_px:.0f} px per mm" if mm_per_px > 0 else "N/A"
  ```

---

## 2. Security Issues

### [MEDIUM] `device/install.sh:14` & `device/install-hub.sh:13` — User group configuration skipped if user exists
- **Severity**: Medium
- **Quoted Code**:
  ```bash
  14| id -u sentinel >/dev/null 2>&1 || useradd --system --create-home --groups video,gpio,i2c sentinel
  ```
- **Concrete Failure Scenario**: If the `sentinel` service account was already created during an earlier partial install, hub install, or system provisioning, `id -u sentinel` succeeds (exit 0) and the right side of `||` is skipped. The user is left without `video`, `gpio`, and `i2c` group memberships. When the camera service starts, accessing `/dev/video*`, `/dev/i2c-*`, or GPIO controllers fails with `PermissionDenied`.
- **Suggested Fix**: Explicitly enforce group memberships with `usermod`:
  ```bash
  id -u sentinel >/dev/null 2>&1 || useradd --system --create-home sentinel
  usermod -a -G video,gpio,i2c sentinel
  ```

---

### [MEDIUM] `field-tests/esp32-window-day/start.sh:51–60` — Root-owned `/etc/sentinel/config.toml` permissions clobbered
- **Severity**: Medium
- **Quoted Code**:
  ```bash
  51| ssh -o BatchMode=yes "$HUB" "cd $HUB_DIR && { [ -e $HUB_CONFIG.before-window-test ] || cp $HUB_CONFIG $HUB_CONFIG.before-window-test; } && python3 - $HUB_CONFIG $PHOTO_EVERY_MIN $CHECKIN_MIN" <<'EOF'
  ...
  59| open(path, "w").write(s)
  ```
- **Concrete Failure Scenario**: `device/install-hub.sh` sets `/etc/sentinel/config.toml` permissions to `640` with owner `root:sentinel`. When `start.sh` connects via SSH as an unprivileged user (e.g. `pi`), `open(path, "w")` raises `PermissionError`. If run with `sudo`, `open(path, "w")` clobbers file ownership and permissions to default umask `644`, exposing API keys and credentials to other local users on the Pi.
- **Suggested Fix**: Use a temporary file and copy it in place with `sudo install -m 640 -g sentinel`.

---

## 3. Deprecated APIs / Outdated Patterns

### [LOW] `hardware/scad/camera_mount.scad:6–12` — Deprecated and incompatible camera mount model
- **Severity**: Low
- **Quoted Code**:
  ```openscad
  6| // Set to the Alpha Scents red plastic delta trap (hardware/TRAP.md). Its 110 mm peak is too low
  7| // for this inside mount to see the whole card (lens 85 mm up sees ~113 mm of the 174 mm across);
  8| // the lens needs to sit ~131-150 mm up, above the roof peak. Redesign as a roof housing before printing.
  9| // Camera numbers follow the Raspberry Pi Camera Module 3 board (25 x 24 mm, M2 holes...
  ```
- **Concrete Failure Scenario**: The repository's operational trap camera is the Arducam UC-572 (IMX219) or ESP32-CAM (see `CAMERAS.md`), whereas `camera_mount.scad` models the Camera Module 3. Furthermore, as noted in the file's header, mounting the camera at 85 mm misses 61 mm of the 174 mm card width. Anyone printing this STL will produce an unusable part.
- **Suggested Fix**: Move `camera_mount.scad` to a `legacy/` or `prototypes/` folder or update it to the external roof housing specification required by `TRAP.md`.

---

## 4. Inconsistencies

### [HIGH] `hardware/scad/liner_tray.scad:10, 20, 49` — Liner tray dimensions exceed delta trap floor width
- **Severity**: High
- **Quoted Code**:
  ```openscad
  10| floor_w = 195;   // mm, trap floor the tray must fit on
  ...
  13| rim     = 18;    // border that carries the markers
  ...
  20| W = liner_w + 2 * (clear + rim);
  ...
  49| if (W > floor_w || L > floor_l)
  50|     echo(str("WARNING: tray ", W, " x ", L, " mm does not fit the ", floor_w, " x ", floor_l, " mm floor; shrink rim/marker."));
  ```
- **Concrete Failure Scenario**: `liner_w = 174`, `clear = 1.0`, `rim = 18`. `W = 174 + 2 * (1 + 18) = 212 mm`. The Alpha Scents delta trap floor is only 195 mm wide. The generated model is 17 mm wider than the trap interior and physically cannot fit inside the trap.
- **Suggested Fix**: Reduce `rim` to 9 mm or switch to 10 mm ArUco markers with a 10 mm border so that `W = 174 + 2 * (1 + 9) = 194 mm <= 195 mm`.

---

### [MEDIUM] `field-tests/esp32-window-day/start.sh:51–60` — Regex assumption breaks on formatted/multiline TOML
- **Severity**: Medium
- **Quoted Code**:
  ```python
  56| s = re.sub(r"^times = \[.*?\].*$", f"times = [{times}]   # window day test", s, count=1, flags=re.M)
  57| s = re.sub(r"^checkin_min = .*\n", "", s, flags=re.M)
  58| s = s.replace("[hub]\n", f"[hub]\ncheckin_min = {checkin}   # window day test\n", 1)
  ```
- **Concrete Failure Scenario**: If `hub.toml` has `times` formatted across multiple lines (standard for TOML formatters when lists are long) or contains Windows `\r\n` line endings, `^times = \[.*?\].*$` fails to match because `.` does not match newlines without `re.DOTALL`. The replacement silently fails, leaving the production schedule intact during the window test.
- **Suggested Fix**: Use Python 3.11's built-in `tomllib` to parse and format the TOML configuration, or use `flags=re.M | re.S`.

---

## 5. Dead Code, Duplication, and Organization Problems

### [MEDIUM] `server/pyproject.toml:35–37` — Non-recursive package-data glob omits nested static assets
- **Severity**: Medium
- **Quoted Code**:
  ```toml
  35| [tool.setuptools.package-data]
  36| sentinel_server = ["templates/*.html", "static/*"]
  ```
- **Concrete Failure Scenario**: In setuptools, `static/*` matches only top-level files in `static/`. Any subdirectories (e.g. `static/css/*.css`, `static/js/*.js`, `static/vendor/*`) are omitted when building source distributions or wheels. Installing `sentinel-server` via `pip install .` on a deployment machine results in broken UI styling due to missing static subdirectories.
- **Suggested Fix**: Include recursive globs:
  ```toml
  [tool.setuptools.package-data]
  sentinel_server = ["templates/**/*.html", "templates/*.html", "static/**/*", "static/*"]
  ```

---

### [LOW] `hardware/scad/liner_tray.scad:35, 42–45` — Split printing cut slices lure seat without alignment features
- **Severity**: Low
- **Quoted Code**:
  ```openscad
  35|     translate([W / 2 - lure_w / 2 - 1.2, L / 2 - lure_l / 2 - 1.2, base_t])
  ...
  42| if (split) {
  43|     intersection() { tray(); cube([W, L / 2, 10]); }
  44|     translate([0, 10, 0]) intersection() { tray(); translate([0, L / 2, 0]) cube([W, L / 2, 10]); }
  ```
- **Concrete Failure Scenario**: Setting `split = true` cuts the model at `Y = L / 2`, which bisects the thin 0.8 mm lure seat directly through its center. The resulting halves have no indexing pins, tabs, or dovetails. A flat butt joint along a 2 mm thin base will fracture under field handling.
- **Suggested Fix**: Offset the split line away from the lure seat center and add alignment puzzle joints or locating pin holes.

---

## 6. Performance & Optimization Opportunities

### [LOW] `device/esp32-node/platformio.ini:14–16` — Conservative upload speed slows development cycles
- **Severity**: Low
- **Quoted Code**:
  ```ini
  14| ; The CH343 USB chip garbles data above 115200 baud on macOS.
  15| upload_speed = 115200
  16| monitor_speed = 115200
  ```
- **Concrete Scenario**: Flashing an 8 MB firmware image at 115,200 baud takes several minutes per build cycle. With updated macOS CH343 VCP drivers (1.5+), 460,800 or 921,600 baud functions reliably.
- **Suggested Fix**: Allow overriding `upload_speed` via an environment variable or document the driver update so developers can flash at `460800`.

---

## 7. Test Coverage Gaps

1. **`field-tests/esp32-window-day/report.py`**: No unit tests exist for `report.py` parsing logic. Missing/corrupted `status.jsonl`, empty `captures.json`, captures with `meta: null`, or missing timestamps should be covered by unit tests with mocked fixtures.
2. **`hardware/make_markers.py` & `hardware/mockup_template.py`**: No regression tests verify that SVG output produces valid, closed paths or that ArUco marker coordinates align with OpenCV detection conventions.
3. **`device/install.sh` & `device/install-hub.sh`**: No idempotency or user-existence tests run in CI (e.g. testing `install.sh` when `sentinel` user already exists).

---

## Prioritized Next Steps

1. **Fix `field-tests/esp32-window-day/start.sh`**: Replace `grep ... && { ... }` and `(( ... )) && ...` with standard `if` statements so the script does not abort on a healthy Pi under `set -e`.
2. **Fix `hardware/mockup_template.py`**: Stop drawing a continuous cut rectangle along `y0` and `y1` so the end flaps remain attached to the floor panel.
3. **Fix `hardware/make_markers.py`**: Reorder marker generation to match clockwise corner ordering (`0 TL, 1 TR, 2 BR, 3 BL`) so ID 2 and ID 3 are not transposed on the printed sheet.
4. **Fix `server/pyproject.toml` packaging**: Update `package-data` to include recursive globs (`static/**/*`, `templates/**/*.html`) to prevent missing UI assets in packaged distributions.
5. **Fix `device/install.sh` user provisioning**: Add `usermod -a -G video,gpio,i2c sentinel` to guarantee group permissions when the user already exists.
6. **Resize `hardware/scad/liner_tray.scad`**: Reduce tray rim from 18 mm to <= 9 mm so the tray fits within the 195 mm trap floor width.
