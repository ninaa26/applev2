# Code Review: `ml/` (Chunk 2 of 6)

Files in scope:
- [ml/crop_field_cards.py](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/crop_field_cards.py)
- [ml/eval_detector_combine.py](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_detector_combine.py)
- [ml/eval_detector_roboflow.py](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_detector_roboflow.py)
- [ml/eval_field_cards.py](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_field_cards.py)
- [ml/eval_liner_species.py](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_liner_species.py)
- [ml/export_server_crops.py](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/export_server_crops.py)
- [ml/fetch_ami.py](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/fetch_ami.py)

---

## 1. Bugs

### [export_server_crops.py:63-80](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/export_server_crops.py#L63-L80)
- **Severity**: High
- **Issue**: Unbounded in-memory image cache causing Out-Of-Memory (OOM) crash.
- **Code**:
  ```python
  63|     images: dict[str, Image.Image] = {}
  64|     for det, x1, y1, x2, y2, image_path, trap, installed, status, reviewed in db.execute(q):
  ...
  78|         if image_path not in images:
  79|             with Image.open(args.server / "media" / image_path) as im:
  80|                 images[image_path] = im.convert("RGB")
  ```
- **Failure Scenario**: Unlike `crop_field_cards.py:167` which retains only one photo in memory (`images = {r["photo"]: ...}`), `export_server_crops.py` accumulates every referenced capture image in `images`. Full-resolution trap images (typically 12 MP ~ 36 MB uncompressed RGB) across hundreds or thousands of captures will consume tens of gigabytes of RAM, crashing the export script with `MemoryError`.
- **Suggested Fix**: Clear or limit the image cache, or sort query `q` by `c.image_path` and keep only the active image in memory:
  ```python
  q = """SELECT ... FROM ... ORDER BY c.image_path"""
  current_path, current_im = None, None
  for det, x1, y1, x2, y2, image_path, ... in db.execute(q):
      if image_path != current_path:
          current_path = image_path
          with Image.open(args.server / "media" / image_path) as im:
              current_im = im.convert("RGB")
  ```

---

### [eval_detector_roboflow.py:163](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_detector_roboflow.py#L163)
- **Severity**: High
- **Issue**: File descriptor leak inside loop causing `OSError: [Errno 24] Too many open files`.
- **Code**:
  ```python
  163|         json.dump(done, open(cache, "w"))  # after every photo: flatbug on a full-size photo takes a while
  ```
- **Failure Scenario**: On every processed image, `open(cache, "w")` creates a new unclosed file descriptor. In datasets containing several hundred images, this rapidly exhausts the OS file descriptor limit (default `ulimit -n` is 256 or 1024 on macOS/Linux), terminating the run before finishing.
- **Suggested Fix**: Use a `with` statement:
  ```python
  with open(cache, "w") as f:
      json.dump(done, f)
  ```

---

### [eval_field_cards.py:42-44](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_field_cards.py#L42-L44)
- **Severity**: High
- **Issue**: `coarse()` fails to map head predicted moth classes (`CM`, `OFM`, `OBLR`, `other_moth`) to `"moth"`, corrupting confusion matrix and recall.
- **Code**:
  ```python
  42| def coarse(label: str) -> str:
  43|     return "moth" if label == "moth" or CLASS_OF.get(label) in MOTH_CLASSES else label
  ```
- **Failure Scenario**: `eval_field_cards.py:150` passes predictions from the head through `coarse()` before evaluating against `COARSE = ["moth", "other_insect", "debris"]`. The head outputs species classes (e.g. `CM`, `OFM`). When `label == "CM"`, `label == "moth"` is `False`. Because `CLASS_OF` from `build_dataset.py` maps raw input labels to targets rather than providing an identity mapping for canonical classes, `CLASS_OF.get("CM")` returns `None`. Thus, `coarse("CM")` returns `"CM"`. In `table()`, `"CM"` is not in `labels` (`COARSE`), so all correctly predicted moths are dropped from the counts, reporting near-zero recall and invalid accuracy.
- **Suggested Fix**: Directly check membership in `MOTH_CLASSES`:
  ```python
  def coarse(label: str) -> str:
      return "moth" if label == "moth" or label in MOTH_CLASSES or CLASS_OF.get(label) in MOTH_CLASSES else label
  ```

---

### [fetch_ami.py:118-120](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/fetch_ami.py#L118-L120)
- **Severity**: High
- **Issue**: Multiple images for the same GBIF occurrence overwrite each other and are skipped as cached.
- **Code**:
  ```python
  118|     dest = out / row["label"] / f"{row['id']}.jpg"
  119|     if dest.exists():
  120|         return "cached", str(dest)
  ```
- **Failure Scenario**: In the GBIF occurrence dataset used by AMI, `row['id']` is the occurrence ID (manifest line 156 maps `row['id']` to `gbif_occurrence`). An individual occurrence record often includes multiple photographs (different angles, dorsal vs. ventral). Because destination filenames are keyed solely to `row['id']`, the first image downloaded writes `{id}.jpg`. Subsequent photos with different `identifier` URLs evaluate `dest.exists()` to `True` and are skipped as `"cached"`, silently dropping training samples.
- **Suggested Fix**: Disambiguate destination filenames using a hash of `identifier` or an image index:
  ```python
  import hashlib
  url_hash = hashlib.md5(row["identifier"].encode("utf-8")).hexdigest()[:8]
  dest = out / row["label"] / f"{row['id']}_{url_hash}.jpg"
  ```

---

### [eval_detector_roboflow.py:241-242](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_detector_roboflow.py#L241-L242) and [eval_detector_combine.py:132](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_detector_combine.py#L132)
- **Severity**: Medium
- **Issue**: Unhandled `ZeroDivisionError` when a photo subgroup has 0 ground-truth annotations.
- **Code**:
  In `eval_detector_roboflow.py`:
  ```python
  241|                         lines.append(f"| {ds} · {group} | {name}{conf} | {tag} | {len(sub)} | {tot_gt} | "
  242|                                      f"**{tot_found / tot_gt:.0%}** | {tot_used / max(1, tot_det):.0%} | "
  243|                                      f"{count_det / tot_gt:.2f} | {med} |")
  ```
  In `eval_detector_combine.py`:
  ```python
  132|                     lines.append(f"| {ds} · {group} ({len(sub)} photos, {n_gt} moths) | {tag} | {s} | "
  133|                                  f"**{tot[s][0] / n_gt:.0%}** | {lost:+d} | {tot[s][1] / len(sub):.1f} |"
  ```
- **Failure Scenario**: If an evaluation partition consists of empty/blank liners or unannotated control photos where `tot_gt == 0` or `n_gt == 0`, `tot_found / tot_gt` and `tot[s][0] / n_gt` raise `ZeroDivisionError: division by zero`. While `tot_det` is guarded by `max(1, tot_det)`, ground truth is not.
- **Suggested Fix**: Guard against zero division:
  ```python
  recall_str = f"{tot_found / tot_gt:.0%}" if tot_gt else "N/A"
  ratio_str = f"{count_det / tot_gt:.2f}" if tot_gt else "N/A"
  ```

---

### [export_server_crops.py:43-44, 64-65](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/export_server_crops.py#L43-L44)
- **Severity**: Medium
- **Issue**: `card_name` crashes with `TypeError` if `cards.installed_at` is `NULL`.
- **Code**:
  ```python
  43| def card_name(trap: str, installed_at: str) -> str:
  44|     return f"{trap}-{datetime.fromisoformat(installed_at):%Y%m%dT%H%M}"
  ...
  64|     for det, x1, y1, x2, y2, image_path, trap, installed, status, reviewed in db.execute(q):
  65|         card = card_name(trap, installed)
  ```
- **Failure Scenario**: If any card in SQLite has a `NULL` `installed_at` field, `installed` is passed as `None`. `datetime.fromisoformat(None)` raises `TypeError: fromisoformat: argument must be str`.
- **Suggested Fix**: Handle `None` gracefully:
  ```python
  def card_name(trap: str, installed_at: str | None) -> str:
      if not installed_at:
          return f"{trap}-uninstalled"
      return f"{trap}-{datetime.fromisoformat(installed_at):%Y%m%dT%H%M}"
  ```

---

### [eval_field_cards.py:129-136](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_field_cards.py#L129-L136)
- **Severity**: Low
- **Issue**: Zero division if `r["ppm"]` parses to `0.0`.
- **Code**:
  ```python
  129|         small = [trap_res(c, float(r["ppm"]), args.trap_ppm, Path(tmp) / f"{k}.jpg") if r["ppm"] else c
  ...
  50|         s = trap_ppm / ppm
  ```
- **Failure Scenario**: If `r["ppm"]` is formatted as `"0.00"` in `labels.csv`, `bool(r["ppm"])` is `True` because the string is non-empty. In `trap_res`, `ppm = float("0.00") = 0.0`, resulting in `s = trap_ppm / 0.0` and raising `ZeroDivisionError`.
- **Suggested Fix**: Guard condition with `if float(r["ppm"]) > 0`:
  ```python
  small = [trap_res(c, float(r["ppm"]), args.trap_ppm, Path(tmp) / f"{k}.jpg") if r["ppm"] and float(r["ppm"]) > 0 else c for k, (r, c) in enumerate(zip(rows, crops))]
  ```

---

## 2. Security Issues

### [eval_field_cards.py:103](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_field_cards.py#L103)
- **Severity**: Medium
- **Issue**: Missing `allow_pickle=False` on `np.load()`.
- **Code**:
  ```python
  103|     head = np.load(args.head)
  ```
- **Failure Scenario**: In contrast to `eval_liner_species.py:107` which specifies `np.load(h, allow_pickle=False)`, `eval_field_cards.py` omits `allow_pickle=False`. Loading a modified or untrusted `.npz` file can trigger arbitrary code execution during deserialization.
- **Suggested Fix**: Add `allow_pickle=False`:
  ```python
  head = np.load(args.head, allow_pickle=False)
  ```

---

### [fetch_ami.py:124-126](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/fetch_ami.py#L124-L126)
- **Severity**: Low
- **Issue**: Unvalidated remote response written directly as `.jpg`.
- **Code**:
  ```python
  124|         with urllib.request.urlopen(urllib.request.Request(row["identifier"], headers=UA), timeout=30) as r:
  125|             dest.write_bytes(r.read())
  ```
- **Failure Scenario**: GBIF media URLs often experience link rot where servers respond with HTTP 200 OK returning HTML error pages ("File Not Found", CDN challenge pages, portal redirects). `dest.write_bytes` blindly writes raw HTML text into `.jpg` files. Downstream image readers fail with `UnidentifiedImageError` when trying to decode the corrupted images.
- **Suggested Fix**: Validate image magic bytes before saving:
  ```python
  data = r.read()
  if not (data.startswith(b"\xff\xd8\xff") or data.startswith(b"\x89PNG")):
      return "failed: invalid image payload", ""
  dest.write_bytes(data)
  ```

---

## 3. Deprecated APIs & Outdated Patterns

### [crop_field_cards.py:240, 260](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/crop_field_cards.py#L240) and [eval_detector_roboflow.py:85](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_detector_roboflow.py#L85)
- **Severity**: Medium
- **Issue**: Hardcoded device fallback ignores NVIDIA CUDA.
- **Code**:
  ```python
  240|         predictor = Predictor(model=args.weights, device="mps:0" if torch.backends.mps.is_available() else "cpu",
  241|                               dtype="float32")
  ```
- **Failure Scenario**: When running on a Linux GPU server (e.g. AWS/GCP or a training rig with NVIDIA GPUs), `torch.backends.mps.is_available()` evaluates to `False`. The code falls back to `cpu`, completely ignoring available CUDA acceleration and slowing down detector tiling by 20x–50x.
- **Suggested Fix**: Support CUDA, MPS, and CPU:
  ```python
  if torch.cuda.is_available():
      device = "cuda:0"
  elif torch.backends.mps.is_available():
      device = "mps:0"
  else:
      device = "cpu"
  ```

---

### [crop_field_cards.py:175](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/crop_field_cards.py#L175)
- **Severity**: Low
- **Issue**: Deprecated Pillow resampling constant `Image.LANCZOS`.
- **Code**:
  ```python
  175|         region = region.resize((round(region.width * up), round(region.height * up)), Image.LANCZOS)
  ```
- **Failure Scenario**: `Image.LANCZOS` is deprecated in modern Pillow in favor of `Image.Resampling.LANCZOS`.
- **Suggested Fix**: Replace with `Image.Resampling.LANCZOS`.

---

## 4. Inconsistencies

### [crop_field_cards.py:189, 276-278](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/crop_field_cards.py#L189)
- **Severity**: Medium
- **Issue**: Cutout naming convention diverges between `main()` and `fill_cutouts()`.
- **Code**:
  In `main()`:
  ```python
  276|             name = f"{p.stem}_{n:02d}"
  ...
  278|             cut_path = args.data / "cutouts" / f"{name}.png"
  ```
  In `fill_cutouts()`:
  ```python
  189|         dest = data / "cutouts" / f"{Path(r['photo']).stem}_{r['n']}{'m' if r['source'] == 'manual' else 'e'}.png"
  ```
- **Failure Scenario**: Initial cutouts in `main()` use 2-digit zero-padding without suffix (e.g. `card1_01.png`), whereas `fill_cutouts()` generates unpadded filenames with source suffixes (e.g. `card1_1m.png` or `card1_1e.png`). In downstream scripts like `eval_field_cards.py:109` that parse cutout stems via `rsplit("_", 1)[0]`, this divergence causes pattern matching mismatches.
- **Suggested Fix**: Align filename construction across both paths using `int(r['n']):02d`.

---

### [fetch_ami.py:36-42](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/fetch_ami.py#L36-L42) vs [export_server_crops.py:33](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/export_server_crops.py#L33)
- **Severity**: Medium
- **Issue**: Discrepancy between AMI fetch target classes and server/evaluation target labels.
- **Code**:
  In `fetch_ami.py`:
  ```python
  36| TARGETS = {
  37|     "1737847": "CM",                 # Cydia pomonella
  38|     "1736574": "OFM",                # Grapholita molesta (iNaturalist: Aspila molesta)
  39|     "5102671": "OBLR",               # Choristoneura rosaceana
  40|     "10457666": "lookalike_LAW",     # Grapholita prunivora, lesser appleworm
  41|     "1747189": "lookalike_RBLR",     # Argyrotaenia velutinana, redbanded leafroller
  42| }
  ```
  In `export_server_crops.py`:
  ```python
  33| LABELS = {"CM", "OFM", "OBLR", "other_moth", "other_insect", "debris"}
  ```
- **Failure Scenario**: `fetch_ami.py` saves images into `data/ami/lookalike_LAW` and `data/ami/lookalike_RBLR`. However, `export_server_crops.py`, `eval_field_cards.py:38`, and `eval_liner_species.py:38` only know `{"CM", "OFM", "OBLR", "other_moth"}`. Without an explicit rule in `build_dataset.py` mapping these lookalikes into `other_moth`, lookalikes are orphaned or cause dataset schema mismatches.
- **Suggested Fix**: Document whether lookalike classes should be folded into `other_moth` or maintained as negative eval classes.

---

### [eval_detector_combine.py:98](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_detector_combine.py#L98)
- **Severity**: Low
- **Issue**: Hardcoded `"8ppm"` resolution tag in `eval_detector_combine.py`.
- **Code**:
  ```python
  98|         for tag in ["native", "8ppm"]:
  ```
- **Failure Scenario**: `eval_detector_roboflow.py` allows `--trap-ppm` to be set to any arbitrary float (e.g. 7.0 for webcam, 15.0 for Camera Module 3), naming cache files `{ds}__{name}__{ppm:g}ppm.json`. If a user runs `eval_detector_roboflow.py --trap-ppm 15`, `eval_detector_combine.py` fails to locate the cache because `"8ppm"` is hardcoded and `--trap-ppm` is not configurable via CLI.
- **Suggested Fix**: Add `--trap-ppm` argument to `eval_detector_combine.py` (default 8.0) and use `[tag, f"{args.trap_ppm:g}ppm"]`.

---

## 5. Dead Code, Duplication & Organization Problems

### [crop_field_cards.py:49-53](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/crop_field_cards.py#L49-L53), [eval_field_cards.py:59-63](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_field_cards.py#L59-L63), and [export_server_crops.py:37-40](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/export_server_crops.py#L37-L40)
- **Severity**: Low
- **Issue**: Duplicated padded box crop logic and hardcoded constants across three scripts.
- **Code**:
  ```python
  PAD = 0.35
  def crop(img: Image.Image, x1, y1, x2, y2, pad=PAD):
      side = max(x2 - x1, y2 - y1) * (1 + 2 * pad)
      cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
      return img.crop((int(cx - side / 2), int(cy - side / 2), int(cx + side / 2), int(cy + side / 2)))
  ```
- **Failure Scenario**: If server crop padding is modified in `server/sentinel_server/pipeline/classify.py`, having three separate copies in `ml/` risks silent divergence between the training crop dimensions and inference crop dimensions.
- **Suggested Fix**: Consolidate `server_crop` and `PAD` into a shared `ml/utils.py` or import directly from `sentinel_server.pipeline.classify`.

---

### [eval_detector_combine.py:126-128](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_detector_combine.py#L126-L128)
- **Severity**: Low
- **Issue**: Redundant re-computation of `match()`.
- **Code**:
  ```python
  122|                     for s, dets in zip(steps, [b, s2, s4, fb, s3, s1]):
  123|                         found, used = match(im["gt"], dets, args.iou)
  ...
  126|                     if tag == "native":
  127|                         found, used = match(im["gt"], s4, args.iou)
  128|                         overlay(im, s4, found, used, ev / "overlays_combined" / f"{ds}__{im['path'].stem[:40]}.jpg")
  ```
- **Failure Scenario**: In the loop over steps, `match(im["gt"], s4, args.iou)` is already evaluated when `s == "+ flatbug"`. At line 127 it is run a second time for every native image.
- **Suggested Fix**: Retain `found, used` when `s == "+ flatbug"` and reuse for `overlay()`.

---

## 6. Performance & Optimization Opportunities

### [crop_field_cards.py:111-116](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/crop_field_cards.py#L111-L116)
- **Severity**: Medium
- **Issue**: Full image duplication on every insect cutout.
- **Code**:
  ```python
  111| def cutout(img: Image.Image, contour: np.ndarray, box) -> Image.Image:
  112|     mask = Image.new("L", img.size, 0)
  113|     ImageDraw.Draw(mask).polygon([(float(x), float(y)) for x, y in contour], fill=255)
  114|     rgba = img.copy()
  115|     rgba.putalpha(mask)
  116|     return rgba.crop(box)
  ```
- **Failure Scenario**: High-resolution card photos are 12–24 MP. For each insect (often 20–50 per card), `cutout()` clones the entire full-resolution RGB image to RGBA (48–96 MB RAM) and generates a full-resolution mask, only to immediately crop down to a small box (~100x100 px).
- **Suggested Fix**: Crop first, then mask inside bounding box coordinates:
  ```python
  def cutout(img: Image.Image, contour: np.ndarray, box) -> Image.Image:
      x1, y1, x2, y2 = box
      cropped = img.crop(box).convert("RGBA")
      mask = Image.new("L", (x2 - x1, y2 - y1), 0)
      ImageDraw.Draw(mask).polygon([(float(x - x1), float(y - y1)) for x, y in contour], fill=255)
      cropped.putalpha(mask)
      return cropped
  ```

---

### [eval_detector_roboflow.py:150, 168, 204](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_detector_roboflow.py#L204)
- **Severity**: Medium
- **Issue**: Triple decoding of image files from disk.
- **Code**:
  Line 204:
  ```python
  ppm_of = {im["path"].name: grid_px_per_mm(cv2.imread(str(im["path"])), args.grid_mm) for im in images}
  ```
  Line 150:
  ```python
  img = cv2.imread(str(im["path"]))
  ```
  Line 168:
  ```python
  img = cv2.imread(str(im["path"]))
  ```
- **Failure Scenario**: Images are read from disk and decompressed up to three times: once in the list comprehension to calculate scale, once in `detect_all`, and once in `overlay`. On large datasets with hundreds of full-resolution images, this adds substantial redundant disk I/O and CPU decompression latency.
- **Suggested Fix**: Compute `ppm` lazily inside `detect_all` or cache the decoded images/scales in the cached metadata dictionary.

---

## 7. Test Coverage Gaps

1. **`HttpFile` range request seek/read logic ([fetch_ami.py:46-77](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/fetch_ami.py#L46-L77))**:
   - `HttpFile` implements custom seekable raw I/O over HTTP Range headers (`read`, `readinto`, `seek`). There are zero unit tests validating boundary edge cases, EOF handling, or non-206 HTTP responses.
2. **Clump box matching logic ([eval_detector_roboflow.py:119-138](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_detector_roboflow.py#L119-L138))**:
   - `match()` handles multi-insect clumps (`cap > 1` and `mutual` center inclusion). There are no unit tests verifying whether greedy matching by confidence accurately assigns detections to ground-truth boxes or properly respects clump capacity limits.
3. **Classification label folding ([eval_field_cards.py:42-44](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_field_cards.py#L42-L44))**:
   - `coarse()` has no automated tests, allowing the missing `label in MOTH_CLASSES` bug to pass unnoticed.

---

## Prioritized Next Steps

1. **Fix `eval_field_cards.py:coarse()`**: Update `coarse()` to explicitly verify `label in MOTH_CLASSES` so all moth species predictions are properly grouped into `"moth"`.
2. **Fix file descriptor leaks and OOM caching**:
   - Enclose `json.dump` inside a `with open(...)` block in [ml/eval_detector_roboflow.py:163](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_detector_roboflow.py#L163).
   - In [ml/export_server_crops.py](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/export_server_crops.py), stream and evict images instead of keeping every capture in memory.
3. **Fix GBIF occurrence ID collision in [ml/fetch_ami.py:118](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/fetch_ami.py#L118)**: Append a URL hash to destination paths to prevent multi-photo occurrences from skipping valid training images.
4. **Guard against `ZeroDivisionError`**: Add `max(1, tot_gt)` and `max(1, n_gt)` in [ml/eval_detector_roboflow.py](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_detector_roboflow.py) and [ml/eval_detector_combine.py](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/eval_detector_combine.py).
5. **Support CUDA detection**: Update device detection in `crop_field_cards.py` and `eval_detector_roboflow.py` to prioritize `cuda:0` when available.
