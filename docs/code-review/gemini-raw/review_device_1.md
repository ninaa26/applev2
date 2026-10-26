# Code Review Report: Chunk 2 of 3 (`device/` Package)

**Scope of this chunk:**
- `device/sentinel_device/camera.py`
- `device/sentinel_device/config.py`
- `device/sentinel_device/cycle.py`
- `device/sentinel_device/flatfield.py`
- `device/sentinel_device/gateway.py`
- `device/sentinel_device/hardware.py`
- `device/sentinel_device/schedule.py`
- `device/sentinel_device/state.py`
- `device/sentinel_device/tools/__init__.py`
- `device/sentinel_device/tools/camera_bench.py`

Special focus applied to the ESP32 node firmware $\leftrightarrow$ hub gateway $\leftrightarrow$ server upload API protocol, error handling, power/schedule lifecycles, and concurrency.

---

## 1. Bugs (Correctness, Crashes, Race Conditions, Data Loss, Date/Time Errors)

### [BUG-01] Premature Skip of Scheduled Capture Window in Gateway Schedule Calculation
- **File:** `device/sentinel_device/gateway.py:163-166`
- **Severity:** High
- **Code:**
  ```python
  163|         wakes, t = [], now - offset
  164|         for _ in range(12):  # a node that misses a window still knows when to wake after that
  165|             t = next_wake(t, self.cfg["schedule"]["times"], self.cfg["timezone"], min_gap=timedelta(minutes=2))
  166|             wakes.append(t + offset)
  ```
- **Failure Scenario:**
  Suppose a trap has a slot at `10:00:00`, and `node_offset_s = 60` (node scheduled to wake at `10:01:00`). If an ESP32 node performs an intermediate check-in (`checkin_min = 30`) or its timer drifted by 35 seconds, contacting the hub at `09:59:25`:
  `now - offset` is `09:58:25`. In `schedule.py:24`, `earliest = local_now + min_gap` evaluates to `09:58:25 + 2 minutes = 10:00:25`.
  Because the slot `candidate` (`10:00:00`) is *less* than `earliest` (`10:00:25`), `next_wake` skips `10:00:00` and returns the *next* slot (`13:00:00`).
  The node receives `sleep_s` for 3 hours later and goes to deep sleep, **completely missing its scheduled 10:00 photo capture**.
- **Suggested Fix:**
  When computing the upcoming wake for nodes during a check-in, do not subtract `offset` and apply a 2-minute `min_gap` against past time. Instead, check if the current slot has not yet passed (`now < slot + offset`), or pass `min_gap=timedelta(seconds=10)` when evaluating check-ins:
  ```python
  # Ensure upcoming slot is preserved if the node is checking in just prior to window
  t = now if now < (next_slot := next_wake(now, self.cfg["schedule"]["times"], self.cfg["timezone"])) else now - offset
  ```

---

### [BUG-02] Shared Lock Held Across Blocking Disk I/O in Gateway Capture Handler
- **File:** `device/sentinel_device/gateway.py:201-212`
- **Severity:** High
- **Code:**
  ```python
  201|         with self.lock:
  202|             if self.requests.get(trap_id) is not None and captured >= self.requests[trap_id]:
  203|                 self.served[trap_id] = self.requests[trap_id]  # this photo answers the dashboard's request
  204|             # A retry after a lost reply: same node_capture_id, already queued or already sent.
  205|             if not any(any(d.glob(f"*_{node_id}.jpg")) for d in (queue.queue_dir, queue.sent_dir)):
  206|                 uid = f"{captured.strftime('%Y%m%dT%H%M%SZ')}_{trap_id}_{node_id}"
  207|                 meta.update(capture_uid=uid, trap_id=trap_id, captured_at=captured.isoformat(),
  208|                             wake_reason=meta.get("wake_reason", "scheduled"),
  209|                             hub={"received_at": now.isoformat(), "hub_trap_id": self.cfg["trap_id"]})
  210|                 tmp = queue.queue_dir / f".{uid}.part"
  211|                 tmp.write_bytes(body)
  212|                 queue.add(tmp.rename(tmp.with_name(f"{uid}.jpg")), meta)
  ```
- **Failure Scenario:**
  `self.lock` is a single lock shared across all Gateway operations (`trap_for`, `photo_wanted`, `schedule_reply`, `schedule`, `preview`, `refresh_nodes`).
  Writing up to `max_image_mb` (4 MB) to an SD card (`tmp.write_bytes(body)`) while holding `self.lock` takes hundreds of milliseconds or seconds during slow flash writes. If multiple ESP32 nodes wake up during the window and attempt to upload or check their schedule simultaneously, all worker threads stall waiting for `self.lock`, causing ESP32 client socket timeouts or dropped requests.
- **Suggested Fix:**
  Perform deduplication check and state reservation under the lock, but perform `write_bytes` and `queue.add` outside the lock:
  ```python
  with self.lock:
      if self.requests.get(trap_id) is not None and captured >= self.requests[trap_id]:
          self.served[trap_id] = self.requests[trap_id]
      if any(any(d.glob(f"*_{node_id}.jpg")) for d in (queue.queue_dir, queue.sent_dir)):
          return 200, {**self.schedule_reply(trap_id), "duplicate": True}
      uid = f"{captured.strftime('%Y%m%dT%H%M%SZ')}_{trap_id}_{node_id}"

  # Perform file writing and queuing outside self.lock
  tmp = queue.queue_dir / f".{uid}.part"
  tmp.write_bytes(body)
  ...
  ```

---

### [BUG-03] Potential `SameFileError` / Improper Staging in `Queue.add`
- **File:** `device/sentinel_device/gateway.py:210-212`
- **Severity:** High
- **Code:**
  ```python
  210|                 tmp = queue.queue_dir / f".{uid}.part"
  211|                 tmp.write_bytes(body)
  212|                 queue.add(tmp.rename(tmp.with_name(f"{uid}.jpg")), meta)
  ```
- **Failure Scenario:**
  In `cycle.py:35-65`, temporary capture files are staged in `data_dir` and then moved into `Queue.queue_dir` via `queue.add(tmp, meta)`.
  In `gateway.py`, line 212 renames `.{uid}.part` to `{uid}.jpg` *directly inside* `queue.queue_dir`. When `queue.add(path, meta)` executes, if `Queue.add` uses `shutil.move(src, self.queue_dir / src.name)`, Python's `shutil` raises `shutil.SameFileError` because the source and destination are identical. Even if `Queue.add` does not use `shutil`, failed writes leave unmonitored hidden `.{uid}.part` files inside `queue_dir`.
- **Suggested Fix:**
  Stage the incoming upload in `data_dir / "tmp"` or `self.nodes_dir / trap_id / "tmp"`, and pass the staged file path to `queue.add`:
  ```python
  tmp_dir = self.nodes_dir / trap_id / "tmp"
  tmp_dir.mkdir(parents=True, exist_ok=True)
  tmp = tmp_dir / f"{uid}.jpg"
  tmp.write_bytes(body)
  queue.add(tmp, meta)
  ```

---

### [BUG-04] Crash in `wake_reason` When `expected_iso` is Offset-Naive
- **File:** `device/sentinel_device/schedule.py:53-54`
- **Severity:** Medium
- **Code:**
  ```python
  53|     expected = datetime.fromisoformat(expected_iso)
  54|     if abs(now - expected) <= WAKE_TOLERANCE:
  ```
- **Failure Scenario:**
  `now` is initialized in `cycle.py:98` as `datetime.now(timezone.utc)` (offset-aware). If `expected_iso` was written without a timezone offset (e.g. from an older state file or manual entry like `"2026-10-23T10:00:00"`), `expected` is offset-naive.
  Python raises `TypeError: can't subtract offset-naive and offset-aware datetimes`, crashing `sentinel-cycle` at boot.
- **Suggested Fix:**
  Ensure `expected` has a timezone assigned:
  ```python
  expected = datetime.fromisoformat(expected_iso)
  if expected.tzinfo is None:
      expected = expected.replace(tzinfo=timezone.utc)
  ```

---

### [BUG-05] Gateway Rejects Valid Requests Containing URL Query Parameters
- **File:** `device/sentinel_device/gateway.py:320, 339`
- **Severity:** Medium
- **Code:**
  ```python
  320|             if self.path != "/node/v1/captures":
  321|                 return self._reply(404, {"error": "not found"})
  ...
  339|             if self.path != "/node/v1/schedule":
  340|                 return self._reply(404, {"error": "not found"})
  ```
- **Failure Scenario:**
  In `BaseHTTPRequestHandler`, `self.path` includes the query string (e.g. `POST /node/v1/captures?retry=1` or `GET /node/v1/schedule?v=1`).
  Because equality is checked directly against `self.path`, any request containing query parameters is returned a 404 Not Found.
- **Suggested Fix:**
  Strip query parameters using `urllib.parse.urlparse`:
  ```python
  from urllib.parse import urlparse
  req_path = urlparse(self.path).path
  if req_path != "/node/v1/captures": ...
  ```

---

### [BUG-06] Unhandled `ValueError` and Server Exceptions in Gateway POST Handler
- **File:** `device/sentinel_device/gateway.py:322-326`
- **Severity:** Medium
- **Code:**
  ```python
  322|             length = int(self.headers.get("Content-Length") or 0)
  323|             if length > gw.hub["max_image_mb"] * 1_000_000:
  324|                 return self._reply(413, {"error": "photo too large"})
  325|             body = self.rfile.read(length)
  326|             self._reply(*gw.capture(self.headers.get("Authorization", ""), self.headers.get("X-Sentinel-Meta", ""), body))
  ```
- **Failure Scenario:**
  If a malformed `Content-Length` header is sent by a client (e.g. invalid string), `int()` throws `ValueError`. If writing to disk inside `gw.capture` fails due to `OSError: [Errno 28] No space left on device`, an unhandled exception bubbles up. In `ThreadingHTTPServer`, this terminates the connection abruptly with no HTTP response code to the client.
- **Suggested Fix:**
  Catch `ValueError` and return `400 Bad Request`, and catch `OSError` returning `500 Internal Server Error`:
  ```python
  try:
      length = int(self.headers.get("Content-Length", 0))
  except ValueError:
      return self._reply(400, {"error": "invalid Content-Length"})
  ```

---

### [BUG-07] Unhandled `FileNotFoundError` in `UsbCamera` Control Configuration
- **File:** `device/sentinel_device/camera.py:137-142`
- **Severity:** Medium
- **Code:**
  ```python
  137|             r = subprocess.run(
  138|                 ["v4l2-ctl", "-d", str(self.cfg["usb_device"]), f"--set-ctrl={key}={int(value)}"],
  139|                 capture_output=True, text=True,
  140|             )
  ```
- **Failure Scenario:**
  If the `v4l-utils` package is not installed on the system, `subprocess.run` raises `FileNotFoundError: [Errno 2] No such file or directory: 'v4l2-ctl'`. Unlike the `cv2` import error at line 147, this exception is not caught and does not raise `CaptureError`.
- **Suggested Fix:**
  Wrap `subprocess.run` in a `try...except FileNotFoundError` block:
  ```python
  except FileNotFoundError as e:
      raise CaptureError("v4l2-ctl is not installed: sudo apt install v4l-utils") from e
  ```

---

### [BUG-08] Non-Compliant JSON `NaN` Output in `camera_bench`
- **File:** `device/sentinel_device/tools/camera_bench.py:185, 261`
- **Severity:** Low
- **Code:**
  ```python
  185|     blur_px = float(np.median(widths)) if widths else float("nan")
  ...
  191|         "edge_blur_px": round(blur_px, 2),
  192|         "edge_blur_mm": round(blur_px / px_per_mm, 3),
  ...
  261|     (folder / f"{args.tag}.json").write_text(json.dumps(result, indent=2))
  ```
- **Failure Scenario:**
  When `widths` is empty (e.g. poor lighting or blurry edges where checkerboard transitions are missed), `blur_px` is `float("nan")`. Python's `json.dumps` outputs unquoted `NaN`. This violates RFC 8259 JSON standards, causing standard JSON parsers in frontends or other tools to fail with syntax errors.
- **Suggested Fix:**
  Use `None` instead of `float("nan")`:
  ```python
  blur_px = float(np.median(widths)) if widths else None
  "edge_blur_px": round(blur_px, 2) if blur_px is not None else None,
  "edge_blur_mm": round(blur_px / px_per_mm, 3) if blur_px is not None else None,
  ```

---

### [BUG-09] Crash on Fixed-Focus Cameras in `camera_bench`
- **File:** `device/sentinel_device/tools/camera_bench.py:100-103`
- **Severity:** Low
- **Code:**
  ```python
  100|         if lens_position is None and "AfMode" in cam.camera_controls:
  101|             cam.autofocus_cycle()
  102|         elif lens_position is not None:
  103|             cam.set_controls({"AfMode": controls.AfModeEnum.Manual, "LensPosition": lens_position})
  ```
- **Failure Scenario:**
  If a user passes `--lens-position 6.5` while benchmarking a fixed-focus camera (e.g. Raspberry Pi Camera Module 2 / IMX219 or HQ Camera), `cam.set_controls(...)` is called without checking whether `"AfMode"` is in `cam.camera_controls` (unlike `camera.py:81`). Picamera2 throws a `RuntimeError`.
- **Suggested Fix:**
  Guard the manual focus setting:
  ```python
  elif lens_position is not None and "AfMode" in cam.camera_controls:
      cam.set_controls({"AfMode": controls.AfModeEnum.Manual, "LensPosition": lens_position})
  ```

---

## 2. Security Issues

### [SEC-01] Unbounded Disk Consumption via `status.jsonl`
- **File:** `device/sentinel_device/gateway.py:237-240`
- **Severity:** Medium
- **Code:**
  ```python
  237|         path = self.nodes_dir / trap_id / "status.jsonl"
  238|         path.parent.mkdir(parents=True, exist_ok=True)
  239|         with self.lock, path.open("a") as f:
  240|             f.write(json.dumps(status) + "\n")
  ```
- **Failure Scenario:**
  Every time a node requests its schedule or checks in, status metadata is appended to `status.jsonl`. A hub servicing several ESP32 nodes checking in every 30 minutes will accumulate tens of thousands of lines. The file is never rotated, truncated, or uploaded to the server, leading to silent, unbounded storage exhaustion on the hub's SD card.
- **Suggested Fix:**
  Implement log rotation or truncate to the most recent $N$ entries (e.g. keeping the last 1,000 status check-ins).

---

### [SEC-02] Brittle Authorization Header Parsing
- **File:** `device/sentinel_device/gateway.py:140-141`
- **Severity:** Low
- **Code:**
  ```python
  140|         key = authorization.removeprefix("Bearer ").strip()
  141|         if not key:
  142|             return None
  ```
- **Failure Scenario:**
  RFC 7235 / RFC 6750 specifies that auth scheme names are case-insensitive. If an ESP32 firmware HTTP library or an intermediate proxy formats the header as `bearer <token>`, `removeprefix("Bearer ")` does not match. `key` retains the prefix `bearer `, which changes the SHA-256 hash calculation, rejecting valid authenticated nodes with a 401 Unauthorized.
- **Suggested Fix:**
  Parse the scheme case-insensitively:
  ```python
  parts = authorization.split(None, 1)
  if len(parts) != 2 or parts[0].lower() != "bearer":
      return None
  key = parts[1].strip()
  ```

---

## 3. Deprecated APIs / Outdated Patterns

### [DEP-01] Deprecated Pillow Resampling Constants
- **File:** `device/sentinel_device/camera.py:252` & `device/sentinel_device/flatfield.py:74`
- **Severity:** Low
- **Code:**
  `camera.py:252`:
  ```python
  252|             moth = moth.rotate(ins["angle"], resample=Image.BICUBIC)
  ```
  `flatfield.py:74`:
  ```python
  74|         g = Image.fromarray(gain[..., c], mode="F").resize(img.size, Image.BILINEAR)
  ```
- **Failure Scenario:**
  In Pillow $\ge 10.0.0$, `Image.BICUBIC` and `Image.BILINEAR` are deprecated aliases. Starting with Pillow 11+, accessing these constants on `Image` will raise `AttributeError`.
- **Suggested Fix:**
  Use `Image.Resampling.BICUBIC` and `Image.Resampling.BILINEAR`.

---

## 4. Inconsistencies

### [INC-01] Gateway `done` Set Never Cleared Across Multiple Windows
- **File:** `device/sentinel_device/gateway.py:87, 281, 365`
- **Severity:** Medium
- **Code:**
  ```python
  87|         self.done: set[str] = set()  # nodes that asked for their schedule since the window opened
  ...
  281|             return self.done >= set(self.hashes)
  ...
  365|         while time.monotonic() < until and not gw.all_done():
  ```
- **Failure Scenario:**
  The docstring states `self.done` tracks nodes that asked for their schedule *since the window opened*. However, `self.done` is only initialized once in `Gateway.__init__`. It is never cleared in `serve_window()`.
  If a `Gateway` instance is reused across multiple wake windows, `gw.all_done()` returns `True` immediately in the second window, terminating `serve_window()` after 0.5s before any ESP32 nodes can connect.
- **Suggested Fix:**
  Clear `gw.done` under lock at the start of `serve_window`:
  ```python
  with gw.lock:
      gw.done.clear()
  ```

---

### [INC-02] Duplicate Capture Response Omits `uid`
- **File:** `device/sentinel_device/gateway.py:214 vs 216`
- **Severity:** Low
- **Code:**
  ```python
  214|         if uid is None:
  215|             return 200, {**self.schedule_reply(trap_id), "duplicate": True}
  216|         log.info("node %s: queued %s (%d kB)", trap_id, uid, len(body) // 1000)
  217|         return 201, {**self.schedule_reply(trap_id), "uid": uid}
  ```
- **Failure Scenario:**
  When a node successfully retries a capture because the original response was dropped, the gateway returns status `200` with `"duplicate": True`, but does not return the capture `"uid"`. If node firmware expects `"uid"` in all successful responses (200 and 201) to log or update its internal sequence state, it receives `null`/undefined.
- **Suggested Fix:**
  Locate the matching existing capture file stem and include `"uid"` in the 200 duplicate response as well.

---

## 5. Dead Code, Duplication, and Organization Problems

### [ORG-01] Global Environment Mutation in `Picamera2Camera._tuning`
- **File:** `device/sentinel_device/camera.py:42`
- **Severity:** Low
- **Code:**
  ```python
  42|         os.environ.pop("LIBCAMERA_RPI_TUNING_FILE", None)
  ```
- **Issue:**
  Directly modifying `os.environ` inside an instance method has process-wide side-effects and is not thread-safe if multiple camera tasks or threads run concurrently.
- **Suggested Fix:**
  Pass configuration tuning files explicitly to the `Picamera2` constructor or scope environment variable manipulation using a thread-safe context manager.

---

## 6. Performance & Optimization Opportunities

### [PERF-01] Excessive Memory Allocation in `flatfield.apply`
- **File:** `device/sentinel_device/flatfield.py:72-76`
- **Severity:** Medium
- **Code:**
  ```python
  72|     img = img.convert("RGB")
  73|     out = []
  74|     for c, band in enumerate(img.split()):
  75|         g = Image.fromarray(gain[..., c], mode="F").resize(img.size, Image.BILINEAR)
  76|         out.append(Image.fromarray(np.clip(np.asarray(band, dtype=np.float32) * np.asarray(g), 0, 255).astype(np.uint8)))
  77|     return Image.merge("RGB", out)
  ```
- **Optimization:**
  Splitting the image into 3 channels and constructing full-resolution 32-bit floating point arrays (`float32`) creates ~50 MB per channel for 12 MP sensors (IMX708 / Pi Camera Module 3). Peak memory usage reaches >250 MB. On memory-constrained devices (e.g. Raspberry Pi Zero 2 W with 512MB RAM), this can trigger Linux OOM kills.
- **Suggested Fix:**
  Resize the entire $(rows, cols, 3)$ gain map using OpenCV (`cv2.resize`) or apply correction with uint16 integer arithmetic in chunks.

---

## 7. Test Coverage Gaps

1. **`gateway.py` Retry and Duplicate Deduplication:** No tests verifying duplicate detection when an ESP32 node retries with the same `node_capture_id` after a lost connection.
2. **`gateway.py` Clock Synchronization Fallbacks:** No test validating that `captured_at` is accurately computed when `clock_synced=False` and only `age_s` is provided.
3. **`schedule.py` DST Gaps and Ambiguous Hours:** No test verifying `next_wake` behavior during Daylight Saving Time "spring forward" (gap) and "fall back" (fold) transitions.
4. **`hardware.py` SHT4x CRC Failure:** No test exercising CRC error handling in `sht4x_decode` and validating graceful return of `None` from `read_sht4x`.
5. **`camera.py` UsbCamera Brightness Step Loop:** No mock test covering the multi-attempt clip reduction loop in `UsbCamera.capture`.

---

## Prioritized Next Steps

1. **Fix Schedule Skipping (`gateway.py:163-166`):** Adjust `next_wake` parameters for node check-in calculations to prevent ESP32 nodes checking in shortly before scheduled windows from missing their capture slots.
2. **Relieve Gateway Lock Contention (`gateway.py:201-212`):** Move file I/O operations (`write_bytes`, `queue.add`) out of `with self.lock:` to prevent concurrent node check-in stalls.
3. **Fix Queue Staging (`gateway.py:210-212`):** Write temporary incoming parts to a staging directory rather than renaming directly within `queue_dir`.
4. **Harden URL and Header Parsing (`gateway.py:140, 320, 339`):** Parse URL paths with `urlparse` and handle `Authorization` headers case-insensitively.
5. **Ensure Aware Datetime Consistency (`schedule.py:53-54`):** Guarantee `expected_iso` datetime is timezone-aware before subtraction against `now`.
