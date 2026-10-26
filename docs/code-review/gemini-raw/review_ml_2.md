# Read-Only Code Review: Chunk 3 of 6 (`ml/`)

**Scope of this chunk:**
- `ml/fetch_inat.py`
- `ml/import_roboflow_labels.py`
- `ml/label_field_cards.py`
- `ml/liner_crops.py`
- `ml/make_bundle.py`

---

## 1. BUGS (Correctness, Crashes, Race Conditions, Data Loss, Error Handling)

### 1.1 Center-Containment Logic Inversion in Overlap Check
- **File / Line:** [`ml/import_roboflow_labels.py:38`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/import_roboflow_labels.py#L38)
- **Severity:** High
- **Code:**
  ```python
  def overlaps(a, b) -> bool:
      return iou(a, b) >= 0.3 or (inside(centre(a), b) and inside(centre(b), a))
  ```
- **Concrete Failure Scenario:**
  If a detector box $d$ is smaller than and completely inside an uploader's ground truth box $g$ (or vice versa), `inside(centre(d), g)` is `True`, but `inside(centre(g), d)` is `False` (the center of the large box is outside the perimeter of the smaller box). Because `and` is used instead of `or`, `overlaps(d, g)` returns `False` whenever IoU $< 0.3$.
  Consequently, in line 70 (`dets = [d for d in union(fb, base) if not any(overlaps(d, g) for g in im["gt"])]`), the detector box is **not dropped**. It gets added to `dets` as an unlabelled box, placing a duplicate box on an insect the uploader already boxed. This directly violates the documented behavior on line 9: *"A detector box overlapping an uploader's box is dropped."*
- **Suggested Fix:**
  Change `and` to `or`:
  ```python
  def overlaps(a, b) -> bool:
      return iou(a, b) >= 0.3 or inside(centre(a), b) or inside(centre(b), a)
  ```

---

### 1.2 `setdefault` Silently Fails to Hold Out Test Groups (Data Leakage)
- **File / Line:** [`ml/liner_crops.py:194-195`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/liner_crops.py#L194-L195)
- **Severity:** High
- **Code:**
  ```python
  for r in rows:
      r.setdefault("held_out", any(r["group"].startswith(t) for t in TEST_GROUPS))
  ```
- **Concrete Failure Scenario:**
  In `field_card_rows()` (line 129), `"held_out"` is explicitly set for every dictionary:
  `"held_out": r["photo"] in held or any(r["photo"].startswith(t) for t in FIELD_TEST)`.
  When `r["held_out"]` is `False`, the key `"held_out"` is already present in `r`. Python's `dict.setdefault()` **only** sets a value if the key does not exist.
  Therefore, if any field card photo belongs to a group listed in `TEST_GROUPS` (e.g., `trap_positive__...`), `setdefault` does nothing, leaving `held_out = False`. Those images are assigned `split = ""` on line 200 and leak directly into the training set.
- **Suggested Fix:**
  Combine the held-out conditions using boolean OR:
  ```python
  for r in rows:
      r["held_out"] = r.get("held_out", False) or any(r["group"].startswith(t) for t in TEST_GROUPS)
  ```

---

### 1.3 Asynchronous Save Race Condition Causes Lost IDs and Duplicate Orphan Boxes
- **File / Line:** [`ml/label_field_cards.py:368-369`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/label_field_cards.py#L368-L369)
- **Severity:** High
- **Code:**
  ```javascript
  if (data[p] === sent && sent.length === rows.length)
    sent.forEach((b,i) => { b.n = rows[i].n; b.source = rows[i].source; b.length_mm = rows[i].length_mm; });
  ```
- **Concrete Failure Scenario:**
  1. A user draws box A (client creates object with `n: null`).
  2. The 300ms debounce fires, and `flush()` posts box A (`sent.length == 1`).
  3. While that request is in-flight, the user draws box B (`data[p].length` becomes 2).
  4. The HTTP response for box A returns (`rows.length == 1`).
  5. The client checks `sent.length === rows.length` (`2 === 1`), which evaluates to `False`. The update loop is skipped! Box A's `n` remains `null`.
  6. The next debounce flush posts box A (`n: null`) and box B (`n: null`).
  7. On the server (`Store.save`), `old.get("None")` is empty, so the server assumes box A is a brand new manual box, allocates a new `next_n`, writes an extra crop to disk, and duplicates box A in `labels.csv`.
- **Suggested Fix:**
  Assign a temporary client-side UUID to new boxes so the server response can update box IDs by matching UUIDs rather than relying on array indices and lengths remaining unchanged during in-flight network requests.

---

### 1.4 Path Traversal / Subpath Crash on Absolute Paths in `make_bundle.py`
- **File / Line:** [`ml/make_bundle.py:43-45`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/make_bundle.py#L43-L45)
- **Severity:** High
- **Code:**
  ```python
  q = Path(path)
  if q.is_absolute():
      q = q.resolve().relative_to(HERE.resolve())
  return q.as_posix()
  ```
- **Concrete Failure Scenario:**
  The docstring notes: *"Some rows of dataset.csv hold absolute paths (photos fetched with --out given in full); the bundle's dataset.csv and feature cache get them rewritten relative to ml/"*.
  `HERE` is defined as `Path(__file__).parent` (`.../ml`). If data was fetched to the project root `data/` (or any path outside `ml/`, such as `/Users/.../Developer/Active/applev2/data/inat`), `q.resolve()` is not a descendant of `HERE.resolve()`.
  Calling `relative_to(HERE.resolve())` immediately crashes with `ValueError: '...' is not in the subpath of '...'`. The bundle process aborts.
- **Suggested Fix:**
  Check whether `q.resolve()` is relative to `HERE.parent.resolve()` (workspace root) or `HERE.resolve()`, and strip accordingly:
  ```python
  if q.is_absolute():
      try:
          q = q.resolve().relative_to(HERE.resolve())
      except ValueError:
          q = q.resolve().relative_to(HERE.parent.resolve())
  ```

---

### 1.5 Missing Images Kept in Bundle `dataset.csv` Causing Training Failures
- **File / Line:** [`ml/make_bundle.py:78-81`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/make_bundle.py#L78-L81)
- **Severity:** Medium
- **Code:**
  ```python
  r["path"] = relative(r["path"])
  if not src.exists():
      missing += 1
      continue
  put(src, ml / r["path"], args.max_side if r["source"] in ("inat", "ami") else 0)
  ```
- **Concrete Failure Scenario:**
  When `src.exists()` is `False`, line 81 skips copying the image file. However, `r["path"]` has already been rewritten on line 78, and `rows` is written in its entirety to `ml/data/dataset.csv` on line 89.
  When the bundle is extracted on the GPU instance and `train_v1.py` attempts to load every image referenced in `dataset.csv`, it throws `FileNotFoundError`.
- **Suggested Fix:**
  Only write rows to the bundle's `dataset.csv` if the file exists and was copied:
  ```python
  valid_rows = []
  for n, r in enumerate(rows, 1):
      src = HERE / r["path"]
      if not src.exists():
          missing += 1
          continue
      r["path"] = relative(r["path"])
      put(src, ml / r["path"], args.max_side if r["source"] in ("inat", "ami") else 0)
      valid_rows.append(r)
  ...
  w.writerows(valid_rows)
  ```

---

### 1.6 File Extension Mismatch in `test_cards.txt` Matching
- **File / Line:** [`ml/liner_crops.py:129`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/liner_crops.py#L129)
- **Severity:** Medium
- **Code:**
  ```python
  "held_out": r["photo"] in held or any(r["photo"].startswith(t) for t in FIELD_TEST)
  ```
- **Concrete Failure Scenario:**
  In `test_cards.txt`, cards are listed by camera card/photo stems (e.g. `PXL_20250422_174434151`), matching how `FIELD_TEST` prefixes are defined on line 107. In `labels.csv`, `r["photo"]` contains the full filename with extension (e.g. `PXL_20250422_174434151.jpg`).
  Because `r["photo"] in held` tests for exact string equality, stems listed in `test_cards.txt` never match `r["photo"]`. Those test cards are never held out and enter the training split.
- **Suggested Fix:**
  Check both the full name and the stem:
  ```python
  "held_out": (r["photo"] in held or Path(r["photo"]).stem in held or any(r["photo"].startswith(t) for t in FIELD_TEST))
  ```

---

### 1.7 Broken Symlinks Trigger `FileExistsError` in `import_roboflow_labels.py`
- **File / Line:** [`ml/import_roboflow_labels.py:61-63`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/import_roboflow_labels.py#L61-L63)
- **Severity:** Medium
- **Code:**
  ```python
  link = out / "inbox" / name
  if not link.exists():
      link.symlink_to(im["path"].resolve())
  ```
- **Concrete Failure Scenario:**
  In Python `pathlib.Path`, `link.exists()` checks whether the *target* of the symlink exists. If `link` is an existing broken symlink (e.g. a previous Roboflow download directory was moved or cleaned up), `link.exists()` returns `False`.
  Executing `link.symlink_to(...)` on an existing symlink path raises `FileExistsError: [Errno 17] File exists`.
- **Suggested Fix:**
  Check `is_symlink()` or unlink first:
  ```python
  if link.is_symlink() or link.exists():
      link.unlink(missing_ok=True)
  link.symlink_to(im["path"].resolve())
  ```

---

### 1.8 Unhandled `ValueError` on Empty or Float Coordinates in `Store.view` and `Store.save`
- **File / Line:** [`ml/label_field_cards.py:74 & 107`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/label_field_cards.py#L74)
- **Severity:** Medium
- **Code:**
  Line 74:
  ```python
  moved = box != [int(r[k]) for k in ("x1", "y1", "x2", "y2")]
  ```
  Line 107:
  ```python
  "x1": float(r["x1"]), "y1": float(r["y1"]), "x2": float(r["x2"]), "y2": float(r["y2"])
  ```
- **Concrete Failure Scenario:**
  If an existing row in `labels.csv` was saved with floating-point formatted strings (e.g. `"12.0"` from detector output), line 74 crashes with `ValueError: invalid literal for int() with base 10: '12.0'`.
  If an entry has empty coordinates (`r["x1"] == ""`), line 107 throws `ValueError: could not convert string to float: ''` during `GET /api/data`, crashing the web UI on load.
- **Suggested Fix:**
  Parse robustly:
  ```python
  # Line 74
  moved = box != [int(round(float(r[k]))) for k in ("x1", "y1", "x2", "y2")]
  # Line 107
  "x1": float(r["x1"]) if r.get("x1") else 0.0, ...
  ```

---

### 1.9 Missing Manifest Directory Creation in `fetch_inat.py`
- **File / Line:** [`ml/fetch_inat.py:174`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/fetch_inat.py#L174)
- **Severity:** Medium
- **Code:**
  ```python
  manifest = args.out / "manifest.csv"
  ...
  with open(manifest, "w", newline="") as f:
  ```
- **Concrete Failure Scenario:**
  If `--only` selects a class with 0 results or if queries return empty, `download()` is never called, so `dest.parent.mkdir` (line 119) never executes. Line 174 attempts to open `manifest` in a non-existent directory `args.out`, raising `FileNotFoundError`.
- **Suggested Fix:**
  Add `args.out.mkdir(parents=True, exist_ok=True)` before line 174.

---

### 1.10 Unsynchronized Access to `store.rows` Across Threads
- **File / Line:** [`ml/label_field_cards.py:130`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/label_field_cards.py#L130)
- **Severity:** Medium
- **Code:**
  ```python
  by = {p: [] for p in store.photos()}
  for r in store.rows:
      by.setdefault(r["photo"], []).append(store.view(r))
  ```
- **Concrete Failure Scenario:**
  `ThreadingHTTPServer` spawns a thread per request. In `Store.save`, `self.rows` is reassigned under `self.lock` (line 94: `self.rows = [r for r in self.rows if r["photo"] != photo] + rows`). However, `do_GET` iterates over `store.rows` without acquiring `store.lock`, exposing callers to torn reads or `RuntimeError: list changed size during iteration`.
- **Suggested Fix:**
  Acquire `store.lock` when reading `store.rows` in `do_GET`, or expose a thread-safe getter method.

---

### 1.11 Missing UTF-8 Encoding on Text File I/O Across All Scripts
- **File / Line:** Multiple files:
  - [`ml/fetch_inat.py:172, 174`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/fetch_inat.py#L172)
  - [`ml/label_field_cards.py:48, 96`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/label_field_cards.py#L48)
  - [`ml/liner_crops.py:66, 115, 122, 207`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/liner_crops.py#L66)
  - [`ml/make_bundle.py:73, 86`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/make_bundle.py#L73)
  - [`ml/import_roboflow_labels.py:52, 84`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/import_roboflow_labels.py#L52)
- **Severity:** Medium
- **Code:** `open(manifest, "w", newline="")`, `open(self.path, newline="")`, etc.
- **Concrete Failure Scenario:**
  iNaturalist attribution and place strings frequently contain non-ASCII characters (e.g. accents in contributor names). On Windows or environments where the default locale encoding is CP1252 or ASCII, writing these strings raises `UnicodeEncodeError`. Reading labels/species CSVs containing unicode raises `UnicodeDecodeError`.
- **Suggested Fix:**
  Pass `encoding="utf-8"` to all `open()`, `read_text()`, and `write_text()` calls.

---

### 1.12 Corrupted 0-Byte Downloads Permanently Cached
- **File / Line:** [`ml/fetch_inat.py:117-118`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/fetch_inat.py#L117-L118) & [`ml/make_bundle.py:50-51`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/make_bundle.py#L50-L51)
- **Severity:** Low
- **Code:**
  ```python
  if dest.exists():
      return "cached"
  ```
- **Concrete Failure Scenario:**
  If a download or thumbnail generation process is interrupted or writes an empty 0-byte file, subsequent runs see `dest.exists() == True` and immediately return `"cached"`. Corrupted or incomplete files remain in the dataset indefinitely.
- **Suggested Fix:**
  Verify file existence and non-zero size: `if dest.exists() and dest.stat().st_size > 0:`.

---

## 2. Security Issues

### 2.1 Unhandled Exceptions and Unbounded Input in `label_field_cards.py`
- **File / Line:** [`ml/label_field_cards.py:143-146`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/label_field_cards.py#L143-L146)
- **Severity:** Medium
- **Code:**
  ```python
  body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
  if body["photo"] not in store.photos():
      return self.send(b"unknown photo", "text/plain", 400)
  rows = store.save(body["photo"], body["boxes"])
  ```
- **Concrete Failure Scenario:**
  If an HTTP POST request omits `Content-Length` or provides an invalid value, `int(self.headers["Content-Length"])` raises `TypeError` or `ValueError`. If `body` is not a dictionary (e.g. `[]`), line 144 raises `TypeError`. Unhandled exceptions in the handler crash the worker thread without returning an HTTP status code.
- **Suggested Fix:**
  Wrap request parsing in a `try...except` block and validate that `Content-Length` and payload fields exist before indexing.

---

## 3. Deprecated APIs / Outdated Patterns

### 3.1 Unclosed File Descriptors in One-Liners
- **File / Line:** [`ml/import_roboflow_labels.py:52, 55, 56`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/import_roboflow_labels.py#L52-L56)
- **Severity:** Low
- **Code:**
  ```python
  old = list(csv.DictReader(open(labels, newline=""))) if labels.exists() else []
  base_c = json.load(open(cache / f"{args.dataset}__baseline__native.json"))
  fb_c = json.load(open(cache / f"{args.dataset}__flatbug__native.json"))
  ```
- **Pattern:** Opening files without a context manager (`with open(...)`) leaves file descriptors unclosed until garbage collected.
- **Suggested Fix:**
  Use context managers:
  ```python
  with open(cache / f"{args.dataset}__baseline__native.json", encoding="utf-8") as f:
      base_c = json.load(f)
  ```

---

## 4. Inconsistencies

### 4.1 Inconsistent Negative Class Inclusion Between Card and Liner Sources
- **File / Line:** [`ml/liner_crops.py:124`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/liner_crops.py#L124) vs [`ml/liner_crops.py:69-70`](file:///Users/ninaiscool/Developer/Active/applev2/.cla
### 4.1 Inconsistent Negative Class Inclusion Between Card and Liner Sources (Continued)
- **File / Line:** [`ml/liner_crops.py:124`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/liner_crops.py#L124) vs [`ml/liner_crops.py:69-70`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/liner_crops.py#L69-L70)
- **Severity:** Medium
- **Code:**
  In `field_card_rows`:
  ```python
  label = r["label"] if r["label"] in CLASS_OF and CLASS_OF[r["label"]] not in ("other_insect", "debris") \
      else species.get((r["photo"], r["n"]), "") if r["label"] == "moth" else ""
  ```
  In `ofm_liner_rows`:
  ```python
  label = claimed if r["label"] == "moth" and claimed else r["label"]
  if label in CLASS_OF and r["ppm"]:
  ```
- **Inconsistency:**
  `ofm_liner_rows` retains non-target classes (`other_insect` and `debris`) as documented on line 11 (*"boxes labelled other_insect or debris in pass 1 count as that"*). In contrast, `field_card_rows` explicitly filters out `other_insect` and `debris`, silently discarding all non-moth bycatch and debris from field cards.
- **Suggested Fix:** Standardize handling across both sources; if non-target negatives are needed for species training, retain them consistently in both readers.

---

### 4.2 Overlapping Taxonomy and Double-Downloading in `fetch_inat.py`
- **File / Line:** [`ml/fetch_inat.py:52 & 55-60`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/fetch_inat.py#L52)
- **Severity:** Low
- **Code:**
  ```python
  "other_insect": ({"taxon_id": "47822,47201,47208,47744", "place_id": NEW_YORK}, 1200, False),
  "bycatch_fly": ({"taxon_id": 47822, "place_id": NEW_YORK}, 300, False),
  "bycatch_beetle": ({"taxon_id": 47208, "place_id": NEW_YORK}, 300, False),
  ```
- **Inconsistency:**
  `other_insect` queries taxon IDs 47822 (Diptera) and 47208 (Coleoptera), which are identically queried by `bycatch_fly` and `bycatch_beetle`. Running without `--only` downloads identical species into separate class directories, creating label redundancy.
- **Suggested Fix:** Unify the non-moth taxonomy or treat `bycatch_*` as named subsets that map to `other_insect`.

---

### 4.3 Directory Resolution Mismatch for Low-Resolution Crops
- **File / Line:** [`ml/liner_crops.py:202-205`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/liner_crops.py#L202-L205)
- **Severity:** Low
- **Code:**
  ```python
  dest = args.data / "species" / f"{ppm:g}" / r["set"] / Path(r["crop"]).name
  ...
  "ppm": f"{min(ppm, r['src_ppm']):.1f}"
  ```
- **Inconsistency:**
  PTM liners have `src_ppm = 7.0`. For `--trap-ppm 15 10`, `resolutions()` returns `[10.0]`. The crop is placed under `species/10/ptm-liners/`, but `at_trap_resolution` skips resizing (`s = 10/7 > 1`), leaving the image at 7.0 px/mm while directory nesting indicates 10 px/mm. Downstream loaders indexing solely by directory path receive mismatched spatial scales.
- **Suggested Fix:** Save under `f"{min(ppm, r['src_ppm']):g}"` or document the directory fallback convention.

---

## 5. Dead Code, Duplication, and Organization

### 5.1 JS Temporal Dead Zone Risk in `label_field_cards.py`
- **File / Line:** [`ml/label_field_cards.py:273-275`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/label_field_cards.py#L273-L275)
- **Severity:** Low
- **Code:**
  ```javascript
  fitScale = s;
  }
  let fitScale = 1;
  ```
- **Issue:** `fitScale` is assigned inside `function fit()` before its `let` declaration on line 275. If `fit()` is called synchronously before line 275 during initialization, JavaScript throws a `ReferenceError` due to TDZ.
- **Suggested Fix:** Move `let fitScale = 1;` above `function fit()`.

---

### 5.2 Orphaned Disk Crops on Manual Box Deletion
- **File / Line:** [`ml/label_field_cards.py:478`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/label_field_cards.py#L478)
- **Severity:** Low
- **Code:**
  ```javascript
  if (b.source === "manual") boxes().splice(sel, 1); else b.label = "skip";
  ```
- **Issue:** Deleting a manual box removes it from `labels.csv`, but the generated crop image (`crops/<stem>/<stem>_m<n>.jpg`) remains on disk permanently.
- **Suggested Fix:** Track deleted manual crops and unlink them in `Store.save`.

---

### 5.3 Potential `IndexError` on Empty `dataset.csv`
- **File / Line:** [`ml/make_bundle.py:87`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/make_bundle.py#L87)
- **Severity:** Low
- **Code:**
  ```python
  w = csv.DictWriter(f, fieldnames=list(rows[0]))
  ```
- **Issue:** If `data/dataset.csv` is empty, `rows` is `[]`, raising `IndexError: list index out of range`.
- **Suggested Fix:** Guard with `if not rows: return` or retrieve fieldnames from `csv.DictReader.fieldnames`.

---

## 6. Performance / Optimization Opportunities

### 6.1 Repeated Disk Scans on Debounced Saves
- **File / Line:** [`ml/label_field_cards.py:144 & 54`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/label_field_cards.py#L144)
- **Severity:** Medium
- **Code:**
  ```python
  if body["photo"] not in store.photos():
  ```
- **Issue:** On every auto-save (every 300ms during user drawing/editing), `store.photos()` executes `(self.data / "inbox").iterdir()`, reading and sorting all files in the directory.
- **Suggested Fix:** Cache photo filenames in a set in `Store.__init__` rather than hitting the filesystem on each save.

---

### 6.2 Unconditional Crop Resampling and Re-Encoding
- **File / Line:** [`ml/liner_crops.py:202-203`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/liner_crops.py#L202-L203)
- **Severity:** Medium
- **Code:**
  ```python
  at_trap_resolution(r["crop"], r["src_ppm"], ppm, dest)
  ```
- **Issue:** `at_trap_resolution()` does not check `if dest.exists(): return`. Every run re-opens, resamples, and re-compresses thousands of crops at JPEG quality 85.
- **Suggested Fix:** Skip processing if `dest.exists() and dest.stat().st_size > 0`.

---

### 6.3 Embedding Feature Cache Compression
- **File / Line:** [`ml/make_bundle.py:95`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/make_bundle.py#L95)
- **Severity:** Low
- **Code:**
  ```python
  np.savez(ml / "data/embeddings" / cache.name, ...)
  ```
- **Issue:** Uncompressed `.npz` storage inflates bundle size when transferring to GPU machines.
- **Suggested Fix:** Use `np.savez_compressed`.

---

## 7. Test Coverage Gaps

1. **Box Overlap and Filtering Logic (`ml/import_roboflow_labels.py`):** No unit tests for `overlaps()`. The inverted `and` logic error in center containment went undetected.
2. **Concurrent State & ID Management (`ml/label_field_cards.py`):** No automated tests verifying concurrent debounced saves, server ID assignments (`next_n`), and manual box deletions.
3. **Split and Holdout Consistency (`ml/liner_crops.py`):** No tests verifying that cards in `test_cards.txt` and groups in `TEST_GROUPS` actually get marked `split == "test"`.
4. **Bundle Path Rewrites (`ml/make_bundle.py`):** No tests verifying that absolute paths originating outside `ml/` are correctly made relative without crashing.

---

## Prioritized Next Steps

1. **Fix `overlaps()` logic in [`ml/import_roboflow_labels.py:38`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/import_roboflow_labels.py#L38):** Replace `and` with `or` so enclosed detector boxes are properly filtered out.
2. **Prevent test set data leakage in [`ml/liner_crops.py:195`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/liner_crops.py#L195):** Replace `setdefault` with `r["held_out"] = r.get("held_out", False) or any(...)`.
3. **Fix test card stem matching in [`ml/liner_crops.py:129`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/liner_crops.py#L129):** Support stems without extension when checking `held`.
4. **Fix save race condition in [`ml/label_field_cards.py:368`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/label_field_cards.py#L368):** Track temporary client IDs so in-flight modifications do not discard server-assigned box IDs.
5. **Handle project-root paths in [`ml/make_bundle.py:44`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/ml/make_bundle.py#L44):** Catch `ValueError` when paths are relative to workspace root rather than `ml/`.
6. **Add explicit `encoding="utf-8"`** to all file opens across `ml/` to prevent locale-dependent crashes.
