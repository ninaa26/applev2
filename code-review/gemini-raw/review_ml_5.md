 empty?
As noted earlier, if `share == 1.0`, `share > 0.92` short-circuits.
What if `inside == 0` has pixels, but `sat[inside == 0]` mean is `< 0.5`?
Then it returns `None`.
WAIT! What if `cv2.findNonZero((lab == biggest).astype(np.uint8))` returns `None`?
Wait! In OpenCV:
If the image passed to `cv2.findNonZero` has NO non-zero pixels, `cv2.findNonZero` returns `None`!
Can `(lab == biggest)` have no non-zero pixels?
Since `biggest` is the component with max area in `stats[1:, CC_STAT_AREA]`, and `n >= 2`, could `stats[biggest, CC_STAT_AREA]` be 0?
In `connectedComponentsWithStats`, background is label 0. Labels 1 to `n-1` are connected components.
Every connected component has at least 1 pixel (area >= 1).
So `lab == biggest` always has at least 1 non-zero pixel.
BUT WHAT IF it has only 1 or 2 pixels?
If `(lab == biggest)` has only 1 or 2 pixels:
`cv2.findNonZero` returns an array of shape `(1, 1, 2)` or `(2, 1, 2)`.
`cv2.convexHull` returns that 1 or 2 point array.
Now line 79:
`cv2.fillConvexPoly(inside, hull, 1)`
In OpenCV, `fillConvexPoly` with 1 or 2 points does NOTHING or can crash / throw an OpenCV assertion error depending on version!
Wait! Can `lab == biggest` have only 1 or 2 pixels?
Look at line 72:
`pale = cv2.morphologyEx(pale, cv2.MORPH_OPEN, np.ones((15, 15), np.uint8))`
An opening with a 15x15 kernel eliminates any connected component smaller than 15x15!
So any surviving component must be at least 15x15 = 225 pixels.
So `stats[biggest, CC_STAT_AREA] >= 225`.
So it cannot be 1 or 2 pixels. That's safe.

WAIT! LOOK AT LINE 297-304 in `detect.py`:
```python
step = max(0.5, float(np.degrees(np.arctan(2.5 * px_per_mm * 0.8 / length))))
full = []
for base in grid.angles:
    fam = np.zeros_like(dark)
    for angle in np.arange(base - 15, base + 15 + 1e-6, step):
        fam = np.maximum(fam, line_opening(dark, float(angle), length))
    full.append(fam)
```
Wait! Look at `line_opening`:
`for angle in np.arange(base - 15, base + 15 + 1e-6, step):`
`    fam = np.maximum(fam, line_opening(dark, float(angle), length))`
How many angles are there per `base`?
Spread is 30 degrees. If `step` is 0.5 degrees, there are 61 angles!
For 2 grid angles: $61 \times 2 = 122$ rotations!
And inside `line_opening`:
Line 440: `rot = _rotate(dark, angle)` (affine warp)
Line 441: `opened = cv2.morphologyEx(...)`
Line 447: `return _rotate(opened, angle, inverse_of=dark.shape)` (second affine warp!)
So each angle does TWO full image affine warps and morphology!
For 122 angles, that is $122 \times 2 = 244$ full affine warps!
On a Raspberry Pi CPU or edge device, 244 full-resolution affine warps takes significant time (tens of seconds).
And look at lines 314-315:
```python
for base in grid.angles:
    for angle in np.arange(base - 15, base + 15 + 1e-6, step):
        thin = np.maximum(thin, line_opening(dark, float(angle), length, thick))
```
It runs the EXACT SAME loop of angles a SECOND TIME with `thick`!
Another 122 angles $\times$ 2 affine warps = 244 more affine warps!
Total ~500 full image affine warps in `_detect` for a single photo!
This is a massive performance bottleneck on CPU!
Why not combine the two passes (thin and thick) in the same loop, avoiding 122 redundant `_rotate(dark, angle)` calls?
In line 440, `rot = _rotate(dark, angle)` is computed twice for every angle: once in the first loop (line 302) and once in the second loop (line 315)!

WAIT! Look at line 415 in `detect.py`:
```python
def darkness(v: np.ndarray, object_px: int) -> np.ndarray:
    """0 on bare liner, towards 1 for dark things; divides out vignetting and uneven light."""
    h, w = v.shape
    s = max(1.0, max(h, w) / 320)  # estimate the background at low resolution: fast with big kernels
    small = cv2.resize(v, (max(8, int(w / s)), max(8, int(h / s))), interpolation=cv2.INTER_AREA)
    k = max(3, int(1.5 * object_px / s) | 1)
    bg = cv2.morphologyEx(small, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
    bg = cv2.GaussianBlur(bg, (0, 0), k / 4)
    bg = cv2.resize(bg, (w, h), interpolation=cv2.INTER_LINEAR)
    return np.clip(1.0 - v / np.maximum(bg, 1.0), 0, 1)
```
Wait! Look at `cv2.GaussianBlur(bg, (0, 0), k / 4)`:
In OpenCV: `cv2.GaussianBlur(src, ksize, sigmaX, sigmaY)`.
When `ksize = (0, 0)`, OpenCV computes kernel size from `sigmaX = k / 4`.
Wait! What if `k / 4 <= 0`?
`k >= 3`, so `k / 4 >= 0.75 > 0`. That's valid.

WAIT! Let's check `_camera` in `detect.py`:
Line 572-574:
```python
def _camera(w: int, h: int) -> np.ndarray:
    f = 0.5 * float(np.hypot(w, h))
    return np.array([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]], np.float64)
```
Line 580:
`cam = _camera(w, h)`
`m1, m2 = cv2.initUndistortRectifyMap(cam, np.array([k, 0, 0, 0], np.float64), None, cam, (w, h), cv2.CV_32FC1)`
Wait! `np.array([k, 0, 0, 0], np.float64)`:
In OpenCV distortion coefficients:
Standard distortion vector is `(k1, k2, p1, p2[, k3[, k4, k5, k6]])`.
Passing `[k, 0, 0, 0]` means $k_1 = k, k_2 = 0, p_1 = 0, p_2 = 0$.
That matches the docstring: "One-parameter radial model (OpenCV's k1)".

WAIT! Let's check `distort_points`:
Line 586-591:
```python
def distort_points(pts: np.ndarray, k: float, w: int, h: int) -> np.ndarray:
    """Straightened-photo pixel coordinates (N×2) -> where they are in the original photo."""
    f = 0.5 * float(np.hypot(w, h))
    c = np.array([w / 2, h / 2])
    n = (np.asarray(pts, np.float64) - c) / f
    r2 = (n ** 2).sum(axis=1, keepdims=True)
    return n * (1 + k * r2) * f + c
```
Wait! Look at `distort_points`:
If `k < 0` (barrel distortion, wide-angle lens):
Is `distort_points` inverting the undistortion, or is it applying distortion?
Let's trace:
In `undistort`:
OpenCV's `initUndistortRectifyMap(cam, distCoeffs, R, newCam, size, m1type)`:
For each pixel in the destination (undistorted) image $(u', v')$:
It computes normalized ray: $x' = (u' - c_x)/f_x, y' = (v' - c_y)/f_y$.
Then it applies distortion to find where this ray came from in the source (distorted) image:
$x_{dist} = x' (1 + k_1 r'^2)$
$y_{dist} = y' (1 + k_1 r'^2)$
$u_{dist} = f_x x_{dist} + c_x = (u' - c_x)(1 + k_1 r'^2) + c_x$.
And `remap` samples source pixel $(u_{dist}, v_{dist})$ and places it at $(u', v')$.
So destination pixel $(u', v')$ in the undistorted image corresponds to source pixel $(u_{dist}, v_{dist})$ in the distorted image!
Now: `_detect(undistort(img, k))` finds a box in the undistorted image.
The coordinates of this box are $(u', v')$ in the undistorted image!
Now we want to know: where was this box in the original distorted photo?
The answer is $(u_{dist}, v_{dist}) = (u' - c_x)(1 + k_1 r'^2) + c_x$!
Which is EXACTLY what `distort_points` computes!
So `distort_points` maps from undistorted photo coordinates back to original distorted photo coordinates. That is mathematically exact.

WAIT! Look at line 598 in `distort_box`:
`return Box(float(max(0, p[:, 0].min())), float(max(0, p[:, 1].min())), float(min(w, p[:, 0].max())), float(min(h, p[:,
# Code Review: Chunk 6 of 6
**Scope:** `server/sentinel_server/pipeline/detect.py`, `server/sentinel_server/pipeline/track.py`, `server/sentinel_server/pipeline/worker.py` (and interface with `ml/`).

---

## 1. Bugs

### 1.1 Timezone Mismatch Crash in `moon_illumination`
- **File & Line:** [worker.py:33](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L33)
- **Severity:** High
- **Code:**
  ```python
  days = (when - type(when)(2000, 1, 6, 18, 14)).total_seconds() / 86400
  ```
- **Concrete Failure Scenario:** If `cap.captured_at` is timezone-aware (e.g., UTC from standard datetime parsers or aware DB column), `type(when)(2000, 1, 6, 18, 14)` instantiates an offset-naive `datetime`. In Python, subtracting offset-naive from offset-aware raises `TypeError: can't subtract offset-naive and offset-aware datetimes`, which aborts photo processing for every capture in `process()`.
- **Suggested Fix:** Preserve `tzinfo` from `when`:
  ```python
  base = datetime(2000, 1, 6, 18, 14, tzinfo=when.tzinfo)
  days = (when - base).total_seconds() / 86400
  ```

---

### 1.2 Empty Sequence Crash in `_agreed_pitch`
- **File & Line:** [detect.py:539-540](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L539-L540)
- **Severity:** High
- **Code:**
  ```python
  cands = {p / k for p in pitches for k in range(1, 5) if p / k >= 12}
  return max(cands, key=prominence)
  ```
- **Concrete Failure Scenario:** `_period` accepts lags down to `min_lag=6`. If `pitches` contains measured pitches under 12 px (e.g. `[7.0, 10.0]`) and `max(pitches) > (1 + tol) * min(pitches)`, all `p / k <= 10.0 < 12`, so the comprehension produces an empty set `set()`. Calling `max(set(), ...)` immediately raises `ValueError: max() arg is an empty sequence` and crashes detection.
- **Suggested Fix:** Fallback to the median pitch if `cands` is empty:
  ```python
  cands = {p / k for p in pitches for k in range(1, 5) if p / k >= 12}
  return max(cands, key=prominence) if cands else float(np.median(pitches))
  ```

---

### 1.3 State Accumulation & Double Counting on Reviewed Tracks in `reprocess_card`
- **File & Line:** [worker.py:198-204](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L198-L204)
- **Severity:** High
- **Code:**
  ```python
  for t in db.scalars(select(Track).where(Track.card_id == card_id)):
      if not t.reviewed:  # people's labels and rejections are kept (and reviews point at them)
          db.delete(t)
  db.flush()
  for c in caps:
      self.process(db, c, check_liner=False, found=found[c.id])
  ```
- **Concrete Failure Scenario:** When a card is reprocessed (triggered manually or automatically upon receiving out-of-order captures via `_process_in_order`), unreviewed tracks are deleted, but reviewed tracks are retained. However, the retained tracks are not reset: their existing `n_seen`, `n_classified`, and `prob_sum` remain in place. As `self.process` loops through `caps`, matched reviewed tracks re-increment `t.n_seen += 1`, `t.n_classified += 1`, and add probabilities to `t.prob_sum`. After reprocessing, the counts and probability sums on reviewed tracks are doubled.
- **Suggested Fix:** Reset accumulator fields on reviewed tracks prior to reprocessing:
  ```python
  for t in db.scalars(select(Track).where(Track.card_id == card_id)):
      if not t.reviewed:
          db.delete(t)
      else:
          t.n_seen = 0
          t.n_classified = 0
          t.prob_sum = {}
          t.misses = 0
  ```

---

### 1.4 Stale Card ID and Desynchronization in `_keep_liner_if_unchanged`
- **File & Line:** [worker.py:130, 238-243](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L130-L135), [worker.py:238-243](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L238-L243)
- **Severity:** High
- **Code:**
  ```python
  if same_liner_as_before(old, boxes):
      n = len(trk.match(old, boxes))
      log.info("capture %s: %d of %d insects from liner %s still in place, not a new liner", cap.id, n, len(old), before.id)
      services.undo_new_card(db, card, f"{n} of {len(old)} insects from the last photo are still in place "
                                       "(battery swap or accidental button press?)")
  ```
- **Concrete Failure Scenario:** When `same_liner_as_before` detects that a button press was accidental, `services.undo_new_card(db, card, ...)` is called. In Python memory, `cap.card_id` remains set to the undone card ID (and `db.refresh(cap)` is never called). `process()` continues immediately to line 133:
  ```python
  live = list(db.scalars(select(Track).where(Track.card_id == cap.card_id, ...)))
  ```
  `live` is queried against the undone card (returning empty), and line 154 creates new `Track(card_id=cap.card_id, ...)`, linking detections to the deleted card or violating foreign key constraints. All previous insects are re-created as new tracks, defeating the exact purpose of `undo_new_card`.
- **Suggested Fix:** Return whether the card was undone, reload `cap`, and reassign `cap.card_id = before.id`:
  ```python
  if _keep_liner_if_unchanged(db, cap, [trk.Rect(b.x1, b.y1, b.x2, b.y2) for b in boxes]):
      db.refresh(cap)
  ```

---

### 1.5 Edge Fragment Preferred Over Whole Insect in `merge_tiles`
- **File & Line:** [detect.py:165-177](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L165-L177)
- **Severity:** Medium
- **Code:**
  ```python
  order = sorted(range(len(boxes)), key=lambda i: -boxes[i][4])
  kept: list[int] = []
  for i in order:
      a = boxes[i]
      for j in kept:
          ...
          smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
          if smaller > 0 and ix * iy / smaller > thr:
              break
      else:
          kept.append(i)
  ```
- **Concrete Failure Scenario:** When an insect lies across tile borders, one tile contains a truncated edge sliver and the adjacent tile contains the whole insect. If the truncated sliver happens to have a marginally higher detector confidence score (e.g. 0.85 vs 0.84), it is processed first into `kept`. When the full box `a` is evaluated, `smaller` is the fragment area; `ix * iy / smaller > 0.5` causes `a` to be discarded. Downstream classification receives only the cut-off fragment.
- **Suggested Fix:** When merging overlapping tile detections, update the retained box geometry to enclose the larger/union boundary (analogous to `merge_fragments`).

---

### 1.6 Worker Race Condition Under Concurrent Processing
- **File & Line:** [worker.py:264-273](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L264-L273)
- **Severity:** Medium
- **Code:**
  ```python
  with session_scope() as db:
      ids = list(db.scalars(select(Capture.id).where(Capture.status == "new").order_by(Capture.captured_at).limit(limit)))
  for cid in ids:
      with session_scope() as db:
          cap = db.get(Capture, cid)
          if cap is not None and cap.status == "new":
              _process_in_order(pipeline, db, cap)
  ```
- **Concrete Failure Scenario:** `cap.status` remains `"new"` throughout the entire detection and classification stages (which take tens of seconds to minutes). If two worker threads or processes execute `process_pending`, both pick up the same capture ID and run detection/tracking concurrently, creating duplicate `Track` and `Detection` records.
- **Suggested Fix:** Transition `status` atomically to `"processing"` upon acquisition in the database before invoking `_process_in_order`.

---

### 1.7 Missing Corrupted Image Guard in `FlatbugDetector.detect`
- **File & Line:** [detect.py:655](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L655)
- **Severity:** Low
- **Code:**
  ```python
  outline = card_outline(cv2.imread(str(image_path)))
  ```
- **Concrete Failure Scenario:** Unlike `BaselineDetector.detect` and `YoloDetector.detect` which explicitly check `if img is None: raise ValueError(...)`, `FlatbugDetector` passes `cv2.imread(...)` directly to `card_outline`. If an image is unreadable or truncated, `card_outline(None)` immediately raises `AttributeError: 'NoneType' object has no attribute 'shape'`.
- **Suggested Fix:** Add `img = cv2.imread(str(image_path)); if img is None: raise ValueError(...)` before calling `card_outline(img)`.

---

## 2. Security Issues

### 2.1 Unsanitized Image Path Traversal
- **File & Line:** [worker.py:77](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L77)
- **Severity:** Medium
- **Code:**
  ```python
  path = get_settings().media_dir / cap.image_path
  ```
- **Concrete Failure Scenario:** If an uploaded capture payload specifies `image_path` containing path traversal sequences (e.g., `../../etc/passwd` or relative paths outside `media_dir`), `path.resolve()` escapes the intended storage directory and causes the server to open and process arbitrary image files on the host filesystem.
- **Suggested Fix:** Resolve and verify that the target path is strictly within `media_dir`:
  ```python
  path = (get_settings().media_dir / cap.image_path).resolve()
  if not path.is_relative_to(get_settings().media_dir.resolve()):
      raise ValueError("Invalid image path")
  ```

---

## 3. Deprecated APIs & Outdated Patterns

### 3.1 Deprecated `datetime.utcnow()` Pattern
- **File & Line:** [worker.py:17, 111, 185](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L17)
- **Severity:** Low
- **Code:**
  ```python
  from ..models import Capture, Card, Detection, Event, Track, Trap, utcnow
  ...
  cap.status, cap.processed_at, cap.model_version = "failed", utcnow(), self.version
  ```
- **Concrete Failure Scenario:** If `utcnow()` wraps `datetime.utcnow()`, this emits `DeprecationWarning` in Python 3.12+ and produces offset-naive datetimes, exacerbating the offset-naive vs offset-aware comparisons noted in finding 1.1.
- **Suggested Fix:** Standardize on timezone-aware UTC via `datetime.now(timezone.utc)`.

---

### 3.2 Omission of CUDA in Device Selection
- **File & Line:** [detect.py:646, 692, 720-726](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L720-L726)
- **Severity:** Low
- **Code:**
  ```python
  def _has_mps() -> bool:
      try:
          import torch
          return torch.backends.mps.is_available()
      except Exception:
          return False
  ...
  self.device = "mps" if _has_mps() else "cpu"
  ```
- **Concrete Failure Scenario:** On any Linux or Windows server with NVIDIA GPUs, `_has_mps()` returns `False`. The detector defaults to `"cpu"`, completely ignoring available CUDA acceleration.
- **Suggested Fix:**
  ```python
  def _default_device() -> str:
      import torch
      if torch.cuda.is_available():
          return "cuda"
      if torch.backends.mps.is_available():
          return "mps"
      return "cpu"
  ```

---

## 4. Inconsistencies & Contract Mismatches

### 4.1 YOLO Detector Classes Completely Ignored by Server Pipeline
- **File & Line:** [detect.py:675, 712-714](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L675)
- **Severity:** Medium
- **Code:**
  ```python
  # detect.py:675:
  # Its classes (moth / other insect / debris) are not passed on: every box goes to the classifier, which has the last word.
  for (x1, y1, x2, y2), c in zip(r.boxes.xyxy.cpu().tolist(), r.boxes.conf.cpu().tolist()):
      found.append(((x1 + ox) / s, (y1 + oy) / s, (x2 + ox) / s, (y2 + oy) / s, float(c)))
  ```
- **Concrete Failure Scenario:** `ml/train_yolo.py` trains a 3-class model (`moth`, `other_insect`, `debris`). If YOLO identifies a box as `debris` with 0.95 confidence, `YoloDetector.detect` extracts only `conf` and coordinates, discarding class prediction. The debris is treated as an insect detection and forwarded to the species classifier and tracker, introducing false tracks.
- **Suggested Fix:** Filter out or penalize boxes predicted by YOLO as `debris` before passing to the classifier.

---

### 4.2 Merged Comments Typo
- **File & Line:** [detect.py:223](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L223)
- **Severity:** Low
- **Code:**
  ```python
  self.bg_object_mm = bg_object_mm  # background estimate looks past dark things up to this size  # no grid found: assume the liner spans the image width
  ```
- **Finding:** Two separate inline comments were accidentally concatenated onto line 223. The second comment was meant for line 222 (`fallback_liner_mm`).

---

## 5. Dead Code & Architecture

### 5.1 Unused Parameter in `_rotate`
- **File & Line:** [detect.py:421](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L421)
- **Severity:** Low
- **Code:**
  ```python
  def _rotate(a: np.ndarray, angle: float, size: tuple[int, int] | None = None, inverse_of=None) -> np.ndarray:
  ```
- **Finding:** Parameter `size` is never used inside `_rotate`.

---

### 5.2 Redundant Disk I/O and Decoding
- **File & Line:** [worker.py:77-88](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L77-L88)
- **Severity:** Low
- **Finding:** A single image is read and decoded up to 4 times per capture: once in `detector.detect()`, once in `worker._detect()` via `cv2.imread()`, once in `worker._detect()` via `Image.open()`, and again in `worker._classify()` via `Image.open()`.

---

## 6. Performance Opportunities

### 6.1 Duplicate Full-Image Affine Warps in `BaselineDetector`
- **File & Line:** [detect.py:299-318](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L299-L318)
- **Severity:** Medium
- **Finding:** `_detect()` iterates through angles around grid directions twice: lines 299–303 (computing `lines`) and lines 314–315 (computing `thin`). Each call to `line_opening` executes two full `cv2.warpAffine` operations. For two axes across $\pm 15^\circ$ with $0.5^\circ$ step, this executes nearly 500 affine transforms per photo. Combining both morphology operations inside a single rotation loop eliminates ~250 affine transforms.

---

### 6.2 Missing Lens Distortion Estimation Cache in `YoloDetector`
- **File & Line:** [detect.py:700](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L700), [detect.py:660-666](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L660-L666)
- **Severity:** Medium
- **Finding:** While `BaselineDetector` caches `k` per liner key (`self._lens_cache[key]`), `YoloDetector.detect()` calls `photo_scale()`, which invokes `estimate_lens_k(img)` anew for every photo when `lens="auto"`. `estimate_lens_k` evaluates dozens of undistort passes, adding seconds of CPU latency per photo.

---

## 7. Test Coverage Gaps

1. **Short Grid Pitches:** Unit tests for `_agreed_pitch` with pitch estimates $< 12$ px.
2. **Reprocessing Card Consistency:** Test `reprocess_card()` on a card with both reviewed and unreviewed tracks to verify counts do not double.
3. **Card Undo Sequence:** Test `_keep_liner_if_unchanged()` returning True and ensure all subsequent capture processing attaches to the existing liner card.
4. **Timezone Compatibility:** Test `photo_quality` and `moon_illumination` with UTC timezone-aware datetime stamps.

---

## Prioritized Next Steps

1. **Immediate Patch:** Fix `moon_illumination` datetime subtraction ([worker.py:33](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L33)) and empty sequence check in `_agreed_pitch` ([detect.py:539](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/detect.py#L539)) to prevent unhandled runtime crashes.
2. **Data Integrity Patch:** Reset `n_seen`, `n_classified`, and `prob_sum` on reviewed tracks in `reprocess_card()` ([worker.py:198](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L198)).
3. **Workflow Fix:** In `Pipeline.process()`, check the outcome of `_keep_liner_if_unchanged()` and reload/reassign `cap.card_id` before querying live tracks ([worker.py:130](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/worker.py#L130)).
4. **Performance Optimization:** Cache `lens_k` in `YoloDetector` and combine the two angle rotation loops in `BaselineDetector`.
