This is a code review of **Chunk 4 of 5** (`services.py`, `settings.py`, `app.css`, dashboard templates, systemd unit, `conftest.py`, and `test_detect.py`).

---

### 1. BUGS

#### Finding 1.1: `undo_new_card` unconditionally clears `removed_at`, violating liner lifecycle
* **File path & line**: [server/sentinel_server/services.py:190](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/services.py#L190)
* **Severity**: High
* **Quote**:
  ```python
  190|     before.removed_at = None
  ```
* **Concrete failure scenario**:
  Suppose Liner 1 was installed May 1 and replaced May 15. Liner 2 was installed May 15 and replaced June 1. Liner 3 was installed June 1. If an operator or system action invokes `undo_new_card` on Liner 2 (or a card that was already superseded), `before.removed_at` (Liner 1) is set to `None`. This results in two cards simultaneously having `removed_at is None` for the same trap (Liner 1 and Liner 3). `open_card(db, trap_id)` queries `.where(Card.removed_at.is_(None))` and will non-deterministically select whichever card happens to have the newest timestamp, silently corrupting card tracking history and liner attribution.
* **Suggested fix**:
  Inherit the undone card’s `removed_at` status instead of assuming `before` is now permanently open:
  ```python
  before.removed_at = card.removed_at
  ```

---

#### Finding 1.2: Hubs table in `overview.html` is trapped inside `{% if rows %}`
* **File path & line**: [server/sentinel_server/templates/overview.html:17-45](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/templates/overview.html#L17-L45)
* **Severity**: High
* **Quote**:
  ```jinja2
  17| {% if rows %}
  ...
  45| {% if hubs %}
  46| <div class="card tbl">
  47|   <h2>Hubs</h2>
  ...
  60| {% endif %}
  ...
  86| {% endif %}
  ```
* **Concrete failure scenario**:
  Per `create_trap` ([services.py:75](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/services.py#L75)), an operator is required to set up a hub in the orchard *before* adding any ESP32 camera traps ("an ESP32 camera needs a hub in the orchard: add the hub first"). When the operator adds the hub and navigates to `/` (the overview page), `rows` (camera traps) is empty (`[]`). Because the `{% if hubs %}` block is nested inside `{% if rows %}`, the entire block is skipped and the Hubs card is never rendered. The user sees only "No cameras yet" and cannot verify whether their newly registered hub is online or checking in.
* **Suggested fix**:
  Move `{% if hubs %}...{% endif %}` outside the `{% if rows %}` block so hubs are displayed regardless of whether camera traps have been added yet.

---

#### Finding 1.3: Unhandled `AttributeError` in `capture.html` when `cap.meta` is None
* **File path & line**: [server/sentinel_server/templates/capture.html:19](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/templates/capture.html#L19)
* **Severity**: Medium
* **Quote**:
  ```jinja2
  19|       <dt>Camera</dt><dd class="mono" style="font-size:12px">{{ cap.meta.camera | tojson if cap.meta.camera else '—' }}</dd>
  ```
* **Concrete failure scenario**:
  `Capture.meta` is a nullable JSON column. If a photo upload encounters an early error, or if metadata extraction fails or was omitted during upload, `cap.meta` is `None`. When rendering `/captures/{id}`, Jinja evaluates `cap.meta.camera` on the `None` object before evaluating the condition, raising `jinja2.exceptions.UndefinedError` or `AttributeError: 'NoneType' object has no attribute 'camera'`, crashing the page with a 500 error.
* **Suggested fix**:
  Check `cap.meta` safely using dict access or chained truthiness check:
  ```jinja2
  <dt>Camera</dt><dd class="mono" style="font-size:12px">{{ cap.meta.camera | tojson if (cap.meta and cap.meta.camera) else '—' }}</dd>
  ```

---

#### Finding 1.4: Battery voltage display treats `0.0V` as missing reading
* **File path & line**: [server/sentinel_server/templates/capture.html:18](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/templates/capture.html#L18) and [server/sentinel_server/templates/overview.html:79](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/templates/overview.html#L79)
* **Severity**: Medium
* **Quote**:
  ```jinja2
  # capture.html:18
  <dt>Battery</dt><dd class="mono">{{ '%.2f V'|format(cap.battery_v) if cap.battery_v else '—' }}</dd>

  # overview.html:79
  <td class="mono">{{ '%.2f V'|format(h.last.battery_v) if h.last and h.last.battery_v else '—' }}</td>
  ```
* **Concrete failure scenario**:
  If a field trap's battery dies or drops to `0.0V`, `0.0` evaluates as falsy in Python/Jinja. The dashboard displays `—` (no reading recorded) rather than `0.00 V`. The farm operator is misled into thinking the sensor reading was omitted rather than diagnosing a completely discharged battery. Notice that lines 16 and 17 of `capture.html` correctly use `if cap.temp_c is not none`.
* **Suggested fix**:
  Use explicit `is not none` checks:
  ```jinja2
  {{ '%.2f V'|format(cap.battery_v) if cap.battery_v is not none else '—' }}
  ```

---

#### Finding 1.5: `weather_days` mixes data across multiple NEWA stations
* **File path & line**: [server/sentinel_server/services.py:297-299](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/services.py#L297-L299)
* **Severity**: Medium
* **Quote**:
  ```python
  297|     rows = list(db.scalars(select(WeatherDay).where(WeatherDay.source.like("newa:%"))))
  298|     if rows:
  299|         return {r.day: (r.tmax_f, r.tmin_f) for r in rows}, rows[0].source
  ```
* **Concrete failure scenario**:
  If an operator imports weather files from more than one NEWA weather station over time (e.g. `newa:station_a` and `newa:station_b`), `rows` loads all records for all stations without filtering by source or ordering. When building the `{r.day: ...}` dict, temperature extremes for identical dates from different stations overwrite each other arbitrarily depending on DB return order, while `rows[0].source` returns whichever station was returned first. Phenology degree-day computations end up using an unpredictable mix of different weather stations.
* **Suggested fix**:
  Identify the latest or preferred weather station first, then query days specifically for that source:
  ```python
  latest_source = db.scalar(select(WeatherDay.source).where(WeatherDay.source.like("newa:%")).order_by(WeatherDay.day.desc()).limit(1))
  if latest_source:
      rows = list(db.scalars(select(WeatherDay).where(WeatherDay.source == latest_source)))
      return {r.day: (r.tmax_f, r.tmin_f) for r in rows}, latest_source
  ```

---

#### Finding 1.6: `camera_status` macro crashes if passed a hub's health dictionary
* **File path & line**: [server/sentinel_server/templates/_status.html:4-5](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/templates/_status.html#L4-L5) and [server/sentinel_server/services.py:268](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/services.py#L268)
* **Severity**: Medium
* **Quote**:
  ```jinja2
  4| {%- elif h.state == 'error' %}<a class="pill error" href="{{ h.reason_url }}" title="{{ h.reason }}">Error · {{ photo }}{{ h.last.received_at|ago }}</a>
  5| {%- else %}<span class="pill {{ h.state }}">{{ h.state|capitalize }} · {{ photo }}{{ h.last.received_at|ago }}</span>{% endif %}
  ```
* **Concrete failure scenario**:
  In `services.py:268`, `hub_health()` returns `"last": None` because hubs have no photos. If `camera_status(h)` is invoked on a hub in an `"offline"` state, line 5 unconditionally accesses `h.last.received_at`, raising `AttributeError: 'NoneType' object has no attribute 'received_at'`.
* **Suggested fix**:
  Guard `h.last` in `_status.html`:
  ```jinja2
  {%- else %}<span class="pill {{ h.state }}">{{ h.state|capitalize }} · {{ photo }}{{ (h.last.received_at|ago) if h.last else (h.seen_at|ago if h.seen_at else '') }}</span>{% endif %}
  ```

---

#### Finding 1.7: Non-atomic `next_trap_id` generation race condition
* **File path & line**: [server/sentinel_server/services.py:57-58](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/services.py#L57-L58)
* **Severity**: Low
* **Quote**:
  ```python
  57|     nums = [int(t[1:]) for t in db.scalars(select(Trap.id)) if t[:1] == "T" and t[1:].isdigit()]
  58|     return f"T{max(nums, default=0) + 1}"
  ```
* **Concrete failure scenario**:
  When multiple users or tabs open the `/manage` page concurrently, `next_trap_id` pre-fills the same suggested ID (e.g. `T3`) for both. Both forms submit with `T3`. The second request triggers `raise ValueError(f"trap {trap_id} already exists")` in [services.py:67](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/services.py#L67), which either returns an unhandled 500 error or aborts the operation.
* **Suggested fix**:
  Handle primary key collisions gracefully when registering traps by allowing automatic incrementing on collision or returning a friendly 409 Conflict error in the route.

---

### 2. SECURITY ISSUES

#### Finding 2.1: Missing CSRF protection on sensitive state-changing operations
* **File path & line**: [server/sentinel_server/templates/manage.html:75-78](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/templates/manage.html#L75-L78), [server/sentinel_server/templates/trap.html:20-25](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/templates/trap.html#L20-L25), and [server/sentinel_server/templates/review.html:19](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/templates/review.html#L19)
* **Severity**: High
* **Quote**:
  ```html
  # manage.html:77
  <form method="post" action="/manage/traps/{{ t.id }}/new-key" style="display:inline" onsubmit="return confirm('Give {{ t.id }} a new key? ...')"><button type="submit">New key</button></form>
  <form method="post" action="/manage/traps/{{ t.id }}/remove" style="display:inline" onsubmit="return confirm('Remove {{ t.id }} ...')"><button type="submit">Remove</button></form>

  # trap.html:25
  <form method="post" action="/traps/{{ trap.id }}/new-card">
  ```
* **Concrete failure scenario**:
  None of the dashboard's POST forms include anti-CSRF tokens. If the dashboard is protected with `SENTINEL_DASHBOARD_PASSWORD`, an authenticated farm operator who visits another browser tab with a malicious page can be targeted by automatic background form submissions to `/manage/traps/T1/new-key`. The browser submits authenticated credentials, revoking the active API key and cutting off communication between the field camera/hub and the server. Traps can also be retired or cards reset via forged requests.
* **Suggested fix**:
  Implement CSRF token middleware (e.g. Starlette CSRF middleware or double-submit cookies) and embed hidden `csrf_token` fields in all POST forms.

---

#### Finding 2.2: Open redirect risk via unvalidated `next` parameter in review queue
* **File path & line**: [server/sentinel_server/templates/review.html:20](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/templates/review.html#L20)
* **Severity**: Medium
* **Quote**:
  ```html
  20|       <input type="hidden" name="next" value="/review">
  ```
* **Concrete failure scenario**:
  The form accepts a hidden `next` redirect target parameter. If the POST `/tracks/{id}/review` endpoint redirects to `request.form.get("next")` without ensuring the path is relative and constrained to the local origin, an attacker can construct a review link or form with `next=https://malicious-site.com/login` that redirects the authenticated operator to a credential-harvesting phishing page upon submitting a review.
* **Suggested fix**:
  Ensure the backend endpoint strictly validates that `next` is a relative URL (e.g. `next.startswith("/") and not next.startswith("//")`) or whitelist valid routes.

---

### 3. DEPRECATED APIS & OUTDATED PATTERNS

#### Finding 3.1: Deprecated `utcnow` pattern
* **File path & line**: [server/sentinel_server/services.py:16, 50, 86, 107, 134, 164, 212, 224, 265, 278](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/services.py#L16)
* **Severity**: Low
* **Quote**:
  ```python
  16| from .models import NOT_CATCHES, Capture, Card, Event, Track, Trap, WeatherDay, utcnow
  ...
  50|     now = utcnow()
  ```
* **Concrete failure scenario**:
  `datetime.utcnow()` is formally deprecated in Python 3.12+ and emits deprecation warnings. Furthermore, throughout `services.py`, naive datetimes produced by `utcnow()` require manual `.replace(tzinfo=timezone.utc)` workarounds (e.g. lines 112, 146).
* **Suggested fix**:
  Standardize on timezone-aware UTC datetimes everywhere using `datetime.now(timezone.utc)`.

---

#### Finding 3.2: `Settings` parses `.env` with system default text encoding
* **File path & line**: [server/sentinel_server/settings.py:18](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/settings.py#L18)
* **Severity**: Low
* **Quote**:
  ```python
  18|     for line in path.read_text().splitlines():
  ```
* **Concrete failure scenario**:
  `Path.read_text()` without an explicit `encoding` parameter defaults to `locale.getpreferredencoding(False)`. On Linux or embedded environments configured with ASCII or non-UTF-8 system locales, a `.env` file containing UTF-8 characters (e.g. in notes or passwords) causes a `UnicodeDecodeError` on server startup.
* **Suggested fix**:
  Explicitly specify UTF-8 encoding: `path.read_text(encoding="utf-8").splitlines()`.

---

### 4. INCONSISTENCIES

#### Finding 4.1: Hubs are forced to validate a pheromone lure species upon creation
* **File path & line**: [server/sentinel_server/services.py:68](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/services.py#L68)
* **Severity**: Low
* **Quote**:
  ```python
  68|     if lure not in phenology.MODELS:
  69|         raise ValueError(f"unknown lure {lure!r}")
  ```
* **Concrete failure scenario**:
  A hub is defined as "Hub (no camera)" and has no lure (`manage.html:70` displays `{{ '—' if t.kind == 'hub' else t.lure }}`). However, `create_trap` enforces `lure in phenology.MODELS` before checking `kind`. As a result, hubs are stored with an arbitrary default `lure="CM"` in the database.
* **Suggested fix**:
  Allow `lure` to be `None` or empty when `kind == "hub"`:
  ```python
  if kind != "hub" and lure not in phenology.MODELS:
      raise ValueError(f"unknown lure {lure!r}")
  ```

---

#### Finding 4.2: Hardcoded species list in bar charts diverges from `PESTS` configuration
* **File path & line**: [server/sentinel_server/templates/overview.html:32, 38](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/templates/overview.html#L32) and [server/sentinel_server/templates/trap.html:78, 84](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/templates/trap.html#L78)
* **Severity**: Low
* **Quote**:
  ```jinja2
  32|       {% for sp in ['CM','OFM','OBLR','other_moth','unclassified'] %}<span class="sp"><i class="dot c-{{ sp }}"></i>{{ SPECIES_LABELS[sp] }}</span>{% endfor %}
  ...
  38|         {% for sp in ['CM','OFM','OBLR','other_moth','unclassified'] %}{% if r.counts.get(sp) %}<i class="c-{{ sp }}" style="height:{{ 120 * r.counts[sp] / o.peak }}px"></i>{% endif %}{% endfor %}
  ```
* **Concrete failure scenario**:
  While the overview summary tiles ([overview.html:22](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/templates/overview.html#L22)) and table headers ([overview.html:68](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/templates/overview.html#L68)) dynamically iterate over `PESTS`, the daily catch bar chart hardcodes `['CM','OFM','OBLR','other_moth','unclassified']`. If a new target pest species is added to `PESTS`, its counts appear in the table but are silently omitted from the daily bar charts.
* **Suggested fix**:
  Construct the bar chart species list from `PESTS + ['other_moth', 'unclassified']` or pass it as a template context variable.

---

### 5. DEAD CODE, DUPLICATION & COUPLING

#### Finding 5.1: Duplicate bar chart markup between `overview.html` and `trap.html`
* **File path & line**: [server/sentinel_server/templates/overview.html:28-43](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/templates/overview.html#L28-L43) and [server/sentinel_server/templates/trap.html:74-89](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/templates/trap.html#L74-L89)
* **Severity**: Low
* **Quote**:
  ```jinja2
  # Identical 15-line daily catch bar chart structure duplicated across both files
  <div class="bars" role="img" aria-label="...">
    {% for r in ... %}
      <div class="bar" ...>
  ```
* **Concrete failure scenario**:
  Styling or rendering bug fixes applied to one chart (such as handling empty daily ranges or dynamic species lists) must be manually mirrored across both templates, risking divergence.
* **Suggested fix**:
  Extract the bar chart into a reusable macro or partial template (e.g. `_daily_chart.html`), similar to `_photo.html` and `_status.html`.

---

#### Finding 5.2: Hardcoded audit sampling rate coupling
* **File path & line**: [server/sentinel_server/services.py:231](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/services.py#L231)
* **Severity**: Low
* **Quote**:
  ```python
  231| AUDIT_EVERY = 10  # one in this many automatic labels is also shown to a person
  ```
* **Concrete failure scenario**:
  Sampling frequency is hardcoded as a module-level constant in `services.py` and referenced across both `pending_reviews` and `spot_checks`. There is no mechanism in `settings.py` for farm operators to adjust the verification workload (e.g. higher audit rate during early deployment or lower during peak flight).
* **Suggested fix**:
  Move `audit_every` into `Settings` with a default of 10 (`SENTINEL_AUDIT_EVERY`).

---

### 6. PERFORMANCE & OPTIMIZATIONS

#### Finding 6.1: N+1 query storm on dashboard overview load
* **File path & line**: [server/sentinel_server/services.py:125-133](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/services.py#L125-L133)
* **Severity**: Medium
* **Quote**:
  ```python
  125|     for t in traps:
  126|         week.update(week_counts(db, t.id))
  127|     daily: list[dict] = []
  128|     for t in traps:
  129|         for i, d in enumerate(daily_counts(db, t.id)):
  ...
  133|     health = [trap_health(db, t)["state"] for t in traps]
  ```
* **Concrete failure scenario**:
  In `orchard_summary()`, three separate database queries are executed *per trap*: `week_counts`, `daily_counts` (which loads all tracks for 30 days into Python memory), and `trap_health` (loading the latest capture). For an orchard with 25 traps, loading the overview page issues over 75 SQL queries. Coupled with `<meta http-equiv="refresh" content="60">` in [overview.html:5](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/templates/overview.html#L5), this places continuous CPU and I/O load on low-power host devices like a Raspberry Pi gateway.
* **Suggested fix**:
  Replace the per-trap Python loops with a single SQL query aggregating counts grouped by `(trap_id, date, label)` over the last 30 days.

---

#### Finding 6.2: External CDN font blocking in offline field environments
* **File path & line**: [server/sentinel_server/templates/base.html:7](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/templates/base.html#L7)
* **Severity**: Medium
* **Quote**:
  ```html
  7| <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader:opsz,wght@6..72,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
  ```
* **Concrete failure scenario**:
  Orchard sentinel servers are often deployed on standalone edge hardware (e.g. local Pi 5 gateway connected to local trap APs) with intermittent or no WAN connectivity. Loading external fonts from Google Fonts blocks or delays page rendering until the browser request times out.
* **Suggested fix**:
  Download and self-host the required WOFF2 font files in `server/sentinel_server/static/fonts/` and serve them locally.

---

### 7. TEST COVERAGE GAPS

#### Finding 7.1: Global autouse fixture overrides `SENTINEL_LENS_K` across all test modules
* **File path & line**: [server/tests/conftest.py:12](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/tests/conftest.py#L12)
* **Severity**: Medium
* **Quote**:
  ```python
  12|     monkeypatch.setenv("SENTINEL_LENS_K", "0")  # the lens estimate has its own tests in test_detect.py
  ```
* **Concrete failure scenario**:
  Because `isolated_env` is `autouse=True` for every test in the entire test suite, `SENTINEL_LENS_K` is globally forced to `"0"`. Any test asserting default settings behavior (where `SENTINEL_LENS_K` defaults to `"auto"` per `settings.py:45`) or testing automatic lens estimation via higher-level pipeline calls will test the overridden `0` instead of the production default `"auto"`.
* **Suggested fix**:
  Do not override `SENTINEL_LENS_K="0"` globally in the base fixture; set it explicitly only within the tests that specifically require a 0-distortion baseline.

---

#### Finding 7.2: Zero unit test coverage for `services.py` lifecycle and business logic
* **File path & line**: [server/sentinel_server/services.py:1-340](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/sentinel_server/services.py#L1)
* **Severity**: Medium
* **Concrete failure scenario**:
  Chunk 4 includes tests only for image detection ([test_detect.py](file:///Users/ninaiscool/Developer/Active/applev2/.claude/worktrees/codebase-review-report-fb0ba7/server/tests/test_detect.py)). Key business logic functions in `services.py` lack dedicated unit tests:
  - `undo_new_card`: folding captures and tracks back to the prior liner and handling card state.
  - `spot_checks`: verifying agreement calculation when tracks have `review_status == "rejected"`.
  - `weather_days`: fallback logic from NEWA station records to trap capture temperatures.
  - `phenology_status`: behavior when `biofix` is not yet established vs provisional.
  - `next_trap_id`: handling ID generation with gaps, retired traps, and empty tables.
* **Suggested fix**:
  Add a dedicated `tests/test_services.py` covering trap creation/retirement, card undo, review spot check auditing, and phenology calculations.

---

### Prioritized Next Steps

1. **Fix `overview.html` Hubs Nesting**: Un-nest `{% if hubs %}` from `{% if rows %}` so hub gateways are visible before cameras are connected.
2. **Fix `undo_new_card` Card State**: Set `before.removed_at = card.removed_at` instead of `None` to prevent duplicate open cards.
3. **Add Template Null Checks**: Guard `cap.meta.camera` in `capture.html:19` and use `is not none` for `battery_v` in `capture.html:18` and `overview.html:79`.
4. **Implement CSRF Protection**: Add CSRF tokens to all POST forms on `/manage`, `/traps`, and `/tracks`.
5. **Batch Overview Queries**: Replace N+1 queries in `orchard_summary` with grouped SQL queries.
6. **Localize Fonts**: Host font assets in `static/` to enable full offline/field functionality.
