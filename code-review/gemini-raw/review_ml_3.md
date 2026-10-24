# Code Review: Chunk 4 of 6 (`ml/` & tests)

## 1. Bugs (Correctness, Crashes, Data Leakage, Resource Leaks)

---

### `ml/make_trap_style.py:259` & `ml/make_trap_style.py:269`
- **Severity**: Critical
- **Category**: Data Leakage / Train-Test Split Contamination
- **Code Quote**:
  ```python
  259|         manifest.append({"path": str(dest), "label": r["label"], "source_path": r["path"], **meta})
  ...
  269|         manifest.append({"path": str(dest), "label": "debris", "source_path": "", **meta})
  ```
- **Concrete Failure Scenario**:
  `FIELDS` defined on line 69 explicitly includes `"group"`:
  ```python
  69| FIELDS = ["path", "label", "source_path", "liner", "ppm", "length_mm", "group"]
  ```
  And lines 23–24 docstrings state:
  > *"Each synthetic photo inherits its source photo's group (so its split), which keeps a moth and its pasted copies on the same side of the train/test line."*
  
  However, in `main()`, `manifest.append(...)` on lines 259 and 269 **completely omits `"group"`** when creating synthetic moth and bare-liner crops. Because `csv.DictWriter(..., restval="")` is used (line 202), `"group"` is written as an empty string `""` for all synthetic web-photo moth crops. When `build_dataset.py` creates dataset splits, it cannot group these pasted copies together. Multiple jittered/rescaled synthetic copies of the exact same insect cutout (`_0.jpg`, `_1.jpg`, etc.) get split across **both train and test/val sets**. This introduces direct data leakage, yielding artificially high test accuracy and deceptive evaluation metrics that fail in field traps.
- **Suggested Fix**:
  Preserve and write the source group (from `r["group"]` or fallback to `Path(r["path"]).stem`):
  ```python
  group = r.get("group") or Path(r["path"]).stem
  manifest.append({"path": str(dest), "label": r["label"], "source_path": r["path"], "group": group, **meta})
  ```
  And assign a distinct group for bare liner crops:
  ```python
  manifest.append({"path": str(dest), "label": "debris", "source_path": "", "group": f"liner:{meta['liner']}", **meta})
  ```

---

### `ml/make_trap_style.py:230`, `244`
- **Severity**: High
- **Category**: Unhandled KeyError / Crash
- **Code Quote**:
  ```python
  230|         cut = [r for r in csv.DictReader(f) if r["status"] == "ok" and r["label"] in LENGTH_MM]
  ...
  244|             labels_in[CLASS_OF[label]] += 1
  ```
- **Concrete Failure Scenario**:
  Line 230 filters `r["label"] in LENGTH_MM`, but does not verify `r["label"] in CLASS_OF`. In contrast, `field_jobs()` on line 174 correctly checks `r["label"] in CLASS_OF`. If `cutouts/manifest.csv` contains any label present in `LENGTH_MM` (e.g. `lookalike_LAW`, `other_tortricid`, `bycatch_lacewing`) that is not mapped in `build_dataset.CLASS_OF`, line 244 will immediately raise an unhandled `KeyError` and crash the script during photo generation.
- **Suggested Fix**:
  Filter for membership in both `LENGTH_MM` and `CLASS_OF`:
  ```python
  cut = [r for r in csv.DictReader(f) if r["status"] == "ok" and r["label"] in LENGTH_MM and r["label"] in CLASS_OF]
  ```

---

### `ml/make_trap_style.py:188`
- **Severity**: High
- **Category**: Unhandled ValueError / Crash on Field Card Data
- **Code Quote**:
  ```python
  188|             measured = float(r["length_mm"]) if r["length_mm"] else None
  ```
- **Concrete Failure Scenario**:
  In field card annotation spreadsheets, missing or unmeasured dimensions are commonly denoted with `"-"`, `"?"`, or whitespace. While line 174 checks `r["cutout"] not in ("", "-")`, line 188 only checks truthiness (`if r["length_mm"]`). If `r["length_mm"]` contains `"-"` or `"?"`, `float("-")` raises `ValueError: could not convert string to float: '-'`, terminating `make_trap_style.py --field`.
- **Suggested Fix**:
  Safely parse `length_mm`:
  ```python
  raw_len = r.get("length_mm", "").strip()
  measured = float(raw_len) if raw_len and raw_len not in ("-", "?", "none") else None
  ```

---

### `ml/model_playground.py:52`
- **Severity**: Medium
- **Category**: KeyError Crash on Summary Metrics
- **Code Quote**:
  ```python
  52|             "info": (f"{what} mAP50 {m['mAP50']:.2f} (moth {m['per_class_mAP50'].get('moth', 0):.2f})"
  53|                      if m else "still training (using its best epoch so far)"),
  ```
- **Concrete Failure Scenario**:
  If a trained YOLO run's `summary.json` has `m = info["test"]` or `val` without the `"per_class_mAP50"` key (e.g. runs evaluated with a single combined class or earlier evaluation scripts), accessing `m['per_class_mAP50']` raises `KeyError: 'per_class_mAP50'`. When the browser calls GET `/api/models`, the request crashes with 500 error, breaking the playground UI. Furthermore, if trained using `one_insect_class()` (where class is `"insect"`), `m['per_class_mAP50'].get('moth', 0)` always displays `0.00`.
- **Suggested Fix**:
  Use safe dictionary lookups:
  ```python
  per_class = m.get("per_class_mAP50", {})
  cls_name = "moth" if "moth" in per_class else ("insect" if "insect" in per_class else next(iter(per_class), ""))
  cls_str = f" ({cls_name} {per_class[cls_name]:.2f})" if cls_name else ""
  "info": (f"{what} mAP50 {m.get('mAP50', 0):.2f}{cls_str}"
           if m else "still training (using its best epoch so far)"),
  ```

---

### `ml/segment_moths.py:92-97`
- **Severity**: Medium
- **Category**: CSV Corruption on Interrupted First Run
- **Code Quote**:
  ```python
  92|     new = not manifest.exists()
  93|     t0 = time.time()
  94|     with open(manifest, "a", newline="") as f:
  95|         w = csv.DictWriter(f, fieldnames=FIELDS)
  96|         if new:
  97|             w.writeheader()
  ```
- **Concrete Failure Scenario**:
  If an initial run of `segment_moths.py` creates `data/cutouts/manifest.csv` but is interrupted (SIGINT or exception) before writing any rows, a 0-byte file remains. On the next invocation, `manifest.exists()` is `True`, so `new` is `False`. The script appends data without writing a header row. When `load_done()` (line 30) runs subsequently:
  ```python
  30|     with open(manifest, newline="") as f:
  31|         return {r["path"]: r for r in csv.DictReader(f)}
  ```
  `csv.DictReader` treats the first data row as the column headers. The first cutout is permanently lost from index lookups and field mappings become corrupted.
- **Suggested Fix**:
  Check if the file does not exist or is empty:
  ```python
  new = not manifest.exists() or manifest.stat().st_size == 0
  ```

---

### `ml/recover_roboflow_originals.py:40-41`, `54-55`
- **Severity**: High
- **Category**: OpenCV Crash on Missing/Corrupted Images
- **Code Quote**:
  ```python
  40|         origs = sorted((root / "roboflow_orig" / s).glob("*.jpg"))
  41|         o_img = {p: cv2.imread(str(p)) for p in origs}
  42|         o_thumb = {p: thumb(im) for p, im in o_img.items()}
  ...
  54|                 e = cv2.imread(str(j.parent / im["file_name"]))
  55|                 et = thumb(e)
  ```
- **Concrete Failure Scenario**:
  If any original or export file is truncated, missing, or corrupt, `cv2.imread()` returns `None`. `thumb()` (line 33) immediately passes `None` to `cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)`, crashing with:
  `cv2.error: OpenCV(4.x) :-1: error: (-5:Bad argument) in function 'cvtColor'`.
  In addition, if `origs` is empty, `min(...)` on line 56 crashes with `ValueError: min() arg is an empty sequence`.
- **Suggested Fix**:
  Verify images loaded successfully:
  ```python
  o_img = {p: im for p in origs if (im := cv2.imread(str(p))) is not None}
  if not o_img:
      print(f"Skipping {s}: no readable original images")
      continue
  ...
  e = cv2.imread(str(j.parent / im["file_name"]))
  if e is None:
      continue
  ```

---

### `ml/make_trap_style.py:222` & `ml/recover_roboflow_originals.py:47`, `75`
- **Severity**: High
- **Category**: Resource Leaks / Unclosed File Descriptors
- **Code Quote**:
  ```python
  # make_trap_style.py:222
  old = list(csv.DictReader(open(manifest_path, newline=""))) if manifest_path.exists() else []

  # recover_roboflow_originals.py:47 & 75
  coco = json.load(open(j))
  ...
  json.dump({"images": images, "annotations": anns, "categories": cats},
            open(out_dir / "_annotations.coco.json", "w"))
  ```
- **Concrete Failure Scenario**:
  Files are opened using bare `open(...)` without context managers or `.close()`. The file handles remain open until garbage collection. In `recover_roboflow_originals.py:75`, unbuffered writes to disk may not flush properly if an exception occurs immediately after, and unclosed write descriptors risk file truncation.
- **Suggested Fix**:
  Always use `with open(...) as f:` blocks.

---

## 2. Security Issues

---

### `ml/model_playground.py:203`
- **Severity**: High
- **Category**: Unbounded Request Body / Denial of Service (DoS)
- **Code Quote**:
  ```python
  203|         data = self.rfile.read(int(self.headers.get("Content-Length", 0)))
  ```
- **Concrete Failure Scenario**:
  The HTTP POST endpoint `/api/run` reads the entire payload directly into memory using the client-supplied `Content-Length` without any size check. An attacker or accidental multi-gigabyte upload (e.g. 4GB) will cause Python to allocate a massive buffer, triggering an Out-Of-Memory (OOM) kill of the server process.
- **Suggested Fix**:
  Enforce a sensible maximum upload limit (e.g. 50 MB):
  ```python
  MAX_UPLOAD_BYTES = 50 * 1024 * 1024
  length = int(self.headers.get("Content-Length", 0))
  if length > MAX_UPLOAD_BYTES:
      return self.send_json({"error": "Payload too large (max 50 MB)"}, 413)
  data = self.rfile.read(length)
  ```

---

### `ml/model_playground.py:210`, `96`, `103`
- **Severity**: Medium
- **Category**: Unvalidated Input / Crash via Invalid `ppm`
- **Code Quote**:
  ```python
  210|             ppm = float(q["ppm"]) if q.get("ppm") else None
  ...
  103|         scale = min(1.0, run["ppm"] / ppm) if ppm else 1.0
  104|         small = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS) if scale < 1 else img
  ```
- **Concrete Failure Scenario**:
  If a user passes `ppm=0` or a negative value via query params, `scale` becomes negative or triggers a `ZeroDivisionError`. When negative, `img.resize((round(img.width * scale), ...))` crashes with `ValueError: height and width must be > 0`. If `q["ppm"]` is non-numeric, `float()` raises `ValueError`, resulting in an unhandled 500 error.
- **Suggested Fix**:
  Validate `ppm` to be strictly positive:
  ```python
  try:
      ppm = float(q["ppm"]) if q.get("ppm") else None
      if ppm is not None and ppm <= 0:
          ppm = None
  except ValueError:
      return self.send_json({"error": "Invalid ppm value"}, 400)
  ```

---

## 3. Deprecated APIs / Outdated Patterns

---

### `ml/make_trap_style.py:93`, `96`, `117`, `119`, `120`, `160` & `ml/model_playground.py:104`
- **Severity**: Low
- **Category**: Deprecated Pillow 10+ Constants
- **Code Quote**:
  ```python
  # make_trap_style.py
  93|     patch = Image.fromarray(...).resize((side, side), Image.BILINEAR)
  96|         patch = patch.transpose(Image.FLIP_LEFT_RIGHT)
  117|     moth = cutout.resize(..., Image.LANCZOS)
  119|         moth = moth.transpose(Image.FLIP_LEFT_RIGHT)
  120|     moth = moth.rotate(..., resample=Image.BICUBIC, expand=True)
  160|             out.paste(im.convert("RGB").resize((cell, cell), Image.NEAREST), ...)

  # model_playground.py
  104|         small = img.resize(..., Image.LANCZOS) if scale < 1 else img
  ```
- **Concrete Failure Scenario**:
  `ml/requirements.txt` pins `pillow>=10.0`. In Pillow 10.0, top-level constants `Image.BILINEAR`, `Image.NEAREST`, `Image.BICUBIC`, `Image.LANCZOS`, and `Image.FLIP_LEFT_RIGHT` are deprecated in favor of `Image.Resampling.*` and `Image.Transpose.*`. Running with warnings enabled produces deprecation warnings, and newer Pillow releases will raise `AttributeError`.
- **Suggested Fix**:
  Replace with modern enums: `Image.Resampling.BILINEAR`, `Image.Resampling.LANCZOS`, `Image.Resampling.BICUBIC`, `Image.Resampling.NEAREST`, and `Image.Transpose.FLIP_LEFT_RIGHT`.

---

## 4. Inconsistencies

---

### `ml/model_playground.py:115` vs `ml/segment_moths.py:88`
- **Severity**: High
- **Category**: CUDA Device Exclusion / Performance Inconsistency
- **Code Quote**:
  ```python
  # model_playground.py:115
  115|         device = "mps" if torch.backends.mps.is_available() else "cpu"

  # segment_moths.py:88
  88|     device = "mps:0" if torch.backends.mps.is_available() else "cuda:0" if torch.cuda.is_available() else "cpu"
  ```
- **Concrete Failure Scenario**:
  Per `ml/requirements-train.txt` and `RUN_ON_CUDA.md`, training and inference machines run on Linux with NVIDIA CUDA GPUs. However, `model_playground.py` checks only MPS and CPU, completely ignoring CUDA. When hosted on a CUDA GPU machine, `model_playground.py` forces PyTorch/YOLO to run on CPU, slowing multi-tile inference from 100ms to 5–10 seconds per image.
- **Suggested Fix**:
  Detect CUDA first:
  ```python
  device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
  ```

---

### `ml/make_trap_style.py:73`
- **Severity**: Low
- **Category**: Type Annotation Inconsistency
- **Code Quote**:
  ```python
  73| def load_liners(folder: Path) -> list[np.ndarray]:
  74|     liners = []
  75|     for p in sorted(folder.glob("*.jpg")) + sorted(folder.glob("*.png")):
  76|         with Image.open(p) as im:
  77|             liners.append((p.name, np.asarray(im.convert("RGB"), dtype=np.float32)))
  ```
- **Concrete Failure Scenario**:
  The return type annotation is `list[np.ndarray]`, but the function returns a list of 2-tuples: `list[tuple[str, np.ndarray]]`. Static type checkers (mypy/pyright) report type errors across `liner_patch` call sites.
- **Suggested Fix**:
  Update annotation to `list[tuple[str, np.ndarray]]`.

---

## 5. Dead Code, Duplication & Module Coupling

---

### `ml/tests/test_train_yolo.py:98-99`
- **Severity**: Low
- **Category**: Redundant Statement in Teardown
- **Code Quote**:
  ```python
  98|                 ty.CLASSES, ty.MERGE = classes, merge
  99|                 ty.MERGE.clear(); ty.MERGE.update(merge)
  ```
- **Concrete Failure Scenario**:
  Line 98 assigns `ty.MERGE = merge`, and line 99 immediately clears and updates `ty.MERGE`. Line 98's assignment of `ty.MERGE` is redundant dead code.
- **Suggested Fix**:
  Simplify to:
  ```python
  ty.CLASSES = classes
  ty.MERGE.clear()
  ty.MERGE.update(merge)
  ```

---

## 6. Performance & Optimization Opportunities

---

### `ml/recover_roboflow_originals.py:40-42`, `62`
- **Severity**: Medium
- **Category**: Excessive RAM Consumption
- **Code Quote**:
  ```python
  40|         origs = sorted((root / "roboflow_orig" / s).glob("*.jpg"))
  41|         o_img = {p: cv2.imread(str(p)) for p in origs}
  42|         o_thumb = {p: thumb(im) for p, im in o_img.items()}
  ...
  62|                 h, w = o_img[best].shape[:2]
  ```
- **Concrete Failure Scenario**:
  `o_img` loads every full-resolution original image into memory at once. For hundreds of 12–24 MP camera trap photos (each 36–72 MB in RAM uncompressed), holding all full images in memory requires 20–40+ GB of RAM, risking an OOM crash. The full image in `o_img[best]` is never used except to read `shape[:2]` on line 62.
- **Suggested Fix**:
  Store only thumbnails and image dimensions `(h, w)` in memory; discard the full decoded image immediately:
  ```python
  o_thumb, o_dims = {}, {}
  for p in origs:
      im = cv2.imread(str(p))
      if im is not None:
          o_dims[p] = im.shape[:2]
          o_thumb[p] = thumb(im)
  ...
  h, w = o_dims[best]
  ```

---

### `ml/make_trap_style.py:107`
- **Severity**: Medium
- **Category**: Generator Allocation in Tight Loop
- **Code Quote**:
  ```python
  107|     a = a + np.random.default_rng(rng.randrange(1 << 30)).normal(0, rng.uniform(1.5, 7.0), a.shape)
  ```
- **Concrete Failure Scenario**:
  `degrade()` is called inside the loop generating 50,000+ crops. Calling `np.random.default_rng(...)` on every crop causes 50,000 allocations of NumPy `PCG64` bit generators, creating measurable CPU overhead during synthetic dataset generation.
- **Suggested Fix**:
  Instantiate a single NumPy Generator outside the loop or reuse an existing instance.

---

## 7. Test Coverage Gaps

---

### `ml/tests/test_trap_style.py`
- **Severity**: High
- **Category**: Missing Test Coverage for Manifest & Grouping Logic
- **Details**:
  `test_trap_style.py` tests `paste_moth`, `liner_patch`, and `export_server_crops`, but has **zero tests** for `main()` or `make_field()` manifest generation, group propagation, or `CLASS_OF` validation. This allowed the critical `group` data-leakage bug in `make_trap_style.py:259` to slip through undetected.
- **Suggested Fix**:
  Add a unit test creating synthetic crops from a dummy cutout manifest, asserting that every row in `synth/manifest.csv` contains a valid, non-empty `group` matching the source observation.

---

### `ml/tests/test_train_v2.py:20-33`
- **Severity**: High
- **Category**: Severe Test Coverage Gap for v2 Classifier
- **Details**:
  `test_train_v2.py` only tests the `MixRes` augmentation transform. There are no tests for:
  - Dataset loading and split separation in `train_v2`
  - Model forward pass and loss computation
  - Exported `head.npz` structure (keys: `W`, `b`, `classes`, `model`, `T`), classes ordering, and temperature scaling
- **Suggested Fix**:
  Add unit tests running a fast forward/backward pass with synthetic embeddings/images and verifying the exported `.npz` head dictionary matches what `sentinel_server.pipeline.classify` and `model_playground.py:Head` expect.

---

## Prioritized Next Steps

1. **Fix Dataset Leakage in `ml/make_trap_style.py:259`**: Assign source `group` to all generated synthetic crops in `manifest.append()` to ensure pasted copies of the same cutout do not cross the train/val/test boundary.
2. **Prevent Generation Crashes in `ml/make_trap_style.py`**:
   - Filter `r["label"] in CLASS_OF` on line 230 to prevent `KeyError` during copy calculation.
   - Safely parse `length_mm` on line 188 to avoid crashes on non-numeric or empty string tokens.
3. **Enable CUDA in `ml/model_playground.py:115`**: Add `torch.cuda.is_available()` check before falling back to CPU so inference on Linux servers uses GPU acceleration.
4. **Secure `ml/model_playground.py:203`**: Enforce a maximum upload size (e.g. 50 MB) and validate `ppm > 0`.
5. **Expand Test Suites**:
   - Add unit tests in `test_trap_style.py` asserting non-empty group assignment in `synth/manifest.csv`.
   - Add unit tests in `test_train_v2.py` verifying `head.npz` export structure and label alignment.
