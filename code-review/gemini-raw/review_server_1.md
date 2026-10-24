This is a read-only code review of **Chunk 2 of 5** (`server/sentinel_server/evaluate.py`, `server/sentinel_server/models.py`, `server/sentinel_server/phenology.py`, `server/sentinel_server/pipeline/__init__.py`, and `server/sentinel_server/pipeline/classify.py`).

---

### 1. Bugs (Correctness, Crashes, Edge Cases, Data Loss)

#### Finding 1.1: `photo_stats` crashes with `TypeError` when JSON `meta` contains `null` values
- **Location:** [server/sentinel_server/evaluate.py:221-222](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L221-L222) in [`photo_stats`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L209-L223)
- **Severity:** High
- **Code:**
```python
221|             "max_glare": max((m.get("glare", 0.0) for m in used), default=0.0),
222|             "oldest_liner_days": max((m.get("liner_days", 0.0) for m in used), default=0.0)}
```
- **Concrete Failure Scenario:** [`Capture.meta`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/models.py#L87) stores arbitrary JSON metadata. If a capture has `{"glare": null}` or `{"liner_days": null}` (e.g. when glare detection failed or liner age was not calculated), `m.get("glare", 0.0)` returns `None` (because the key exists in the dictionary, so the default argument `0.0` is ignored). Calling `max(...)` over a sequence containing both `float` and `None` raises `TypeError: '>' not supported between instances of 'NoneType' and 'float'`, crashing `sentinel-server evaluate`.
- **Suggested Fix:**
Coalesce `None` values using `or 0.0`:
```python
"max_glare": max((m.get("glare") or 0.0 for m in used), default=0.0),
"oldest_liner_days": max((m.get("liner_days") or 0.0 for m in used), default=0.0)}
```

---

#### Finding 1.2: Cards with zero catches fail accuracy evaluation and zero-manual cards with false positives are skipped
- **Location:** [server/sentinel_server/evaluate.py:66-67](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L66-L67) in [`count_accuracy`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L66-L67) and [server/sentinel_server/evaluate.py:165](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L165)
- **Severity:** High
- **Code:**
```python
66| def count_accuracy(auto: float, manual: float) -> float | None:
67|     return None if manual == 0 else 1 - abs(auto - manual) / manual
...
165|                     "accuracy": acc, "pass": acc is not None and acc >= rep.targets.count,
```
- **Concrete Failure Scenario:**
  1. A sticky liner card has 0 moths manually counted and 0 moths detected automatically (`manual == 0`, `auto == 0`). This represents 100% counting accuracy. However, `count_accuracy(0, 0)` returns `None`. Line 165 checks `acc is not None and acc >= rep.targets.count`, which evaluates to `False`. When generating the summary at line 307 (`passed = sum(r["pass"] ...)`), perfectly accurate 0-catch cards are reported as **FAIL**.
  2. If a card has `manual == 0` but `auto == 10` (10 false positives), `count_accuracy` also returns `None` instead of `0.0` (or negative).
- **Suggested Fix:**
```python
def count_accuracy(auto: float, manual: float) -> float | None:
    if manual == 0:
        return 1.0 if auto == 0 else 0.0
    return 1 - abs(auto - manual) / manual
```

---

#### Finding 1.3: Unhandled `AttributeError` if `Card` references a missing or orphaned `Trap`
- **Location:** [server/sentinel_server/evaluate.py:194-195](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L194-L195) in [`evaluate`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L134-L206)
- **Severity:** Medium
- **Code:**
```python
194|             trap = db.get(Trap, trap_id)
195|             manual_dates = sorted(d for cid in cids for d, label, n in counts[cid] if label == trap.lure for _ in range(n))
```
- **Concrete Failure Scenario:** If a trap record was deleted or SQLite foreign key constraints were not enforced when records were created, `db.get(Trap, trap_id)` returns `None`. Line 195 directly accesses `trap.lure` without a `None` check, crashing the entire evaluation run with `AttributeError: 'NoneType' object has no attribute 'lure'`.
- **Suggested Fix:**
Guard against missing traps:
```python
trap = db.get(Trap, trap_id)
if trap is None:
    continue
```

---

#### Finding 1.4: Floating-point precision error in `be_degree_days` causes unhandled `ValueError: math domain error`
- **Location:** [server/sentinel_server/phenology.py:24](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/phenology.py#L24) in [`be_degree_days`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/phenology.py#L14-L26)
- **Severity:** High
- **Code:**
```python
23|     amp = (tmax_f - tmin_f) / 2
24|     theta = math.asin((base_f - mean) / amp)
25|     return ((mean - base_f) * (math.pi / 2 - theta) + amp * math.cos(theta)) / math.pi
```
- **Concrete Failure Scenario:** When `base_f` is within floating-point epsilon of `tmax_f` or `tmin_f` (e.g. `tmin_f = 49.99999999999999`, `tmax_f = 50.00000000000001`, `base_f = 50.0`), IEEE-754 arithmetic rounding can cause `(base_f - mean) / amp` to evaluate to `1.0000000000000002` or `-1.0000000000000002`. Passing any value strictly outside `[-1.0, 1.0]` into `math.asin` raises `ValueError: math domain error`, terminating degree-day computation unexpectedly.
- **Suggested Fix:**
Clamp the argument to `[-1.0, 1.0]`:
```python
ratio = max(-1.0, min(1.0, (base_f - mean) / amp))
theta = math.asin(ratio)
```

---

#### Finding 1.5: `daily_extremes_f` crashes with `TypeError` when reading temperatures from captures with `temp_c = None`
- **Location:** [server/sentinel_server/phenology.py:120](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/phenology.py#L120) in [`daily_extremes_f`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/phenology.py#L115-L121)
- **Severity:** Medium
- **Code:**
```python
118|     per_day: dict[date, list[float]] = {}
119|     for d, c in readings:
120|         per_day.setdefault(d, []).append(c * 9 / 5 + 32)
```
- **Concrete Failure Scenario:** In [`Capture`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/models.py#L71), `temp_c` is defined as `Mapped[float | None] = mapped_column(Float, nullable=True)`. When a trap has no sensor or fails to read temperature, `temp_c` is `None`. If callers pass `(capture_date, capture.temp_c)` into [`daily_extremes_f`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/phenology.py#L115-L121), `c * 9 / 5 + 32` raises `TypeError: unsupported operand type(s) for *: 'NoneType' and 'int'`.
- **Suggested Fix:**
Filter out `None` readings:
```python
for d, c in readings:
    if c is not None:
        per_day.setdefault(d, []).append(c * 9 / 5 + 32)
```

---

#### Finding 1.6: Division by zero when temperature `T` is 0.0 in model logits calibration
- **Location:** [server/sentinel_server/pipeline/classify.py:88](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L88) in [`linear_head_probs`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L86-L92) and [server/sentinel_server/pipeline/classify.py:134](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L134) in [`FineTunedCNN.classify`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L128-L135)
- **Severity:** Medium
- **Code:**
```python
88|     logits = (feats @ W.T + b) / T
...
134|             p = (self.model(x) / self.T).softmax(dim=-1).cpu().numpy()
```
- **Concrete Failure Scenario:** If a head file (`head.npz`) or CNN checkpoint stores `T = 0.0` or invalid values, dividing logits by `T` produces `NaN` and `Inf` values (`RuntimeWarning: divide by zero encountered in divide`), resulting in corrupted probabilities and invalid downstream classifications.
- **Suggested Fix:**
Validate that `T` is strictly positive:
```python
self.T = max(float(ck.get("T", 1.0)), 1e-6)
```

---

#### Finding 1.7: `open()` calls without explicit encoding cause platform-dependent `UnicodeDecodeError`
- **Location:** [server/sentinel_server/evaluate.py:94](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L94) and [server/sentinel_server/evaluate.py:102](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L102)
- **Severity:** Low
- **Code:**
```python
94|     with open(path, newline="") as f:
...
102|     with open(path, newline="") as f:
```
- **Concrete Failure Scenario:** Reading CSV truth files with non-ASCII characters (e.g. utf-8 notes, degree symbols, or en-dashes) on systems where the locale is not UTF-8 (or in non-UTF-8 container runtimes) raises `UnicodeDecodeError`.
- **Suggested Fix:**
Add `encoding="utf-8"`:
```python
with open(path, newline="", encoding="utf-8") as f:
```

---

### 2. Security Issues

#### Finding 2.1: Arbitrary code execution via `weights_only=False` in `torch.load`
- **Location:** [server/sentinel_server/pipeline/classify.py:116](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L116) in [`FineTunedCNN.__init__`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L112-L126)
- **Severity:** High
- **Code:**
```python
116|         ck = torch.load(model_path, map_location="cpu", weights_only=False)
```
- **Concrete Failure Scenario:** PyTorch checkpoints deserialized with `weights_only=False` use Python's standard `pickle` engine without restrictions. If a model file path specified via `SENTINEL_CLASSIFIER_MODEL` is tampered with, loaded from a shared filesystem, or downloaded from an untrusted bucket, unpickling triggers arbitrary Python code execution (RCE) with the full permissions of the server process. Note that [`BioClipLinear`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L95-L109) safely uses `allow_pickle=False` at line 97, but `FineTunedCNN` explicitly opts out of PyTorch 2.4+'s default safe behavior.
- **Suggested Fix:**
Use `weights_only=True`:
```python
ck = torch.load(model_path, map_location="cpu", weights_only=True)
```
If standard Python primitives like lists and strings are in the checkpoint dictionary, PyTorch's `weights_only=True` loader supports them natively.

---

#### Finding 2.2: SQL `LIKE` wildcard injection in `Capture.image_path.like`
- **Location:** [server/sentinel_server/evaluate.py:240](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L240) in [`detection_scores`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L230-L294)
- **Severity:** Medium
- **Code:**
```python
240|         cap = db.scalar(select(Capture).where(Capture.image_path.like(f"%{photo}")))
```
- **Concrete Failure Scenario:** According to the docstring (line 34), standard capture photo filenames follow the format `20260924T175641Z_T1.jpg`. Underscores (`_`) are special single-character wildcards in SQL `LIKE` expressions. Because `photo` is unescaped, `_T1.jpg` matches `_T1.jpg`, `_T2.jpg`, etc. If photo filenames contain `%` or `_`, queries match unintended capture records.
- **Suggested Fix:**
Escape LIKE wildcard characters, match on exact file basename, or use `Capture.image_path.endswith(photo)`.

---

### 3. Deprecated APIs / Outdated Patterns

#### Finding 3.1: Deprecated and non-standard datetime naive UTC helper
- **Location:** [server/sentinel_server/models.py:27-28](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/models.py#L27-L28)
- **Severity:** Low
- **Code:**
```python
27| def utcnow() -> datetime:
28|     return datetime.now(timezone.utc).replace(tzinfo=None)
```
- **Failure Scenario / Pattern Issue:** Python 3.12+ deprecated `datetime.utcnow()` in favor of timezone-aware datetimes (`datetime.now(timezone.utc)`). The project correctly avoids `datetime.utcnow()`, but stripping `tzinfo` with `.replace(tzinfo=None)` re-creates naive datetimes across all database columns. Naive datetimes are prone to subtle timezone bugs when mixed with local dates (such as in `services.local_date(card.installed_at)` in `evaluate.py:180`).
- **Suggested Fix:**
Store timezone-aware datetimes in SQLAlchemy with `DateTime(timezone=True)` or standard ISO 8601 strings.

---

### 4. Inconsistencies

#### Finding 4.1: `Track.reviewed` returns `False` when a track is confirmed without changing its label
- **Location:** [server/sentinel_server/models.py:129-133](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/models.py#L129-L133) in [`Track`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/models.py#L95-L133)
- **Severity:** Medium
- **Code:**
```python
117|     # auto: confident model label; review: needs a person; unknown: model can't tell;
118|     # confirmed / relabelled by a person; rejected: not an insect
119|     review_status: Mapped[str] = mapped_column(String(16), default="review", index=True)
120|     reviewed_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
...
129|     @property
130|     def reviewed(self) -> bool:
131|         """A person labelled or rejected it: the model no longer changes its label or count."""
132|         return self.reviewed_label is not None or self.review_status == "rejected"
```
- **Concrete Failure Scenario:** The docstring and comments state that `review_status` can be `"confirmed"` when confirmed by a person without relabelling. When a reviewer confirms the model's species prediction, `reviewed_label` remains `None` while `review_status` is updated to `"confirmed"`. However, [`Track.reviewed`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/models.py#L130) only checks `reviewed_label is not None or self.review_status == "rejected"`. It returns `False`, allowing automated background jobs or tracking updates to alter a human-confirmed track.
- **Suggested Fix:**
Include `"confirmed"` in the check:
```python
@property
def reviewed(self) -> bool:
    return self.reviewed_label is not None or self.review_status in ("rejected", "confirmed")
```

---

#### Finding 4.2: Confusing duplicate state name `"confirmed"` in `status` and `review_status`
- **Location:** [server/sentinel_server/models.py:107](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/models.py#L107) and [server/sentinel_server/models.py:119](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/models.py#L119)
- **Severity:** Low
- **Code:**
```python
106|     # candidate: seen once; confirmed: seen in 2+ photos (counted); dropped: vanished while a candidate
107|     status: Mapped[str] = mapped_column(String(16), default="candidate", index=True)
...
118|     # confirmed / relabelled by a person; rejected: not an insect
119|     review_status: Mapped[str] = mapped_column(String(16), default="review", index=True)
```
- **Failure Scenario / Inconsistency:** Both columns use the state string `"confirmed"` with completely different semantics (multi-frame pipeline detection confirmation vs manual human review confirmation). In queries and filters (such as `evaluate.py:145` `auto_counts(tracks, {"confirmed"})` vs `evaluate.py:123` `review_status != "rejected"`), this homonym creates high cognitive load and high probability of subtle query bugs.
- **Suggested Fix:**
Rename the review status value to `"human_verified"` or `"approved"`.

---

#### Finding 4.3: Discrepancy in `PESTS` and `SPECIES` constants across modules
- **Location:** [server/sentinel_server/models.py:23](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/models.py#L23) and [server/sentinel_server/evaluate.py:53-54](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L53-L54)
- **Severity:** Low
- **Code:**
```python
# models.py
23| PESTS = ["CM", "OFM", "OBLR"]

# evaluate.py
53| PESTS = ("CM", "OFM", "OBLR")
54| MOTHS = {"CM", "OFM", "OBLR", "other_moth", "unclassified"}
```
- **Failure Scenario / Inconsistency:** `evaluate.py` redefines `PESTS` as a tuple instead of importing `PESTS` from `models.py`. In addition, `models.SPECIES_LABELS` contains `"unclassified"`, but `models.SPECIES` excludes it while `evaluate.MOTHS` includes it.
- **Suggested Fix:**
Import `PESTS` directly from `models.py` in `evaluate.py` to maintain a single source of truth.

---

### 5. Dead Code, Duplication, and Architecture

#### Finding 5.1: CUDA is completely unsupported in classifier device selection
- **Location:** [server/sentinel_server/pipeline/classify.py:57](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L57) in [`_BioClip`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L48-L68) and [server/sentinel_server/pipeline/classify.py:120](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L120) in [`FineTunedCNN`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L111-L136)
- **Severity:** Medium
- **Code:**
```python
57|         self.device = "mps" if torch.backends.mps.is_available() else "cpu"
...
120|         self.device = "mps" if torch.backends.mps.is_available() else "cpu"
```
- **Concrete Failure Scenario:** When running the server or ML evaluation on any Linux workstation or cloud server with an NVIDIA GPU (AWS, GCP, etc.), `torch.backends.mps.is_available()` returns `False`. The code falls back directly to `"cpu"`, completely ignoring `torch.cuda.is_available()`. Model inference runs 10x–50x slower on CPU despite available CUDA hardware.
- **Suggested Fix:**
Support CUDA, MPS, and CPU properly:
```python
if torch.cuda.is_available():
    self.device = "cuda"
elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
    self.device = "mps"
else:
    self.device = "cpu"
```

---

#### Finding 5.2: Repeated inner-loop lambda allocation in `evaluate`
- **Location:** [server/sentinel_server/evaluate.py:147](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L147) in [`evaluate`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L134-L206)
- **Severity:** Low
- **Code:**
```python
147|         moths = lambda c: sum(v for k, v in c.items() if k in MOTHS)  # noqa: E731
```
- **Failure Scenario / Antipattern:** The lambda `moths` is defined inside the `for cid in cards:` loop on every iteration, re-instantiating a function object for every liner card and requiring `# noqa: E731` to suppress linter warnings.
- **Suggested Fix:**
Define `_moth_count(c: Counter) -> int` once at module scope.

---

### 6. Performance & Optimization Opportunities

#### Finding 6.1: N+1 queries and full table scans in `detection_scores`
- **Location:** [server/sentinel_server/evaluate.py:240](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L240), [server/sentinel_server/evaluate.py:246](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L246), [server/sentinel_server/evaluate.py:262](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L262), [server/sentinel_server/evaluate.py:274](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L274)
- **Severity:** Medium
- **Code:**
```python
239|     for photo, rows in sorted(boxes.items()):
240|         cap = db.scalar(select(Capture).where(Capture.image_path.like(f"%{photo}")))
...
246|         dets = list(db.scalars(select(Detection).where(Detection.capture_id == cap.id)))
...
262|             track = db.get(Track, dets[j].track_id) if dets[j].track_id else None
...
274|             track = db.get(Track, d.track_id) if d.track_id else None
```
- **Concrete Failure Scenario:**
  1. `Capture.image_path.like(f"%{photo}")` has a leading wildcard `%` and cannot use any B-tree index on `image_path`. This forces a full table scan of the `captures` table for every photo in `boxes.csv`.
  2. Inside the matching loop, `db.get(Track, ...)` issues individual point-lookups for every detection rather than pre-fetching or joining tracks. For an evaluation dataset with hundreds of photos and thousands of detections, this executes thousands of individual round-trips to the database.
- **Suggested Fix:**
Pre-fetch capture paths and tracks into in-memory dictionaries:
```python
capture_by_name = {Path(c.image_path).name: c for c in db.scalars(select(Capture))}
```

---

#### Finding 6.2: `classes.index(s)` called repeatedly inside nested loop in classifier probabilities
- **Location:** [server/sentinel_server/pipeline/classify.py:92](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L92) and [server/sentinel_server/pipeline/classify.py:135](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L135)
- **Severity:** Low
- **Code:**
```python
92|     return [{s: float(row[classes.index(s)]) if s in classes else 0.0 for s in SPECIES} for row in p]
```
- **Performance Issue:** `classes.index(s)` performs a linear search over `classes` for every species in `SPECIES` for every crop in `p`.
- **Suggested Fix:**
Pre-compute a mapping of `{s: classes.index(s) for s in SPECIES if s in classes}` once before iterating over `p`.

---

### 7. Test Coverage Gaps

#### Finding 7.1: Zero unit test coverage for ML classification pipelines due to blanket `# pragma: no cover`
- **Location:** [server/sentinel_server/pipeline/classify.py:48](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L48), [server/sentinel_server/pipeline/classify.py:70](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L70), [server/sentinel_server/pipeline/classify.py:95](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L95), [server/sentinel_server/pipeline/classify.py:111](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L111)
- **Severity:** Medium
- **Issue:** All four model classes ([`_BioClip`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L48-L68), [`BioClipZeroShot`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L70-L84), [`BioClipLinear`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L95-L109), and [`FineTunedCNN`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L111-L136)) are marked `# pragma: no cover`. While downloading multi-gigabyte foundation model weights in CI is understandably avoided, critical mathematical routines such as [`linear_head_probs`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L86-L92), [`crop`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L34-L39), [`make_classifier`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L138-L153) error handling, and temperature scaling have no mock-based unit tests.
- **Suggested Fix:**
Add isolated unit tests using synthetic NumPy arrays and mock state dictionaries to verify temperature calibration, probability output shapes, and edge cases.

---

### Prioritized Next Steps

1. **Fix `photo_stats` crash on null glare/liner_days metadata:** Coalesce with `(m.get(...) or 0.0)` in [server/sentinel_server/evaluate.py:221-222](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L221-L222).
2. **Correct counting accuracy metric for zero-catch cards:** Update [`count_accuracy`](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/evaluate.py#L66-L67) in `evaluate.py` so clean cards with 0 manual and 0 auto detections evaluate to `1.0` (PASS) instead of `None` (FAIL).
3. **Mitigate arbitrary code execution in checkpoint loading:** Change `weights_only=False` to `weights_only=True` in [server/sentinel_server/pipeline/classify.py:116](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L116).
4. **Prevent floating-point `math.asin` domain crash:** Clamp `(base_f - mean) / amp` to `[-1.0, 1.0]` in [server/sentinel_server/phenology.py:24](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/phenology.py#L24).
5. **Support CUDA hardware acceleration:** Update device discovery in [server/sentinel_server/pipeline/classify.py:57](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/pipeline/classify.py#L57) and `classify.py:120` to check `torch.cuda.is_available()`.
6. **Fix `Track.reviewed` property:** Update [server/sentinel_server/models.py:132](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/models.py#L132) to recognize `review_status == "confirmed"`.
