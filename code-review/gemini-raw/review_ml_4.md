## Orchard Sentinel Code Review — Chunk 5 of 6
**Scope**: `ml/train_v1.py`, `ml/train_v2.py`, `ml/train_yolo.py`, `server/sentinel_server/models.py`, `server/sentinel_server/pipeline/__init__.py`, `server/sentinel_server/pipeline/classify.py`.

---

### 1. BUGS (Correctness, Crashes, Data Loss, Resource Leaks, Error Handling)

#### [ml/train_v1.py:208, 215] — Variable Shadowing Causes Unconditional Crash on `--final`
- **Severity**: Critical
- **Code Quote**:
  ```python
  193|     T = embedder.texts([PROMPTS[c] for c in classes])
  ...
  207|         if best is None or score > best[1]:
  208|             best = (C, score, fit_temperature(clf.decision_function(X[tune]), y[tune]))
  209|     C, _, T = best
  ...
  214|     if args.final and lk.any():
  215|         results["v0 zero-shot · LOCKED own cards"] = report(y[lk], (X[lk] @ T.T).argmax(1), classes)
  ```
- **Failure Scenario**:
  At line 193, `T` stores the 2D BioCLIP text embeddings array. At line 208, `C, _, T = best` overwrites `T` with a scalar `float` (the temperature scaling parameter). When `python train_v1.py --final` is executed to evaluate the locked test cards (`lk.any() == True`), line 215 evaluates zero-shot accuracy using `(X[lk] @ T.T).argmax(1)`. Because `T` is now a `float`, accessing `T.T` raises `AttributeError: 'float' object has no attribute 'T'`. If `T` is a NumPy scalar, matrix multiplication `@` with 0-D operand fails with `ValueError: matmul: Input operand 1 does not have enough dimensions`. Running `--final` crashes every time.
- **Suggested Fix**:
  Rename the text embedding matrix to `text_features` and keep `temperature` separate:
  ```python
  text_features = embedder.texts([PROMPTS[c] for c in classes])
  ...
  results[f"v0 zero-shot · {name}"] = report(y[m], (X[m] @ text_features.T).argmax(1), classes)
  ...
  C, _, temperature = best
  ...
  if args.final and lk.any():
      results["v0 zero-shot · LOCKED own cards"] = report(y[lk], (X[lk] @ text_features.T).argmax(1), classes)
  ```

---

#### [server/sentinel_server/pipeline/classify.py:86-92] — Binary Classification Head Output Dimension Mismatch
- **Severity**: High
- **Code Quote**:
  ```python
  88|     logits = (feats @ W.T + b) / T
  89|     logits -= logits.max(axis=1, keepdims=True)
  90|     p = np.exp(logits)
  91|     p /= p.sum(axis=1, keepdims=True)
  92|     return [{s: float(row[classes.index(s)]) if s in classes else 0.0 for s in SPECIES} for row in p]
  ```
- **Failure Scenario**:
  In `scikit-learn`, `LogisticRegression` for a 2-class problem produces `coef_` of shape `(1, n_features)` and `intercept_` of shape `(1,)`. If `train_v1.py` is trained on a 2-class dataset (e.g. during early data collection or binary target experiments), `feats @ W.T + b` is 1D per sample (`shape (N, 1)`). Line 89 reduces `logits` to zero (`logits -= logits.max()`), resulting in `p = [[1.0], ...]`. Then at line 92, for the second class (`classes.index(s) == 1`), `row[1]` raises `IndexError: index 1 is out of bounds for axis 0 with size 1`.
- **Suggested Fix**:
  Detect 1D binary outputs in `linear_head_probs`:
  ```python
  if W.shape[0] == 1 and len(classes) == 2:
      # Binary logistic regression output
      prob_pos = 1.0 / (1.0 + np.exp(-((feats @ W.T + b) / T)))
      p = np.hstack([1.0 - prob_pos, prob_pos])
  else:
      logits = (feats @ W.T + b) / T
      logits -= logits.max(axis=1, keepdims=True)
      p = np.exp(logits)
      p /= p.sum(axis=1, keepdims=True)
  ```

---

#### [ml/train_v2.py:192-196] — Crash in SequentialLR When `steps <= 2`
- **Severity**: High
- **Code Quote**:
  ```python
  192|     steps = args.epochs * len(train_loader)
  193|     warm = min(len(train_loader), steps // 2)
  194|     sched = torch.optim.lr_scheduler.SequentialLR(opt, milestones=[warm], schedulers=[
  195|         torch.optim.lr_scheduler.LinearLR(opt, start_factor=0.05, total_iters=warm),
  196|         torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(1, steps - warm))])
  ```
- **Failure Scenario**:
  If `train_v2.py` is executed with `--epochs 1` on a dataset or batch size where `len(train_loader) == 1` (common in quick verification runs and CI smoke tests), `steps = 1`, and `steps // 2` is `0`. Consequently, `warm = 0`. In PyTorch, `torch.optim.lr_scheduler.LinearLR` asserts `total_iters > 0`, raising `ValueError: total_iters must be greater than 0`.
- **Suggested Fix**:
  Guard warmup configuration:
  ```python
  warm = min(len(train_loader), steps // 2)
  if warm > 0:
      sched = torch.optim.lr_scheduler.SequentialLR(opt, milestones=[warm], schedulers=[
          torch.optim.lr_scheduler.LinearLR(opt, start_factor=0.05, total_iters=warm),
          torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(1, steps - warm))])
  else:
      sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(1, steps))
  ```

---

#### [ml/train_yolo.py:150-151] — ZeroDivisionError on Uncalibrated Photo Rows
- **Severity**: High
- **Code Quote**:
  ```python
  150|             ppms = [float(r["ppm"]) for r in rows if r.get("ppm")]
  151|             scale = min(1.0, ppm / statistics.median(ppms)) if ppms else 1.0
  ```
- **Failure Scenario**:
  If an image in `labels.csv` has `ppm` entered as `"0"` or `"0.0"` (e.g. placeholder row or uncalibrated test photo), `r.get("ppm")` evaluates to truthy (`"0"`), and `0.0` is added to `ppms`. If `statistics.median(ppms)` resolves to `0.0`, line 151 triggers `ZeroDivisionError: float division by zero`.
- **Suggested Fix**:
  Filter for positive numbers:
  ```python
  ppms = [float(r["ppm"]) for r in rows if r.get("ppm") and float(r["ppm"]) > 0]
  scale = min(1.0, ppm / statistics.median(ppms)) if ppms else 1.0
  ```

---

#### [ml/train_yolo.py:207-211] — Crash in `best_conf` on Empty Validation Curves
- **Severity**: Medium
- **Code Quote**:
  ```python
  208| def best_conf(box) -> tuple[float, float]:
  209|     f1 = [sum(col) / len(col) for col in zip(*[list(c) for c in box.f1_curve])]
  210|     k = max(range(len(f1)), key=f1.__getitem__)
  211|     return round(float(box.px[k]), 3), round(float(f1[k]), 4)
  ```
- **Failure Scenario**:
  If validation outputs no predictions or if `box.f1_curve` contains no curve entries (such as when running on a synthetic or real liner subset where no bounding boxes are detected), `zip(*...)` returns an empty list, so `f1 = []`. Line 210 then executes `max(range(0), ...)`, raising `ValueError: max() arg is an empty sequence`.
- **Suggested Fix**:
  Add an empty check fallback:
  ```python
  if not getattr(box, "f1_curve", None) or len(box.f1_curve) == 0 or len(box.f1_curve[0]) == 0:
      return 0.25, 0.0
  ```

---

#### [ml/train_yolo.py:259-261] — `IndexError` on Blank or Trailing-Newline Label Files in `synth`
- **Severity**: Medium
- **Code Quote**:
  ```python
  248|         lines = (out / "labels/train" / f"{base.stem}.txt").read_text().splitlines()
  ...
  259|         taken = [((float(c[1]) - float(c[3]) / 2) * w, (float(c[2]) - float(c[4]) / 2) * h,
  260|                   (float(c[1]) + float(c[3]) / 2) * w, (float(c[2]) + float(c[4]) / 2) * h)
  261|                  for c in (ln.split() for ln in lines)]
  ```
- **Failure Scenario**:
  When a training tile has no annotations (such as blank tiles added via `--blank` or negative card tiles where `lines` is empty or ends in whitespace), `lines` can have empty entries. If `ln` is empty, `c = ln.split()` returns `[]`. Accessing `c[1]`, `c[2]`, `c[3]`, `c[4]` raises `IndexError
#### [ml/train_yolo.py:259-261] — `IndexError` on Blank or Trailing-Newline Label Files in `synth` *(cont.)*
- **Severity**: Medium
- **Code Quote**:
  ```python
  259|         taken = [((float(c[1]) - float(c[3]) / 2) * w, (float(c[2]) - float(c[4]) / 2) * h,
  260|                   (float(c[1]) + float(c[3]) / 2) * w, (float(c[2]) + float(c[4]) / 2) * h)
  261|                  for c in (ln.split() for ln in lines)]
  ```
- **Failure Scenario**: When selecting a blank tile or a file containing trailing newlines, `lines` contains empty strings. `ln.split()` yields `[]`, raising `IndexError: list index out of range` on `c[1]`.
- **Suggested Fix**:
  ```python
  for c in (ln.split() for ln in lines if ln.strip())
  ```

---

#### [ml/train_v1.py:101-107] — Non-Atomic Cache Save Risks Cache Corruption and Work Loss
- **Severity**: Medium
- **Code Quote**:
  ```python
  101|         chunk = batch * 32  # save as we go, so a crash or a stalled GPU doesn't lose an hour of work
  ...
  106|             np.savez(cache, paths=np.array(paths), feats=np.stack([cached[p] for p in paths]).astype(np.float16))
  ```
- **Failure Scenario**: `np.savez` writes directly to `cache`. If interrupted mid-write (e.g. SIGINT, OOM, Metal driver timeout), `cache` is left truncated. The next run fails in `np.load` with `BadZipFile`, destroying all previously computed embeddings.
- **Suggested Fix**: Write to a temporary file in the same directory and atomically rename via `replace`:
  ```python
  tmp_cache = cache.with_suffix(".tmp.npz")
  np.savez(tmp_cache, paths=np.array(paths), feats=np.stack([cached[p] for p in paths]).astype(np.float16))
  tmp_cache.replace(cache)
  ```

---

#### [ml/train_v1.py:93] & [server/sentinel_server/pipeline/classify.py:97] — Unclosed `NpzFile` Handle Leaks File Descriptors
- **Severity**: Low
- **Code Quote**:
  ```python
  classify.py:97|         z = np.load(head_path, allow_pickle=False)
  ```
- **Failure Scenario**: `np.load` on a `.npz` archive leaves a zipfile handle open. In long-running processes or server workers that dynamically instantiate classifiers, file descriptors leak.
- **Suggested Fix**: Use a context manager:
  ```python
  with np.load(head_path, allow_pickle=False) as z:
      self.W, self.b = z["W"], z["b"]
      self.classes = z["classes"].tolist()
      self.T = float(z["T"]) if "T" in z else 1.0
      model_name = str(z["model"])
  super().__init__(model_name)
  ```

---

### 2. SECURITY ISSUES

#### [server/sentinel_server/pipeline/classify.py:116] — Unsafe Checkpoint Deserialization via `weights_only=False`
- **Severity**: High
- **Code Quote**:
  ```python
  116|         ck = torch.load(model_path, map_location="cpu", weights_only=False)
  ```
- **Failure Scenario**: `FineTunedCNN` sets `weights_only=False`. If `SENTINEL_CLASSIFIER_MODEL` points to an untrusted file, arbitrary code execution (RCE) can occur via Python `pickle` payloads during model load. The checkpoint saved by [train_v2.py](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/train_v2.py#L231-L232) contains only standard dicts, tensors, and primitives, which work safely with `weights_only=True`.
- **Suggested Fix**:
  ```python
  ck = torch.load(model_path, map_location="cpu", weights_only=True)
  ```

---

### 3. DEPRECATED APIS & OUTDATED PATTERNS

#### [ml/train_v2.py:106-107] & [ml/train_yolo.py:155, 196, 253, 275, 278] — Deprecated Pillow Resampling Enums
- **Severity**: Low
- **Code Quote**:
  ```python
  train_v2.py:106|  small = im.resize((max(1, round(im.width * s)), max(1, round(im.height * s))), Image.BILINEAR)
  train_yolo.py:155| img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
  ```
- **Failure Scenario**: `Image.BILINEAR`, `Image.LANCZOS`, and `Image.BICUBIC` are legacy Pillow attributes deprecated since Pillow 9.1 and subject to removal in upcoming releases.
- **Suggested Fix**: Use `Image.Resampling.BILINEAR`, `Image.Resampling.LANCZOS`, and `Image.Resampling.BICUBIC`.

---

### 4. INCONSISTENCIES

#### [server/sentinel_server/pipeline/classify.py:57, 120] vs [ml/train_v1.py:58] — Server Pipeline Ignores CUDA
- **Severity**: High
- **Code Quote**:
  ```python
  classify.py:57|  self.device = "mps" if torch.backends.mps.is_available() else "cpu"
  classify.py:120| self.device = "mps" if torch.backends.mps.is_available() else "cpu"
  ```
- **Failure Scenario**: Unlike training scripts that support CUDA, the server classifier only checks `mps` and falls back to `cpu`. When deployed on an NVIDIA GPU server, inference runs on CPU, causing high server latency and CPU spikes.
- **Suggested Fix**: Check CUDA first:
  ```python
  self.device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
  ```

---

#### [ml/train_yolo.py:325] vs [ml/train_v1.py:164] & [ml/train_v2.py:150] — YOLO Script Hardcodes Default Device to MPS
- **Severity**: High
- **Code Quote**:
  ```python
  train_yolo.py:325| ap.add_argument("--device", default="mps")
  ```
- **Failure Scenario**: `train_v1.py` and `train_v2.py` default `--device` to `"auto"`, while `train_yolo.py` defaults to `"mps"`. Running `python train_yolo.py` on Linux/CUDA (as described in `RUN_ON_CUDA.md`) crashes with `RuntimeError: MPS not available on this platform`.
- **Suggested Fix**: Default `--device` to `"auto"` or use dynamic selection.

---

#### [ml/train_v1.py:183-185] vs [ml/train_v2.py:172-174] — Inconsistent Test Split Definitions
- **Severity**: Medium
- **Code Quote**:
  ```python
  train_v1.py:185| "test · real liners (held out)": te & real  # real = source in ("liner", "own")
  train_v2.py:174| "test · real liners (held out)": items(lambda r: r["split"] == "test" and r["source"] == "liner")
  ```
- **Failure Scenario**: In `train_v1.py`, held-out liners include both `"liner"` and `"own"`. In `train_v2.py`, it strictly matches `"liner"` and excludes `"own"`. Furthermore, `train_v2.py` strictly restricts web photos to `("inat", "ami")` whereas `train_v1.py` treats any non-synth, non-real test sample as web photos. Consequently, benchmark reports for v1 and v2 are evaluated on different test distributions.
- **Suggested Fix**: Align both scripts to use the identical test set definition.

---

#### [server/sentinel_server/models.py:130-133] — `Track.reviewed` Returns False for `"confirmed"` Status
- **Severity**: Medium
- **Code Quote**:
  ```python
  131|     def reviewed(self) -> bool:
  132|         """A person labelled or rejected it: the model no longer changes its label or count."""
  133|         return self.reviewed_label is not None or self.review_status == "rejected"
  ```
- **Failure Scenario**: When an expert confirms a model's prediction without changing the text label, `review_status` is set to `"confirmed"` while `reviewed_label` may remain `None`. Under line 133, `track.reviewed` returns `False`, allowing the pipeline to re-classify or mutate a human-confirmed track.
- **Suggested Fix**:
  ```python
  return self.reviewed_label is not None or self.review_status in ("confirmed", "rejected")
  ```

---

### 5. DEAD CODE, DUPLICATION & REPRODUCIBILITY

#### [ml/train_v2.py:93-96, 119] — Multi-Worker DataLoaders Duplicate MixRes RNG State
- **Severity**: Medium
- **Code Quote**:
  ```python
  96|      self.sides, self.p, self.rng = sides, p, random.Random(seed)
  ...
  119|     MixRes(),  # seed defaults to None
  ...
  186|     train_loader = DataLoader(Photos(train_items, t_train, args.size), sampler=sampler, **loader_kw)
  ```
- **Failure Scenario**: When `seed=None`, `random.Random(None)` is created in the main process before worker processes are forked. In PyTorch `DataLoader` with `num_workers > 0` and no `worker_init_fn`, every worker inherits the exact same `self.rng` generator state. Across parallel worker processes, identical sequences of scale transformations are applied to concurrent batches.
- **Suggested Fix**: Provide a `worker_init_fn` to reseed Python `random` in each worker, or use `torch.randint`.

---

#### [ml/train_v1.py:169-170, 202] — Missing Random Seed in `train_v1.py`
- **Severity**: Low
- **Code Quote**:
  ```python
  202| clf = LogisticRegression(C=C, class_weight="balanced", max_iter=3000).fit(X[tr], y[tr])
  ```
- **Failure Scenario**: While `train_v2.py` sets `torch.manual_seed(0)` and `train_yolo.py` passes `seed=0`, `train_v1.py` sets no seed for NumPy or scikit-learn. If solver implementations change or multi-threading differences occur, exact head weights and tie-breaking differ between runs.
- **Suggested Fix**: Pass `random_state=0` to `LogisticRegression` and call `np.random.seed(0)`.

---

#### [server/sentinel_server/models.py:103] — Missing Database Index on Foreign Key
- **Severity**: Low
- **Code Quote**:
  ```python
  103|     first_capture_id: Mapped[int] = mapped_column(ForeignKey("captures.id"))
  ```
- **Failure Scenario**: `card_id` and `track_id` have `index=True`, but `first_capture_id` lacks an index. In SQLite, unindexed foreign keys lead to table scans during joins or cascade integrity checks.
- **Suggested Fix**: Add `index=True` to `first_capture_id`.

---

### 6. PERFORMANCE & OPTIMIZATION

#### [server/sentinel_server/pipeline/classify.py:65, 133] — Unbatched Full-Image Stacking Causes Server OOM
- **Severity**: Medium
- **Code Quote**:
  ```python
  65|  batch = torch.stack([self.preprocess(c.convert("RGB")) for c in crops]).to(self.device)
  133| x = torch.stack([self.preprocess(c.convert("RGB")) for c in crops]).to(self.device)
  ```
- **Failure Scenario**: On sticky trap cards with high insect density or debris (e.g. hundreds of bounding boxes), all crops are stacked into a single tensor and pushed through the network in one forward pass. On memory-constrained devices or edge hubs, this triggers Out-Of-Memory crashes.
- **Suggested Fix**: Batch inference into chunks of 16 or 32 crops:
  ```python
  probs = []
  for i in range(0, len(crops), 32):
      batch = torch.stack([self.preprocess(c.convert("RGB")) for c in crops[i:i + 32]]).to(self.device)
      probs.append((self.model(batch) / self.T).softmax(dim=-1).cpu().numpy())
  p = np.concatenate(probs, axis=0) if probs else np.zeros((0, len(self.classes)))
  ```

---

#### [ml/train_v2.py:185-187] — 36 Persistent Workers Overwhelm System Resources
- **Severity**: Medium
- **Code Quote**:
  ```python
  185| loader_kw = dict(batch_size=args.batch, num_workers=args.workers, persistent_workers=args.workers > 0)
  186| train_loader = DataLoader(Photos(train_items, t_train, args.size), sampler=sampler, **loader_kw)
  187| eval_loaders = {k: DataLoader(Photos(v, t_eval, args.size), shuffle=False, **loader_kw) for k, v in evals.items()}
  ```
- **Failure Scenario**: Applying `loader_kw` (`num_workers=6`, `persistent_workers=True`) to `train_loader` plus 5 evaluation loaders spawns 36 persistent worker processes. These workers remain allocated for tiny evaluation datasets that are either evaluated only once at the end or contain fewer than 100 images, causing thread contention and shared-memory exhaustion.
- **Suggested Fix**: Use `num_workers=0` (or `num_workers=2, persistent_workers=False`) for `eval_loaders`.

---

### 7. TEST COVERAGE GAPS

#### [server/sentinel_server/pipeline/classify.py:48, 70, 95, 111] — Pragma No-Cover Suppresses Entire Classification Module
- **Severity**: High
- **Code Quote**:
  ```python
  48|  class _BioClip:  # pragma: no cover - needs torch + open_clip + weights download
  70|  class BioClipZeroShot(_BioClip):  # pragma: no cover
  95|  class BioClipLinear(_BioClip):  # pragma: no cover
  111| class FineTunedCNN:  # pragma: no cover - needs torch + torchvision
  ```
- **Failure Scenario**: All production classification classes are blanket-suppressed from test coverage. Mock or synthetic test fixtures for `linear_head_probs`, `FineTunedCNN.classify`, and `BioClipLinear.classify` are absent, allowing bugs such as the binary classification head crash or missing CUDA support to pass CI undetected.
- **Suggested Fix**: Write unit tests with lightweight dummy weight dicts and mock tensor models to verify output shape, temperature division, class ordering, and edge cases (0 detections, single detection, empty inputs).

---

### Scope & Contract Alignment Checks

1. **Dataset Splits & Leakage**:
   - `train_yolo.py` respects liner grouping across splits (`pick_val` and `held_out` group multi-day photos of the same liner together). Synthetic tile generation (`synth`) draws background tiles exclusively from `images/train`.
   - In `train_v1.py` and `train_v2.py`, classes are derived strictly from `train`. However, if a class (e.g. `debris`) appears only in `val` or `test`, both scripts silently discard those rows via `keep` filtering rather than recording open-set or zero-shot metrics on them.
2. **Label & Class Ordering**:
   - [server/sentinel_server/models.py](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/models.py#L13-L14) defines `SPECIES = ["CM", "OFM", "OBLR", "other_moth", "other_insect", "debris"]`.
   - `train_v1.py` and `train_v2.py` sort classes alphabetically (`['CM', 'OBLR', 'OFM', 'debris', ...]`).
   - `BioClipLinear` and `FineTunedCNN` correctly remap probabilities using `classes.index(s)` when building dictionaries, avoiding class label permutation.
3. **Artifact Names & Input Dimensions**:
   - `train_v1.py` saves `models/v1/head.npz` containing `classes`, `W`, `b`, `T`, `model`. Matches `BioClipLinear` loader.
   - `train_v2.py` saves `models/v2/<arch>.pt` containing `state_dict`, `arch`, `classes`, `size`, `mean`, `std`, `T`. Matches `FineTunedCNN` loader.
   - Input image resolution defaults to 224x224 and is stored in `ck["size"]`, matching server transforms.

---

### Prioritized Next Steps

1. **Fix Critical Crash in `train_v1.py`**: Rename `T` (text features) to `text_features` to eliminate the variable shadowing collision with `T` (temperature) that crashes `--final`.
2. **Harden Model Deserialization in Server**: Replace `weights_only=False` with `weights_only=True` in `FineTunedCNN` to protect against arbitrary code execution.
3. **Fix CUDA Device Fallback on Server**: Update `server/sentinel_server/pipeline/classify.py` to prioritize `cuda` so server deployments utilize available GPUs.
4. **Fix Edge-Case Crashes in Training Scripts**: Add zero-guards in `train_yolo.py` for `ppm == 0` and empty `f1_curve`, and guard `warm == 0` in `train_v2.py` `SequentialLR`.
5. **Fix `Track.reviewed` Property**: Include `"confirmed"` status in `Track.reviewed` logic so human confirmations are respected by downstream tracking stages.
6. **Add Unit Tests for Classification & Pipeline**: Add automated tests covering `linear_head_probs` (including 2-class binary heads) and batch-sliced crop classification.
