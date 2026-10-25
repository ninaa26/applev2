# Code Review: Chunk 3 of 5 (Pipeline & Worker Scope)

**Scope Files Reviewed:**
- [detect.py](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py)
- [track.py](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/track.py)
- [worker.py](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py)

---

## 1. Bugs (Correctness, Crashes, Race Conditions, Data Loss, Errors)

### [worker.py:33](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L33)
- **Severity**: Critical
- **Relevant Code**:
  ```python
  days = (when - type(when)(2000, 1, 6, 18, 14)).total_seconds() / 86400
  ```
- **Failure Scenario**: `moon_illumination` is invoked on line 123 during every capture execution (`"moon": moon_illumination(cap.captured_at)`). If `cap.captured_at` is timezone-aware (the modern standard for ISO-8601 timestamps and aware UTC datetimes in SQLAlchemy/Pydantic), `type(when)(2000, 1, 6, 18, 14)` instantiates a **naive** `datetime` without `tzinfo`. In Python, subtracting an offset-naive datetime from an offset-aware datetime immediately raises `TypeError: can't subtract offset-naive and offset-aware datetimes`, crashing `Pipeline.process` for every single capture.
- **Suggested Fix**:
  Preserve or match timezone awareness:
  ```python
  from datetime import datetime, timezone
  
  def moon_illumination(when: datetime) -> float:
      ref_tz = when.tzinfo if when.tzinfo is not None else timezone.utc
      epoch = datetime(2000, 1, 6, 18, 14, tzinfo=ref_tz)
      dt = when if when.tzinfo is not None else when.replace(tzinfo=timezone.utc)
      days = (dt - epoch).total_seconds() / 86400
      return round((1 - math.cos(2 * math.pi * (days % 29.530588853) / 29.530588853)) / 2, 2)
  ```

---

### [worker.py:188-205](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L188-L205)
- **Severity**: Critical
- **Relevant Code**:
  ```python
  for t in db.scalars(select(Track).where(Track.card_id == card_id)):
      if not t.reviewed:  # people's labels and rejections are kept (and reviews point at them)
          db.delete(t)
  db.flush()
  for c in caps:
      self.process(db, c, check_liner=False, found=found[c.id])
      db.flush()
  ```
- **Failure Scenario**: Tracking accumulator corruption on reviewed tracks. In `reprocess_card`, detections are deleted (line 195) and unreviewed tracks are deleted (line 200). Reviewed tracks (`t.reviewed == True`) are kept to preserve manual classifications. However, the cumulative tracking counters on these surviving tracks (`t.n_seen`, `t.n_classified`, `t.prob_sum`, and `t.misses`) are **not reset**. When `self.process` replays all card captures from the beginning:
  1. Line 146 (`t.n_seen += 1`) increments on top of the old counts (doubling `n_seen`).
  2. Lines 164–166 (`summed[k] = summed.get(k, 0.0) + v; t.prob_sum = summed; t.n_classified += 1`) add species probabilities to the previous sum and double `n_classified`.
  3. If the insect first landed on the card in photo 4, captures 1–3 will increment `t.misses` (line 181) for photos taken before the insect was even present!
- **Suggested Fix**:
  Reset the tracking runtime counters for kept reviewed tracks before re-running `self.process`:
  ```python
  for t in db.scalars(select(Track).where(Track.card_id == card_id)):
      if not t.reviewed:
          db.delete(t)
      else:
          t.n_seen = 0
          t.n_classified = 0
          t.prob_sum = {}
          t.misses = 0
  db.flush()
  ```

---

### [detect.py:539-540](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L539-L540)
- **Severity**: High
- **Relevant Code**:
  ```python
  cands = {p / k for p in pitches for k in range(1, 5) if p / k >= 12}
  return max(cands, key=prominence)
  ```
- **Failure Scenario**: `_period` detects peaks starting from `min_lag = 6` (line 558). If high-frequency grid noise or fine line spacing produces measured pitches where `p < 12.0` (e.g. `[10.5, 11.0]`), then for all $k \in \{1, 2, 3, 4\}$, $p/k < 12$. The set comprehension filters out every item, leaving `cands = set()`. Calling `max(cands, ...)` on an empty set crashes with `ValueError: max() arg is an empty sequence`, aborting the detector entirely.
- **Suggested Fix**:
  Provide a fallback before evaluating `max`:
  ```python
  cands = {p / k for p in pitches for k in range(1, 5) if p / k >= 12}
  if not cands:
      return float(np.median(pitches))
  return max(cands, key=prominence)
  ```

---

### [worker.py:153-157](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L153-L157) & [worker.py:146](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L146)
- **Severity**: High
- **Relevant Code**:
  ```python
  t = Track(
      card_id=cap.card_id, first_seen_at=cap.captured_at, last_seen_at=cap.captured_at,
      first_capture_id=cap.id, x1=box.x1, y1=box.y1, x2=box.x2, y2=box.y2, prob_sum={},
      n_insects=box.n,
  )
  db.add(t)
  db.flush()
  ```
- **Failure Scenario**: Counter omission and uninitialized state on new tracks. When creating a new `Track`, `n_seen`, `misses`, `n_classified`, and `status` are not passed. If `n_seen` or `misses` defaults to `0` or `None`:
  1. A newly detected insect has appeared in 1 photo, but its `n_seen` is left as `0` (or `None`). If `None`, line 146 (`t.n_seen += 1`) fails with a `TypeError` on the next photo. If `0`, confirmation requires 3 photos instead of `CONFIRM_AFTER = 2`.
  2. If `status` is not initialized in Python, line 171 (`if t.status == "candidate" and t.n_seen >= trk.CONFIRM_AFTER`) risks evaluating against `None` if server-side defaults are used.
- **Suggested Fix**:
  Explicitly initialize all track state attributes:
  ```python
  t = Track(
      card_id=cap.card_id, first_seen_at=cap.captured_at, last_seen_at=cap.captured_at,
      first_capture_id=cap.id, x1=box.x1, y1=box.y1, x2=box.x2, y2=box.y2, prob_sum={},
      n_insects=box.n, n_seen=1, misses=0, n_classified=0, status="candidate"
  )
  ```

---

### [worker.py:120-130](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L120-L130) & [worker.py:224-243](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L224-L243)
- **Severity**: High
- **Relevant Code**:
  ```python
  cap.width, cap.height = w, h
  if check_liner:
      _keep_liner_if_unchanged(db, cap, [trk.Rect(b.x1, b.y1, b.x2, b.y2) for b in boxes])

  # Tracks on this card that are still alive.
  live = list(
      db.scalars(
          select(Track).where(Track.card_id == cap.card_id, Track.status.in_(["candidate", "confirmed"]))
      )
  )
  ```
- **Failure Scenario**: Execution does not stop after reverting an accidental liner change. If `_keep_liner_if_unchanged` determines that the liner was not changed (e.g. battery swap), it invokes `services.undo_new_card(db, card, ...)`. However,
`_keep_liner_if_unchanged` returns `None` and does not signal `process()` to abort or re-evaluate. Consequently:
1. `cap.card_id` in Python may still reference the undone card (or point to an in-memory stale ID).
2. If `undo_new_card` deleted or reassigned the card record, subsequent operations (`db.add(Track(card_id=cap.card_id...))` and `Detection(...)`) either violate foreign key constraints or write tracking records to the cancelled card.
3. Metadata computed earlier on lines 120–127 (`liner_days`, `card_old` event) used the undone card rather than the previous card.
- **Suggested Fix**:
  Have `_keep_liner_if_unchanged` return a boolean indicating whether the card was undone. If `True`, refresh `cap`, reload the active card, or return/re-route processing:
  ```python
  if check_liner and _keep_liner_if_unchanged(db, cap, [trk.Rect(b.x1, b.y1, b.x2, b.y2) for b in boxes]):
      db.refresh(cap)
      return  # or re-process under previous card
  ```

---

### [detect.py:655](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L655) & [worker.py:80-81](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L80-L81)
- **Severity**: Medium
- **Relevant Code**:
  ```python
  # detect.py:655
  outline = card_outline(cv2.imread(str(image_path)))

  # worker.py:80-81
  bgr = cv2.imread(str(path))
  quality = photo_quality(bgr, info["card"] if "card" in info else card_outline(bgr))
  ```
- **Failure Scenario**: Unlike `BaselineDetector` and `YoloDetector` (which check `if img is None: raise ValueError`), `FlatbugDetector.detect` and `Pipeline._detect` pass the result of `cv2.imread(...)` directly into `card_outline` and `photo_quality` without verifying it succeeded. If the file is missing or corrupted, `card_outline` crashes with `AttributeError: 'NoneType' object has no attribute 'shape'`.
- **Suggested Fix**:
  Validate `cv2.imread` return value:
  ```python
  bgr = cv2.imread(str(path))
  if bgr is None:
      raise ValueError(f"Cannot read image: {path}")
  ```

---

### [track.py:73-85](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/track.py#L73-L85)
- **Severity**: Medium
- **Relevant Code**:
  ```python
  species, total = max(prob_sum.items(), key=lambda kv: kv[1])
  conf = total / n
  if conf >= AUTO_THRESHOLD:
      status = "auto"
  elif conf >= REVIEW_THRESHOLD:
      status = "review"
  else:
      status = "unknown"
  return species, conf, status
  ```
- **Failure Scenario**: Count inflation from low-confidence tracks. When `conf < REVIEW_THRESHOLD` (0.50), `status` is set to `"unknown"`, but `species` remains set to `max(prob_sum)`. Any count query filtering on `status == "confirmed" and review_status != "rejected"` (e.g. line 237) will count the insect under `species` (e.g., `"codling_moth"`) even though confidence was below 50% and the track was never routed to human review (`review_status != "review"`).
- **Suggested Fix**:
  When confidence is below `REVIEW_THRESHOLD`, set the species to `"unknown"` or route to `"review"`:
  ```python
  if conf >= AUTO_THRESHOLD:
      status = "auto"
  elif conf >= REVIEW_THRESHOLD:
      status = "review"
  else:
      species = "unknown"
      status = "unknown"
  return species, conf, status
  ```

---

### [worker.py:104, 108](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L104)
- **Severity**: Low
- **Relevant Code**:
  ```python
  problem = blur_problem([m["sharpness"] for m in before if m.get("sharpness")], quality["sharpness"])
  ...
  problem = scale_problem([m["px_per_mm"] for m in before if m.get("px_per_mm")], ppm) or problem
  ```
- **Failure Scenario**: `0.0` is falsy in Python. If an extremely blurred photo had `sharpness == 0.0`, `m.get("sharpness")` evaluates to `False` and drops the sample from historical baseline calculations.
- **Suggested Fix**:
  Check `if m.get(...) is not None:`.

---

### [worker.py:280](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L280)
- **Severity**: Low
- **Relevant Code**:
  ```python
  cap.status, cap.error = "failed", f"{e.__class__.__name__}: {e}"[:2000]
  ```
- **Failure Scenario**: In `process_pending`, when an exception occurs, `cap.status` and `cap.error` are updated, but `cap.processed_at` remains `None`. In contrast, line 111 sets `cap.processed_at = utcnow()`. This causes inconsistent query results when filtering failed captures by `processed_at`.
- **Suggested Fix**:
  Set `cap.processed_at = utcnow()` in the exception block.

---

## 2. Security Issues

### [worker.py:77](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L77)
- **Severity**: High
- **Relevant Code**:
  ```python
  path = get_settings().media_dir / cap.image_path
  ```
- **Failure Scenario**: Path traversal. In `pathlib.Path`, if `cap.image_path` is absolute (e.g., `/etc/shadow`) or contains `../`, `media_dir / cap.image_path` navigates outside `media_dir`. An attacker manipulating image paths can force the server to read arbitrary files from the filesystem via OpenCV and PIL.
- **Suggested Fix**:
  Resolve and enforce directory containment:
  ```python
  media_dir = get_settings().media_dir.resolve()
  path = (media_dir / cap.image_path).resolve()
  if not path.is_relative_to(media_dir):
      raise ValueError(f"Security: invalid image path {cap.image_path}")
  ```

---

### [detect.py:646, 685](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L646)
- **Severity**: Medium
- **Relevant Code**:
  ```python
  self.model = Predictor(model=str(weights), ...)
  self.model = YOLO(str(weights))
  ```
- **Failure Scenario**: Arbitrary code execution via pickle deserialization in PyTorch `.pt` model files. If `SENTINEL_DETECTOR_MODEL` or the model storage directory is writable by untrusted users, loading a crafted `.pt` weight file executes arbitrary Python code.
- **Suggested Fix**:
  Ensure model weight directories have strict permissions (0700/0600) and validate file checksums before loading.

---

## 3. Deprecated APIs / Outdated Patterns

### [worker.py:33](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L33) & [track.py:29](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/track.py#L29)
- **Severity**: Medium
- **Relevant Code**:
  ```python
  days = (when - type(when)(2000, 1, 6, 18, 14)).total_seconds() / 86400
  ```
- **Issue**: Non-standard naive datetime construction. Mixing naive and aware datetimes breaks in Python 3.11+. Standardize on explicit `timezone.utc` across the pipeline.
- **Suggested Fix**:
  Use `datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)` and ensure input timestamps are timezone-aware UTC.

---

## 4. Inconsistencies

### [detect.py:657](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L657) vs [detect.py:274, 717](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L274)
- **Severity**: Medium
- **Relevant Code**:
  ```python
  # BaselineDetector (detect.py:274)
  kept = on_card(boxes, outline, CARD_EDGE_MM * self.last["px_per_mm"])

  # YoloDetector (detect.py:717)
  merge_fragments(on_card([Box(*found[i]) for i in merge_tiles(found, tiles)], outline, CARD_EDGE_MM * (ppm or 0)))

  # FlatbugDetector (detect.py:657)
  return on_card(found, outline)
  ```
- **Failure Scenario**: Inconsistent detector behavior. `BaselineDetector` and `YoloDetector` discard boxes within `CARD_EDGE_MM` (4 mm) of the liner edge to prevent false positives from clips and shadows, and apply `merge_fragments()`. `FlatbugDetector` omits the margin entirely (`margin_px = 0.0`) and never runs `merge_fragments()`, resulting in false positives on trap clips and duplicate fragmented boxes.
- **Suggested Fix**:
  Apply uniform card margin exclusion and fragment merging across all three detector implementations.

---

### [detect.py:646, 692, 720-726](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L646)
- **Severity**: Low
- **Relevant Code**:
  ```python
  # FlatbugDetector (detect.py:646)
  device="mps:0" if _has_mps() else "cpu"

  # YoloDetector (detect.py:692)
  self.device = "mps" if _has_mps() else "cpu"
  ```
- **Failure Scenario**: Device selection discrepancy and lack of CUDA support. If deployed on Linux/CUDA servers, both detectors silently fall back to slow CPU inference because they only check for Apple Silicon MPS.
- **Suggested Fix**:
  Implement a unified device resolution helper:
  ```python
  def get_device() -> str:
      if torch.cuda.is_available():
          return "cuda:0"
      if torch.backends.mps.is_available():
          return "mps"
      return "cpu"
  ```

---

## 5. Dead Code, Duplication & Module Coupling

### [detect.py:24-49](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L24-L49) vs [track.py:32-38](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/track.py#L32-L38)
- **Severity**: Low
- **Relevant Code**:
  `detect.py` defines `Box(x1, y1, x2, y2, conf, n)` while `track.py` defines `Rect(x1, y1, x2, y2)`.
  In `worker.py:138-139, 236`:
  ```python
  rects = [trk.Rect(t.x1, t.y1, t.x2, t.y2) for t in live]
  det_rects = [trk.Rect(b.x1, b.y1, b.x2, b.y2) for b in boxes]
  ```
- **Issue**: Redundant data models causing repetitive conversion loops in `worker.py`. `trk.iou` and `trk.centre_close` only require attributes `x1, y1, x2, y2`.
- **Suggested Fix**:
  Consolidate into a single bounding box class or support duck typing protocol across `detect.py`, `track.py`, and `worker.py`.

---

### [detect.py:421](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L421)
- **Severity**: Low
- **Relevant Code**:
  ```python
  def _rotate(a: np.ndarray, angle: float, size: tuple[int, int] | None = None, inverse_of=None) -> np.ndarray:
  ```
- **Issue**: Unused parameter `size`. It is never referenced in `_rotate()`.
- **Suggested Fix**:
  Remove `size` parameter from the signature.

---

### [detect.py:223](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L223)
- **Severity**: Low
- **Relevant Code**:
  ```python
  self.bg_object_mm = bg_object_mm  # background estimate looks past dark things up to this size  # no grid found: assume the liner spans the image width
  ```
- **Issue**: Mangled inline comment combining two separate comments into one line.
- **Suggested Fix**:
  Move `# no grid found: assume the liner spans the image width` to line 222 (`self.fallback_liner_mm`).

---

## 6. Performance & Optimization Opportunities

### [worker.py:77-90](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L77-L90)
- **Severity**: Medium
- **Relevant Code**:
  ```python
  boxes = self.detector.detect(path, key=(cap.trap_id, cap.card_id))
  ...
  bgr = cv2.imread(str(path))
  ...
  with Image.open(path) as img:
      w, h = img.size
  ...
  with Image.open(found["path"]) as img:
      return self.classifier.classify([crop(img, b) for b in found["boxes"]])
  ```
- **Issue**: Repeated disk reads and image decodings. For an 8 MP capture, `path` is opened and read 3 to 4 times within a single pipeline pass (`detector.detect`, `cv2.imread(str(path))`, `Image.open(path)`, and `Image.open(found["path"])`).
- **Suggested Fix**:
  Read and decode the image once into memory, passing the image array/object to detection, quality checks, and classification.

---

### [detect.py:662, 700](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L662)
- **Severity**: Medium
- **Relevant Code**:
  ```python
  ppm, grid = photo_scale(img, self.grid_mm, self.lens)
  ```
- **Issue**: Uncached lens calibration search in `YoloDetector`. `photo_scale` runs `estimate_lens_k(img)` on every capture when `lens == "auto"`. `BaselineDetector` caches lens distortion estimates per liner via `_lens_cache`, but `YoloDetector` lacks caching and recalculates the full search grid on every capture, adding multiple seconds of CPU overhead per photo.
- **Suggested Fix**:
  Pass `key` to `photo_scale` and cache the lens parameter in `YoloDetector`.

---

### [worker.py:158-159](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L158-L159)
- **Severity**: Low
- **Relevant Code**:
  ```python
  db.add(t)
  db.flush()
  ```
- **Issue**: `db.flush()` inside the per-box loop. If a card has 60 detections, 60 separate flush roundtrips are executed within the SQLite transaction.
- **Suggested Fix**:
  Use SQLAlchemy relationships (`Detection(track=t, ...)`) so all objects can be flushed together in a single batch.

---

## 7. Test Coverage Gaps

1. **`detect.py:634, 669`**: Both `FlatbugDetector` and `YoloDetector` are explicitly flagged `# pragma: no cover`. No unit or integration tests exist verifying box parsing, tile merging, or scale transformations for either production ML detector.
2. **`worker.py:188-205` (`reprocess_card`)**: Zero tests exercising `reprocess_card` with pre-existing reviewed tracks, allowing the cumulative counter duplication bug to go unnoticed.
3. **`worker.py:224-243` (`_keep_liner_if_unchanged`)**: Lack of unit tests verifying behaviour when accidental card swaps are detected and undone.
4. **`detect.py:539-540` (`_agreed_pitch`)**: Lack of test cases where pitch candidates are `< 12.0` px, which triggers the empty `max()` crash.
5. **Timezone consistency**: No unit tests verifying `moon_illumination` or `fresh()` with timezone-aware `datetime` objects.

---

## Prioritized Next Steps

1. **Fix `moon_illumination` timezone crash**: Patch [worker.py:33](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L33) to prevent crashes on offset-aware capture timestamps.
2. **Fix `reprocess_card` state accumulation**: Reset tracking accumulators (`n_seen`, `n_classified`, `prob_sum`, `misses`) in [worker.py:198-204](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L198-L204) when reprocessing liners with reviewed tracks.
3. **Fix empty sequence crash in `_agreed_pitch`**: Add a fallback before calling `max(cands)` in [detect.py:539-540](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L539-L540).
4. **Sanitize media paths**: Wrap `media_dir / cap.image_path` with `.resolve()` and verify path containment in [worker.py:77](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L77) to prevent directory traversal.
5. **Harmonize detector pipelines**: Standardize card edge margin exclusion, fragment merging, and lens caching across `BaselineDetector`, `FlatbugDetector`, and `YoloDetector`.
