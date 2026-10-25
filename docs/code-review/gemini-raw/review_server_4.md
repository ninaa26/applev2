Here is the thorough code review for the test files in scope (Chunk 5 of 5).

---

### 1. BUGS (Correctness, Crashes, Race Conditions, Timezone/Date Errors)

---

#### Finding 1.1: `UnboundLocalError` in concurrency test teardown masks real test failures
- **File & Line**: `server/tests/test_pipeline.py:455-465` (and `505-514`)
- **Severity**: **High**
- **Quote**:
  ```python
  455|         try:
  456|             assert pipeline.classifier.started.wait(30)
  457|             result = {}
  458|             up = threading.Thread(target=lambda: result.update(r=upload(client, key, now, MOTHS, "during")))
  459|             up.start()
  460|             up.join(5)  # with the lock held, this waits for the busy timeout instead
  461|             assert not up.is_alive() and result["r"].status_code == 201
  462|         finally:
  463|             pipeline.classifier.release.set()
  464|             worker.join(30)
  465|             up.join(60)
  ```
- **Concrete Failure Scenario**: If line 456 (`pipeline.classifier.started.wait(30)`) times out or fails (e.g., on a slow CI runner), Python immediately jumps to the `finally:` block. At line 465, `up.join(60)` is called, but the local variable `up` has not been assigned yet. Python raises `UnboundLocalError: cannot access local variable 'up' where it is not associated with a value`, replacing and masking the underlying assertion error. The identical bug exists in lines 505–514 of `test_upload_commits_while_a_liner_is_reprocessed`.
- **Suggested Fix**: Initialize `up = None` before the `try` block and guard the join:
  ```python
  up = None
  try:
      ...
  finally:
      pipeline.classifier.release.set()
      worker.join(30)
      if up is not None:
          up.join(60)
  ```

---

#### Finding 1.2: Missing directory creation and unsafe unlinking in `test_old_database_gets_new_columns`
- **File & Line**: `server/tests/test_pipeline.py:264-266`
- **Severity**: **High**
- **Quote**:
  ```python
  264|     path = tmp_path / "data" / "sentinel.db"
  265|     path.unlink()
  266|     con = sqlite3.connect(path)
  ```
- **Concrete Failure Scenario**: `tmp_path` is a freshly provisioned temporary directory. The subdirectory `tmp_path / "data"` does not exist. Calling `path.unlink()` without `missing_ok=True` raises `FileNotFoundError: [Errno 2] No such file or directory: '.../data/sentinel.db'`. Furthermore, calling `sqlite3.connect(path)` when the parent directory `data` does not exist raises `sqlite3.OperationalError: unable to open database file`.
- **Suggested Fix**: Create the parent folder and pass `missing_ok=True`:
  ```python
  path = tmp_path / "data" / "sentinel.db"
  path.parent.mkdir(parents=True, exist_ok=True)
  path.unlink(missing_ok=True)
  ```

---

#### Finding 1.3: Season-boundary date bug in biofix test causing failures in early January
- **File & Line**: `server/tests/test_review_policy.py:51-55`
- **Severity**: **High**
- **Quote**:
  ```python
  51|     ids = trap_with_tracks([("CM", 0.6, "review", 12), ("CM", 0.4, "unknown", 11),
  52|                             ("CM", 0.95, "auto", 5), ("CM", 0.95, "auto", 4)])
  53|     with session_scope() as db:
  54|         s = services.phenology_status(db, db.get(Trap, "T1"))
  55|         assert s["biofix"] is not None and s["biofix_sure"] is None and s["unsure_catches"] == 2
  ```
- **Concrete Failure Scenario**: `services.phenology_status()` filters catches to the current season/calendar year (as verified by lines 66–71: `test_biofix_comes_from_this_seasons_catches_only`). If this test runs between January 1 and January 11, `utcnow() - timedelta(days=12)` and `utcnow() - timedelta(days=11)` fall into the previous calendar year (December). They are filtered out as last season's catches, resulting in `s["unsure_catches"] == 0` and `s["biofix"] is None`, failing `assert s["biofix"] is not None`.
- **Suggested Fix**: Use explicit fixed calendar dates during the growing season (e.g., June 2026, as in `test_evaluate.py`) or mock `utcnow()` to a stable mid-season date.

---

#### Finding 1.4: Global Settings singleton state leakage across test cases
- **File & Line**: `server/tests/test_pipeline.py:89-90` and `433-434`
- **Severity**: **Medium**
- **Quote**:
  ```python
  89|     monkeypatch.setenv("SENTINEL_DASHBOARD_PASSWORD", "orchard")
  90|     settings_mod.reset_settings()
  ```
  and
  ```python
  433|     monkeypatch.setenv("SENTINEL_LINER_MAX_DAYS", "-1")  # every photo raises "card_old" before classifying
  434|     settings_mod.reset_settings()
  ```
- **Concrete Failure Scenario**: While pytest's `monkeypatch` fixture restores `os.environ` after the test completes, it does not call `settings_mod.reset_settings()`. The cached `Settings` singleton continues to hold `dashboard_password="orchard"` or `liner_max_days=-1` for subsequent tests executing in the same worker process, leading to cascading failures (spurious 401 Unauthorized errors or premature `card_old` event creation).
- **Suggested Fix**: Use a `try/finally` block or create an autouse fixture that resets settings after the test:
  ```python
  try:
      ...
  finally:
      settings_mod.reset_settings()
  ```

---

#### Finding 1.5: Silent assertion bypass for empty UID
- **File & Line**: `server/tests/test_pipeline.py:302-305`
- **Severity**: **Medium**
- **Quote**:
  ```python
  302|         for uid in ("../../../../escaped", "a/b", ".hidden", ""):
  303|             r = upload(client, key, now, MOTHS, uid)
  304|             if uid:
  305|                 assert r.status_code == 422, uid
  ```
- **Concrete Failure Scenario**: When `uid == ""`, the conditional `if uid:` evaluates to `False`, silently skipping the `assert r.status_code == 422` statement. If an empty UID is accepted by the server or triggers an unhandled 500 error, the test passes without verifying the status code.
- **Suggested Fix**: Remove the `if uid:` check so that all test cases are validated, or explicitly assert the expected response for empty UIDs:
  ```python
  for uid in ("../../../../escaped", "a/b", ".hidden", ""):
      r = upload(client, key, now, MOTHS, uid)
      assert r.status_code == 422, f"Failed for uid={uid!r}"
  ```

---

#### Finding 1.6: Race condition between default background worker and synchronous `process_pending`
- **File & Line**: `server/tests/test_pipeline.py:106, 111` (compared with line 340)
- **Severity**: **Medium**
- **Quote**:
  ```python
  106|     with TestClient(create_app()) as client:
  ...
  111|         assert process_pending(Pipeline(), limit=10) == 4
  ```
  versus:
  ```python
  340|     with TestClient(create_app(start_worker=False)) as client:
  ```
- **Concrete Failure Scenario**: Line 340 explicitly specifies `start_worker=False`. In `test_counts_each_insect_once_and_new_card_resets` (line 106) and other tests in `test_pipeline.py`, `create_app()` is called without `start_worker=False`. If `create_app()` spawns a background worker thread on startup, that worker races against the synchronous `process_pending()` calls in the test. If the background worker claims the jobs first, `process_pending(Pipeline(), limit=10)` returns 0 instead of 4, causing intermittent test flakiness.
- **Suggested Fix**: Consistently pass `start_worker=False` whenever `process_pending()` is invoked manually in tests.

---

### 2. Security Issues

---

#### Finding 2.1: Lack of CSRF protection on trap management endpoints
- **File & Line**: `server/tests/test_manage.py:23, 53, 59, 62`
- **Severity**: **Medium**
- **Quote**:
  ```python
  23|     r = client.post("/manage/traps", data={"name": "", "block": "", "lure": "CM", **form})
  ...
  53|         client.post("/manage/traps/T2/remove")
  ...
  59|         client.post("/manage/traps/T2/restore")
  ...
  62|         r = client.post("/manage/traps/T2/new-key")
  ```
- **Concrete Failure Scenario**: All state-modifying trap management actions (trap registration, removal, restoration, and API key regeneration) accept plain HTML form POST requests with no CSRF tokens or anti-CSRF headers. An attacker hosting a malicious site can submit a cross-origin form to `/manage/traps/T2/new-key` or `/manage/traps/T2/remove`, disconnecting cameras or modifying trap configurations on an authenticated farm dashboard.
- **Suggested Fix**: Implement CSRF tokens on dashboard forms or enforce strict `SameSite=Lax`/`SameSite=Strict` cookie policies and custom verification headers on state-changing management routes.

---

### 3. Deprecated APIs / Outdated Patterns

---

#### Finding 3.1: Deprecated `utcnow` import and usage
- **File & Line**: `server/tests/test_review_policy.py:10, 20, 25`
- **Severity**: **Low**
- **Quote**:
  ```python
  10| from sentinel_server.models import Capture, Card, Track, Trap, utcnow
  ...
  20|         cap = Capture(trap_id="T1", card_id=card.id, uid="c1", captured_at=utcnow(), image_path="x.jpg")
  ...
  25|             when = utcnow() - timedelta(days=days)
  ```
- **Concrete Failure Scenario**: `datetime.utcnow()` has been deprecated since Python 3.12 (`DeprecationWarning: datetime.datetime.utcnow() is deprecated and scheduled for removal in a future version`). While `test_pipeline.py` and `test_manage.py` use `datetime.now(timezone.utc)`, `test_review_policy.py` relies on `utcnow()`.
- **Suggested Fix**: Replace `utcnow()` with timezone-aware `datetime.now(timezone.utc)` (or `datetime.now(timezone.utc).replace(tzinfo=None)` if naive UTC timestamps are required by the SQLite schema).

---

### 4. Inconsistencies

---

#### Finding 4.1: Inconsistent domain attribute naming: `Track.label` vs `Track.species`
- **File & Line**: `server/tests/test_pipeline.py:218` vs `server/tests/test_evaluate.py:35` and `server/tests/test_review_policy.py:27`
- **Severity**: **Low**
- **Quote**:
  `test_pipeline.py:218`:
  ```python
  218|             assert db.get(Track, ids[1]).label == "other_insect"
  ```
  `test_evaluate.py:35`:
  ```python
  35|                       x1=box[0], y1=box[1], x2=box[2], y2=box[3], prob_sum={}, species=label, review_status=review,
  ```
  `test_review_policy.py:27`:
  ```python
  27|                       x1=0, y1=0, x2=10, y2=10, species=species, species_conf=conf, review_status=status)
  ```
- **Concrete Failure Scenario**: `Track` models are constructed with `species=...`, but queried in assertions as `track.label`. If `label` is an unmapped property or alias, any refactoring of the SQLAlchemy model that drops this alias will cause `AttributeError` on line 218.
- **Suggested Fix**: Standardize on a single attribute name (either `species` or `label`) across model definitions, form handlers, and test assertions.

---

#### Finding 4.2: Codling Moth (CM) phenology model milestone cut-off at 250 DD
- **File & Line**: `server/tests/test_phenology.py:44-45`
- **Severity**: **Low**
- **Quote**:
  ```python
  44|     assert ph.next_milestone(cm, 230).dd == 250
  45|     assert ph.next_milestone(cm, 300) is None
  ```
- **Concrete Failure Scenario**: For Codling Moth, 250 DD (base 50°F) corresponds only to first-generation egg hatch. In standard agricultural phenology models (e.g., NEWA/UC IPM), CM models track subsequent generations (second flight ~1000 DD, third flight ~2100 DD). Returning `None` for DD > 250 stops phenology tracking after mid-June.
- **Suggested Fix**: Extend `MODELS["CM"]` in `phenology.py` to support later-season generational milestones.

---

### 5. Dead Code / Organization Problems

---

#### Finding 5.1: Unused `capsys` fixture parameter
- **File & Line**: `server/tests/test_evaluate.py:90`
- **Severity**: **Low**
- **Quote**:
  ```python
  90| def test_detection_scores_and_cli_report(tmp_path, capsys):
  ```
- **Concrete Failure Scenario**: The fixture `capsys` is requested in the test signature but never used; the test validates the output by reading `out.read_text()` directly.
- **Suggested Fix**: Remove `capsys` from the function signature:
  ```python
  def test_detection_scores_and_cli_report(tmp_path):
  ```

---

#### Finding 5.2: Fragile HTML string splitting in dashboard assertions
- **File & Line**: `server/tests/test_manage.py:56, 120, 138`
- **Severity**: **Low**
- **Quote**:
  ```python
  56|         assert "/traps/T2" not in client.get("/").text.split("Recent events")[0]  # gone from the trap table
  ...
  120|         assert "/traps/T2" in table and "/traps/T1" not in table  # the hub has no row of counts
  ...
  138|         assert "Offline" in client.get("/").text.split("Each trap")[0]
  ```
- **Concrete Failure Scenario**: Splitting rendered HTML on verbatim UI text like `"Recent events"` or `"Each trap"` makes tests brittle. Any minor copy change or HTML structure update causes an unhandled `IndexError: list index out of range` or false negatives.
- **Suggested Fix**: Use CSS selectors or an HTML parser (e.g., BeautifulSoup) to assert the presence or absence of specific trap IDs within targeted DOM containers (e.g., `#trap-table`).

---

### 6. Performance Opportunities

---

#### Finding 6.1: Redundant mutating HTTP request in key rotation test
- **File & Line**: `server/tests/test_manage.py:110-111`
- **Severity**: **Low**
- **Quote**:
  ```python
  110|         assert "/etc/sentinel/config.toml" in client.post("/manage/traps/T1/new-key").text
  111|         hub_key = re.search(r'api_key = "([^"]+)"', client.post("/manage/traps/T1/new-key").text).group(1)
  ```
- **Concrete Failure Scenario**: Calling `/manage/traps/T1/new-key` twice triggers two separate cryptographic key generations, hash calculations, and database commits. The key generated at line 110 is immediately invalidated by line 111.
- **Suggested Fix**: Capture the response once:
  ```python
  res = client.post("/manage/traps/T1/new-key")
  assert "/etc/sentinel/config.toml" in res.text
  hub_key = re.search(r'api_key = "([^"]+)"', res.text).group(1)
  ```

---

#### Finding 6.2: 50 full HTTP image uploads in a single unit test
- **File & Line**: `server/tests/test_manage.py:80-81`
- **Severity**: **Low**
- **Quote**:
  ```python
  80|         for i in range(50):
  81|             assert _upload(client, k2, "T2", f"p{i:02d}", start + timedelta(hours=i)).status_code == 201
  ```
- **Concrete Failure Scenario**: Running 50 end-to-end multipart POST uploads with PIL JPEG generation solely to test photo gallery pagination (48 items per page) adds several seconds of disk I/O and HTTP overhead to the test suite.
- **Suggested Fix**: Seed 50 `Capture` records directly into SQLite using `db.add_all()` and use HTTP uploads only for tests verifying the upload endpoint itself.

---

### 7. Test Coverage Gaps

---

#### Finding 7.1: Minimal coverage for application settings
- **File & Line**: `server/tests/test_settings.py:1-30`
- **Severity**: **Medium**
- **Failure Scenario**: `test_settings.py` only tests `.env` comment parsing and the `SENTINEL_LENS_K` option. Core configuration parameters—such as database URL formatting, `SENTINEL_DATA_DIR` directory creation, invalid/out-of-range port numbers, missing required environment variables, and fallback defaults—are entirely unexercised.
- **Suggested Fix**: Add test cases verifying default values and validation error handling across all fields in `Settings`.

---

#### Finding 7.2: Unhandled empty reading lists in `daily_extremes_f`
- **File & Line**: `server/tests/test_phenology.py:48-51`
- **Severity**: **Low**
- **Failure Scenario**: `daily_extremes_f` is only tested with a populated list of readings. If a trap has days with zero temperature readings or readings missing temperature floats, passing an empty sequence could raise `ValueError: max() arg is an empty sequence`.
- **Suggested Fix**: Add unit tests for edge cases: empty input `[]`, negative temperatures, and readings with missing values.

---

### Prioritized Next Steps

1. **Fix Thread Join Errors in `test_pipeline.py` (Lines 465 & 514)**: Initialize `up = None` before `try` blocks to prevent `UnboundLocalError` from masking assertion failures.
2. **Fix `tmp_path` Setup in `test_old_database_gets_new_columns` (Line 264)**: Ensure parent directory exists before connecting or unlinking SQLite files.
3. **Stabilize Date Calculations in `test_review_policy.py` (Line 51)**: Pin dates or mock timestamps to eliminate seasonal date-boundary test failures during January.
4. **Isolate Settings State (Lines 90 & 434)**: Add fixture teardown to reset `Settings` singletons so mutated configurations cannot leak across tests.
5. **Enforce Consistent Background Worker Shutdown**: Pass `start_worker=False` across all test client instantiations that test `process_pending` synchronously.
