# Orchard Sentinel Code Review — Chunk 1 of 6
**Scope:** `CLAUDE.md`, `.claude/rules/ml.md`, `ml/README.md`, `ml/RUN_ON_CUDA.md`, `ml/build_dataset.py`, `ml/carry_liner_labels.py`, `ml/clean_dataset.py`.

---

## 1. Bugs (Correctness, Crashes, Data Leakage, Resource Leaks)

### [ml/build_dataset.py:141](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/build_dataset.py#L141)
- **Severity:** Critical
- **Category:** Data Leakage / Correctness
- **Quote:**
  ```python
  138| return [{"path": r["path"], "label": r["label"], "source": "synth", "source_path": r["source_path"],
  139|          # bare-liner debris has no source photo: each crop is its own group;
  140|          # field-card photos (make_trap_style.py --field) bring their card as the group
  141|          "group": r.get("group") or ("" if r["source_path"] else f"liner:{Path(r['path']).stem}"),
  ```
- **Concrete Failure Scenario:** For bare-liner debris, `r["source_path"]` is empty, so line 141 sets `group = f"liner:{Path(r['path']).stem}"`. Because `r['path']` is the unique file path of the synthetic crop rather than the underlying liner photo (`r['liner']`), every single crop receives its own distinct group. At lines 248–251, `split_of(s["group"], ...)` hashes each crop independently. As a result, crops cut from the exact same blank liner photo (and according to `ml/README.md:30-33`, only 3 blank webcam liner photos exist for all 24,112 synthetic samples) are split across `train`, `val`, and `test`. The classifier trains on debris patches from liner A and evaluates on patches from the exact same physical liner A (identical paper texture, grid alignment, lighting, and sensor noise), causing severe data leakage. This violates `.claude/rules/ml.md:23` (*"A split keeps every photo of one liner or card on the same side"*).
- **Suggested Fix:** Group bare-liner debris by the source liner image (`r["liner"]`) so all crops from a liner stay in the same split:
  ```python
  "group": r.get("group") or ("" if r["source_path"] else f"liner:{Path(r['liner']).stem}"),
  ```

---

### [ml/build_dataset.py:246-251](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/build_dataset.py#L246-L251)
- **Severity:** High
- **Category:** Test Set Leakage / Split Integrity
- **Quote:**
  ```python
  246| synth = [s for s in synth if s["own_group"] or not s["source_path"] or s["source_path"] in kept]
  247| for s in synth:
  248|     src = None if s["own_group"] else kept.get(s["source_path"])
  249|     s["group"] = src["group"] if src else s["group"]
  250|     s["class"] = CLASS_OF[s["label"]]
  251|     s["split"] = src["split"] if src else split_of(s["group"], args.seed, args.val, args.test)
  ```
- **Concrete Failure Scenario:** When synthetic crops are generated from field cards (`make_trap_style.py --field`), `s["own_group"]` is True, setting `src = None`. Line 251 assigns `s["split"]` solely via `split_of(s["group"], ...)`, which executes a random SHA-1 split (70% train / 15% val / 15% test). `split_of` never inspects `data/field/test_cards.txt` or `locked_test.txt`. Consequently, synthetic copies of held-out test cards leak into `train` (~70% probability per group), directly violating `.claude/rules/ml.md:22-23` (*"Held-out sets are listed in files, not chosen at random each run: data/own/locked_test.txt, data/field/test_cards.txt... Never train on them. Synthetic copies keep their source photo's split"*).
- **Suggested Fix:** Check card lists when determining splits for `own_group` synthetic items:
  ```python
  if s["own_group"]:
      card = s["group"].removeprefix("card:")
      if card in locked:
          s["split"] = "locked"
      elif card in field_test_cards:
          s["split"] = "test"
      else:
          s["split"] = split_of(s["group"], args.seed, args.val, args.test)
  ```

---

### [ml/build_dataset.py:227-231](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/build_dataset.py#L227-L231)
- **Severity:** High
- **Category:** Data Loss / Inverted Precedence
- **Quote:**
  ```python
  227| if CLASS_OF[rows[i]["label"]] == CLASS_OF[rows[j]["label"]]:
  228|     drop.add(j)  # rows are sorted by source preference, so i is the one to keep
  229| elif rows[i]["source"] != "own" or rows[j]["source"] != "own":
  230|     drop |= {i, j}
  231|     conflicts.append((rows[i]["path"], rows[i]["label"], rows[j]["path"], rows[j]["label"]))
  ```
- **Concrete Failure Scenario:**
  1. If an `own` image (rank 0, row `i`) matches an external web image (`inat`/`ami`, rank 1/2, row `j`) but their labels conflict, `rows[j]["source"] != "own"` is True. Line 230 drops `{i, j}`, discarding the team's ground-truth `own` trap image because of a mislabelled external web photo.
  2. If two images from `own` match with conflicting labels (e.g. human error during staged card review), `rows[i]["source"] != "own"` and `rows[j]["source"] != "own"` are both False. The conflict is not logged to `conflicts`, neither index is added to `drop`, and both contradictory labels remain in `dataset.csv`.
- **Suggested Fix:** Align the code with the docstring (*"keeping own > inat > ami"* and dropping true ambiguities):
  ```python
  if CLASS_OF[rows[i]["label"]] == CLASS_OF[rows[j]["label"]]:
      drop.add(j)
  elif rows[i]["source"] == "own" and rows[j]["source"] != "own":
      drop.add(j)  # own takes precedence over web
  else:
      drop |= {i, j}  # conflicting labels within the same source rank or both own
      conflicts.append((rows[i]["path"], rows[i]["label"], rows[j]["path"], rows[j]["label"]))
  ```

---

### [ml/build_dataset.py:166](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/build_dataset.py#L166)
- **Severity:** High
- **Category:** Crash / Runtime Compatibility
- **Quote:**
  ```python
  165| block = hashes[start:start + 512, None, :] ^ hashes[None, :, :]
  166| dist = np.bitwise_count(block).sum(axis=-1)
  ```
- **Concrete Failure Scenario:** `np.bitwise_count` requires NumPy $\ge$ 2.0.0. When running on environments with NumPy 1.x (such as NumPy 1.26.4, commonly installed by PyTorch CUDA 12.4 wheels as instructed in `RUN_ON_CUDA.md`), `build_dataset.py` crashes with `AttributeError: module 'numpy' has no attribute 'bitwise_count'`.
- **Suggested Fix:** Enforce `numpy>=2.0.0` in `requirements.txt` or use a backward-compatible popcount implementation:
  ```python
  dist = np.unpackbits(block.view(np.uint8), axis=-1).sum(axis=-1)
  ```

---

### [ml/build_dataset.py:257-263](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/build_dataset.py#L257-L263)
- **Severity:** Medium
- **Category:** Off-by-one / Split Imbalance
- **Quote:**
  ```python
  257| groups = sorted({r["group"] for r in liner if r["set"] == name and not r["held_out"]},
  258|                  key=lambda g: hashlib.sha1(f"{args.seed}:{g}".encode()).hexdigest())
  259| size = Counter(r["group"] for r in liner if r["set"] == name and not r["held_out"])
  260| for g in groups[:-1]:  # liners differ a lot in how many insects they hold: go by crops, not liners
  261|     if sum(size[v] for v in liner_val if v in size) >= 0.2 * sum(size.values()):
  262|         break
  263|     liner_val.add(g)
  ```
- **Concrete Failure Scenario:** If a liner set contains only 1 non-held-out group (`len(groups) == 1`), `groups[:-1]` is empty (`[]`), resulting in zero validation crops from that set. Furthermore, if `len(groups) == 2` and `groups[0]` holds 90% of the crops, `0 >= 0.2 * total` is False on the first iteration, unconditionally placing `groups[0]` (90% of the set's data) into `liner_val`.
- **Suggested Fix:** Handle `len(groups) <= 1` explicitly and select the subset of groups that minimizes `|sum(val_crops) / total - 0.2|`.

---

### [ml/carry_liner_labels.py:34, 40-46](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/carry_liner_labels.py#L34-L46)
- **Severity:** Medium
- **Category:** Crash / Missing Error Guard
- **Quote:**
  ```python
  33| def features(path: Path, orb) -> tuple[np.ndarray, np.ndarray]:
  34|     k, d = orb.detectAndCompute(cv2.imread(str(path), cv2.IMREAD_GRAYSCALE), None)
  35|     return np.float32([p.pt for p in k]), d
  ...
  40| (pa, da), (pb, db) = fa, fb
  41| good = [m for m, n in (p for p in bf.knnMatch(da, db, k=2) if len(p) == 2) if m.distance < 0.75 * n.distance]
  ```
- **Concrete Failure Scenario:** If an image is missing, corrupt, or unreadable by OpenCV, `cv2.imread()` returns `None`, causing `orb.detectAndCompute` to crash with `cv2.error`. If an image has excessive glare or no distinct texture, ORB finds zero keypoints, returning `d = None`. Passing `da = None` or `db = None` to `bf.knnMatch()` at line 41 crashes OpenCV.
- **Suggested Fix:** Check that image matrices and descriptors are valid:
  ```python
  def features(path: Path, orb) -> tuple[np.ndarray, np.ndarray | None]:
      img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
      if img is None:
          return np.empty((0, 2), np.float32), None
      k, d = orb.detectAndCompute(img, None)
      return (np.float32([p.pt for p in k]) if k else np.empty((0, 2), np.float32)), d
  ```
  In `affine()`, return `None` immediately if `da is None or db is None or len(da) < 2 or len(db) < 2`.

---

### [ml/carry_liner_labels.py:102-105](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/carry_liner_labels.py#L102-L105)
- **Severity:** Medium
- **Category:** Crash on Write / Data Integrity
- **Quote:**
  ```python
  102| with open(labels, "w", newline="") as f:
  103|     w = csv.DictWriter(f, fieldnames=FIELDS, restval="")
  104|     w.writeheader()
  105|     w.writerows(rows)
  ```
- **Concrete Failure Scenario:** `labels.csv` often contains extra columns (e.g. `by`, `species`, `notes`, or `annotator` as mentioned in `ml/README.md:75-78`). Because `extrasaction` defaults to `"raise"`, `w.writerows(rows)` raises `ValueError: dict contains fields not in fieldnames`, failing after having already created a backup file.
- **Suggested Fix:** Pass `extrasaction="ignore"` to `csv.DictWriter`:
  ```python
  w = csv.DictWriter(f, fieldnames=FIELDS, restval="", extrasaction="ignore")
  ```

---

### [ml/carry_liner_labels.py:70, 78](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/carry_liner_labels.py#L70)
- **Severity:** Low
- **Category:** Resource Leak
- **Quote:**
  ```python
  70| rows = list(csv.DictReader(open(labels, newline="")))
  ...
  78| for group in json.load(open(args.data / "liners.json")):
  ```
- **Concrete Failure Scenario:** File descriptors are opened without context managers or explicit `.close()` calls, relying on garbage collection.
- **Suggested Fix:** Wrap in `with open(...) as f:` blocks.

---

### [ml/clean_dataset.py:76-80](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/clean_dataset.py#L76-L80)
- **Severity:** Low
- **Category:** Crash on Bad Image
- **Quote:**
  ```python
  76| with Image.open(p) as im:
  77|     im = im.convert("RGB")
  78|     im.thumbnail((cell, cell))
  79|     out.paste(im, ((k % cols) * cell, (k // cols) * cell))
  ```
- **Concrete Failure Scenario:** If a suspect image file listed in `suspects` has been removed or is corrupt, `Image.open(p)` raises `FileNotFoundError` or `UnidentifiedImageError`, crashing `clean_dataset.py` at the very end after long logistic regression feature processing.
- **Suggested Fix:** Wrap `Image.open` in a `try...except (OSError, IOError)` block and render a blank or red placeholder cell.

---

## 2. Security Issues

### [ml/carry_liner_labels.py:78-79](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/carry_liner_labels.py#L78-L79)
- **Severity:** Low
- **Category:** Unvalidated Input / Path Traversal
- **Quote:**
  ```python
  78| for group in json.load(open(args.data / "liners.json")):
  79|     feats = {p: features(args.data / "inbox" / p, orb) for p in group}
  ```
- **Concrete Failure Scenario:** `liners.json` provides photo filename keys `p` that are joined directly with `args.data / "inbox" / p`. If `liners.json` contains `../` sequences, it can traverse outside `inbox` and open arbitrary image files on the filesystem.
- **Suggested Fix:** Validate that `(args.data / "inbox" / p).resolve().is_relative_to((args.data / "inbox").resolve())`.

---

## 3. Deprecated APIs / Outdated Patterns

### [ml/build_dataset.py:154, 178](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/build_dataset.py#L154)
- **Severity:** Low
- **Category:** Deprecated API
- **Quote:**
  ```python
  154| g = np.asarray(ImageOps.exif_transpose(im).convert("L").resize((17, 16), Image.BILINEAR), dtype=np.int16)
  ...
  178| t = np.asarray(ImageOps.exif_transpose(im).convert("L").resize((64, 64), Image.BILINEAR), dtype=np.float32).ravel()
  ```
- **Concrete Failure Scenario:** `Image.BILINEAR` is deprecated since Pillow 10.0.0 and will be removed in future versions in favor of `Image.Resampling.BILINEAR`.
- **Suggested Fix:** Use `Image.Resampling.BILINEAR`.

### [ml/carry_liner_labels.py:100](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/carry_liner_labels.py#L100)
- **Severity:** Low
- **Category:** Outdated Pattern / Name Collision
- **Quote:**
  ```python
  100| backup = labels.with_name(f"labels.backup-{time.strftime('%H%M%S')}.csv")
  ```
- **Concrete Failure Scenario:** The timestamp format `%H%M%S` omits the year, month, and day. If the script is run at the same second across days, backups can overwrite prior backups.
- **Suggested Fix:** Use `time.strftime('%Y%m%d-%H%M%S')`.

---

## 4. Inconsistencies

### [ml/RUN_ON_CUDA.md:85](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/RUN_ON_CUDA.md#L85) vs [ml/RUN_ON_CUDA.md:62](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/RUN_ON_CUDA.md#L62)
- **Severity:** Medium
- **Category:** Workflow Inconsistency / Packaging Loss
- **Quote:**
  ```bash
  62| python train_v1.py --device cuda --batch 64
  ...
  85| cd ~/orchard-train/ml && zip -qr results.zip models -x 'models/v1/*' && cp results.zip /mnt/c/Users/YOU/Downloads/
  ```
- **Concrete Failure Scenario:** Step 2 instructs retraining the v1 linear head on CUDA, which saves to `models/v1/` by default. Step "Bring back" (line 85) explicitly excludes `'models/v1/*'` from `results.zip`. Retrained v1 weights are omitted from the archive.
- **Suggested Fix:** Remove `-x 'models/v1/*'` or specify an explicit output directory (e.g. `--out models/v1-cuda`) and update the zip command.

### [ml/README.md:7-8, 29](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/README.md#L7-L8) vs [CLAUDE.md:19-20](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/CLAUDE.md#L19-L20)
- **Severity:** Low
- **Category:** Documentation Inconsistency
- **Quote:**
  ```bash
  7| python3 fetch_ami.py --out data/ami --other-moths 60
  8| python3 fetch_inat.py --out data/inat
  ...
  29| python make_trap_style.py --preview 48
  ```
- **Concrete Failure Scenario:** `CLAUDE.md:19-20` mandates: *"Use that folder's `.venv/bin/python`, not the system Python."* However, `ml/README.md` mixes `python3`, `python`, and `.venv/bin/python`, which can invoke an unconfigured global Python environment without the installed `uv` dependencies.
- **Suggested Fix:** Standardize all examples on `.venv/bin/python`.

### [ml/build_dataset.py:77, 93, 133](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/build_dataset.py#L77) vs [ml/build_dataset.py:114, 130](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/build_dataset.py#L114)
- **Severity:** Low
- **Category:** Inconsistent Input Validation
- **Quote:**
  ```python
  114| if label not in CLASS_OF:
  ...
  130| for r in csv.DictReader(f) if r["label"] in CLASS_OF]
  ```
- **Concrete Failure Scenario:** `read_own` and `read_liner` filter entries using `label in CLASS_OF`. In contrast, `read_ami`, `read_inat`, and `read_synth` do not check `CLASS_OF`, allowing unmapped labels to trigger `KeyError` exceptions later at lines 227, 239, 250, and 285.
- **Suggested Fix:** Enforce `if r["label"] in CLASS_OF` consistently across all data readers.

---

## 5. Dead Code, Duplication, and Organization Problems

### [ml/clean_dataset.py:70, 80](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/clean_dataset.py#L70)
- **Severity:** Low
- **Category:** Inefficient Organization / Repeated Allocations
- **Quote:**
  ```python
  69| def sheet(paths: list[str], captions: list[str], dest: Path, cell: int = 160, cols: int = 10) -> None:
  70|     from PIL import Image, ImageDraw
  ...
  80|     ImageDraw.Draw(out).text(((k % cols) * cell + 3, (k // cols) * cell + 3), c, fill=(255, 0, 0))
  ```
- **Concrete Failure Scenario:** `ImageDraw.Draw(out)` is re-instantiated on every single loop iteration (up to 150 times per sheet). Imports are located inside function bodies instead of module level.
- **Suggested Fix:** Move `from PIL import Image, ImageDraw` to top-level imports, and instantiate `draw = ImageDraw.Draw(out)` once outside the thumbnail loop.

### [ml/carry_liner_labels.py:93](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/carry_liner_labels.py#L93)
- **Severity:** Low
- **Category:** String Formatting Defect
- **Quote:**
  ```python
  93| r["source"] = f"{r['source']} carried"
  ```
- **Concrete Failure Scenario:** If `r["source"]` was empty or missing, this evaluates to `" carried"` (with an unintended leading space). If run iteratively across cascading days, it appends `" carried carried"`.
- **Suggested Fix:** Cleanly format source provenance:
  ```python
  src = r.get("source", "").strip()
  r["source"] = f"{src} carried" if src and "carried" not in src else (src or "carried")
  ```

---

## 6. Performance & Optimization Opportunities

### [ml/build_dataset.py:216](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/build_dataset.py#L216)
- **Severity:** Medium
- **Category:** Performance Bottleneck
- **Quote:**
  ```python
  216| for r in rows:
  217|     r["dhash"] = dhash(r["path"])
  ```
- **Concrete Failure Scenario:** Computing 256-bit difference hashes across 15,000+ images (iNat, AMI, and own) runs in a single-threaded loop, opening, EXIF-transposing, and resizing each file sequentially. On a multi-core machine (such as an Apple M3 or Linux workstation), this step takes several minutes.
- **Suggested Fix:** Use `concurrent.futures.ProcessPoolExecutor` to parallelize `dhash` computation across CPU cores:
  ```python
  with ProcessPoolExecutor() as executor:
      hashes = list(executor.map(dhash, [r["path"] for r in rows]))
  for r, h in zip(rows, hashes):
      r["dhash"] = h
  ```

---

## 7. Test Coverage Gaps

1. **`build_dataset.py` split isolation tests missing:**
   No unit tests verify that synthetic copies, bare-liner debris, and staged cards never leak across train/val/test splits or violate `locked_test.txt` and `test_cards.txt`.
2. **Near-duplicate conflict tests missing:**
   No tests verify that near-duplicate images with conflicting labels between `own` and `inat`/`ami` correctly preserve `own` rather than dropping both.
3. **`carry_liner_labels.py` alignment and propagation tests missing:**
   No automated tests verify that ORB feature extraction, affine RANSAC transformation, and IoU matching correctly project bounding boxes between time series photos.
4. **`clean_dataset.py` out-of-fold probability tests missing:**
   No tests check `odd_ones` or `out_of_fold` behavior on small synthetic arrays with edge cases (e.g. single-class folds or zero variance).

---

## Prioritized Next Steps

1. **Fix bare-liner debris grouping in `build_dataset.py:141`:** Change `group` assignment to use `r["liner"]` so bare-liner debris does not leak identical liner backgrounds across train and test.
2. **Enforce held-out card checks for synthetic field cards in `build_dataset.py:251`:** Ensure `own_group` synthetic crops respect `test_cards.txt` and `locked_test.txt` rather than hashing into training.
3. **Correct near-duplicate resolution logic in `build_dataset.py:227-231`:** Prevent `own` ground truth photos from being discarded when colliding with conflicting external web photos.
4. **Guard OpenCV reading and matching in `carry_liner_labels.py:34, 41`:** Check for `None` images and empty descriptors before calling `orb.detectAndCompute` and `bf.knnMatch`.
5. **Add `extrasaction="ignore"` to `carry_liner_labels.py:103`:** Avoid runtime `ValueError` crashes when `labels.csv` contains additional annotation columns.
6. **Harmonize `RUN_ON_CUDA.md:85` zip exclusions:** Ensure trained v1 head weights are preserved when bundling results back from CUDA.
