# Orchard Sentinel — codebase review (Oct 24 2026)

Reviewed at `master` 814c9f2. **Gemini 3.8 Flash did the review** (17 chunks covering every tracked text file, run
through the Antigravity CLI), plus two Gemini web-research reports. Claude ran the test suites, checked the
critical and high findings against the code, and wrote this summary. Gemini's raw output is in
[gemini-raw/](gemini-raw/): about 70 critical or high findings and a few hundred medium or low ones.

**How far to trust the raw files:** of the ~25 critical or high claims checked, about half held up. Several
"critical" ones were wrong. Treat anything in `gemini-raw/` that isn't listed under "Confirmed" below as a lead to
check, not a fact.

## Test status

| Suite | Result |
|---|---|
| server | **1 failed**, 78 passed (86 s) |
| device | 32 passed, 1 skipped |
| ml | passed |

The failure is `server/tests/test_review_policy.py::test_biofix_says_when_it_rests_on_unconfirmed_catches`. The
test is flaky by weekday: it places catches "12, 11, 5 and 4 days ago" and expects two Monday–Sunday weeks with 2+
catches each. On Fridays and Saturdays, 12 and 11 days ago fall in different weeks, so no biofix is found. The
server code is right; the test isn't. **CI will fail on PRs opened on those days.** Fix: build the dates from a fixed
Monday (e.g. `monday = today - timedelta(days=today.weekday())`) rather than "N days ago".

## Confirmed bugs (checked against the code)

### Server
1. **Reprocessing inflates reviewed insects' counters.** In `pipeline/worker.py:188-205`, `reprocess_card` deletes
   unreviewed tracks but keeps reviewed ones without resetting `n_seen`, `misses`, `prob_sum` or `n_classified`.
   Replaying every photo then adds on top of the old values. A 10-photo liner reprocessed once leaves a reviewed
   moth with `n_seen = 20`. Photos taken before it landed also count as `misses`. Fix: zero those four fields
   on kept tracks before the replay.
2. **Liner age is computed before the liner check.** In `worker.py:120-130`, `liner_days` and the `card_old` event
   are computed from the new card, and only then does `_keep_liner_if_unchanged` decide the "new liner" was false
   and fold it back. The photo is left with `liner_days: 0.0`, and an old liner's `card_old` warning is missed. Fix:
   call `_keep_liner_if_unchanged` first, then read the card.
3. **The liner scale can lock in wrong.** `scale_problem` (`worker.py:48-62`) compares each photo with the median
   of the liner's *processed* photos and accepts the first two unconditionally. If those two misread the grid
   (e.g. a harmonic), every correct photo after them fails as "scale off", and failed photos never enter the median.
   The liner can't recover until it's changed. Fix: drop the baseline when, say, three photos in a row agree on a
   different scale.
4. **The OBLR biofix rule contradicts its own label.** `phenology.py:59` says OBLR biofix is "first catch; traps out
   by June 1", but `services.py:326` and `evaluate.py:196-197` apply `sustained_biofix` (2+ moths two weeks running)
   to every lure. Decide which rule is meant (check the NEWA OBLR page), then either add a per-model biofix rule or
   fix the label.
5. **The overview hides hubs when no camera rows exist.** In `templates/overview.html`, the `{% if hubs %}` table
   (line 45) sits inside `{% if rows %}` (line 17, closed at 86). A freshly added hub with no cameras yet never shows
   whether it's online, which is exactly when you need to see it.
6. **`undo_new_card` can reopen an old liner** (`services.py:190`). It always sets `before.removed_at = None`. If
   the folded card wasn't the newest, two cards end up open. This is an edge case, but worth a guard: only reopen
   when `card` was the open one.

### ESP32 firmware (`device/esp32-node/src/main.cpp`)
7. **The sleep-drift correction almost never runs.** `takeTime` (lines 196-201) updates `rate` only if more than
   3600 s have passed since the last sync, but it moves `sync_clock` on every contact, and check-ins come every 30
   min. `rate` stays 1.0 except across long gaps. Fix: keep a separate reference point and move it only when the
   rate is updated.
8. **A dashboard photo request can loop on a clock-skewed node.** The gateway marks a request answered only
   when `captured >= requested_at` (`gateway.py:202-203`). If a node's clock is behind the hub's, every
   "requested" photo is stamped too early, `photo_now` stays true, and the node captures and reboots again on every
   wake. Fix: let the node skip `photo_now` on a wake that was already `"requested"`, or have the gateway mark
   requests answered by wake reason.
9. **The node web server has no auth, and it's plain HTTP.** The setup preview and stream on ports 80/81 are open to
   anyone on the hub Wi-Fi during the 2-minute preview, and the trap key travels in cleartext. That's acceptable on a
   private hub AP, but write it down as a known limit.

### ML
10. **`ml/train_v1.py --final` always crashes.** Line 193 sets `T` to the BioCLIP text-embedding matrix, then line
    209 (`C, _, T = best`) overwrites it with the scalar temperature. Line 215 (`X[lk] @ T.T`) then fails, so the
    locked-test-set evaluation, the run that produces reportable numbers, never completes. Fix: rename the
    temperature (`temp`).
11. **Bare-liner debris crops may straddle splits** (`ml/build_dataset.py:141`). Each crop is its own group
    (`liner:<crop stem>`), so crops cut from the same liner photo can land in both train and test. The comment says
    this is intended, but it leaks liner background into test. Grouping by `r["liner"]` matches the rule in
    `.claude/rules/ml.md` ("a split keeps every crop of a photo together").
12. **`torch.load(..., weights_only=False)`** at `server/sentinel_server/pipeline/classify.py:116` runs arbitrary
    pickle code. The checkpoints are your own, so the risk is low. Switch to `weights_only=True` if the checkpoint
    holds only tensors and plain types.

## Gemini claims that were wrong (don't spend time on these)
- "409 from the server blocks the ESP32 queue forever": the node talks to the gateway, which answers duplicates with
  `200 {"duplicate": true}` (`gateway.py:214`).
- "moon_illumination crashes on timezone-aware datetimes": `app.py:125` converts every timestamp to naive UTC first.
- "`node_config.h` (Wi-Fi password, keys) isn't gitignored": `device/esp32-node/.gitignore` covers it.
- "make_trap_style drops `group`, leaking synthetic copies across splits": `build_dataset.py:246-248` inherits the
  group from `source_path`.
- "`card_at` returns None and crashes the upload": that branch runs only when an open card exists, and `card_at`
  falls back to the first card.
- "`daily_counts` drops catches in timezones ahead of UTC": the query starts a full day early.

## Not yet checked, but worth a look (from `gemini-raw/`)
- Server ([review_server_0.md](gemini-raw/review_server_0.md), [review_server_1.md](gemini-raw/review_server_1.md)):
  - The worker thread isn't joined on shutdown.
  - `_add_missing_columns` skips NOT NULL columns that have no default.
  - Uploads have no size cap at the server.
  - There's no CSRF protection on dashboard POSTs (the dashboard has a password, so this matters if it's ever
    exposed beyond Tailscale).
  - `be_degree_days` can raise a math domain error.
  - The overview runs N+1 queries.
  - The `upload_capture` handler is `async def` but does blocking I/O.
- Device ([review_device_1.md](gemini-raw/review_device_1.md), [review_device_2.md](gemini-raw/review_device_2.md)):
  - The gateway lock is held during disk writes.
  - Schedule edge case: a wake at exactly the window boundary is skipped.
  - When the hub is offline, a node keeps Wi-Fi on for up to 5 min per wake, which is a battery cost.
  - An empty `.json` is left behind if the JPEG write fails.
- ML ([review_ml_0.md](gemini-raw/review_ml_0.md) through [review_ml_5.md](gemini-raw/review_ml_5.md)):
  - `train_v2.py` SequentialLR fails with very few steps.
  - Division by zero in `train_yolo.py` on uncalibrated rows.
  - `train_yolo.py` defaults its device to MPS.
  - An async save race in the labeller.
- Field tests and hardware ([review_cross_1.md](gemini-raw/review_cross_1.md),
  [review_cross_2.md](gemini-raw/review_cross_2.md)):
  - `set -e` plus `grep -v` exiting 1 can abort `finish.sh` before it cleans up the crontab.
  - `start.sh` may exit on a healthy status check.
  - ArUco marker IDs may be transposed in `make_markers.py`.
  - The liner tray may be wider than the trap floor.
  - The cleanup claims are worth checking first, since a half-run cleanup leaves cron jobs on the shared bench Pi.

## Inconsistencies and organization
- **`Patti's code`** (repo root, no extension, 321 lines) sits outside the layout in CLAUDE.md, and Gemini says its
  class names differ from the six standard labels. Move it to `ml/` as a named script (or `ml/archive/`) with its
  labels mapped, or delete it if it's been superseded.
- `docs/bring-up.md:31` tells the reader to run `device/install.sh`, but CLAUDE.md says never to run it on the bench
  Pi. Add a warning in the doc.
- The hub (`hub.example.toml`) and Pi trap (`config.example.toml`) configs name overlapping settings differently
  (Gemini's claim; not checked).
- The ESP32 partition table keeps an `otadata` partition although there's no OTA. That's harmless, but the
  comment and the table disagree.
- The deprecation warning from Starlette's `TestClient` uses `httpx`. Pin or upgrade before it breaks.

## Pipeline: what professionals do vs. what you have
Gemini's research ([research_pipeline.md](gemini-raw/research_pipeline.md)) recommends 13 changes. Several are
**already done** in this repo:
- tracking insects across photos so each is counted once (`pipeline/track.py` matching)
- grouped train/test splits
- a human review queue
- the NEWA sustained-catch biofix
- idempotent uploads keyed by `capture_uid`
- store-and-forward queues on both the hub and the Pi trap
- SQLite WAL mode (`db.py:29`)

The real gaps, in order of value:

| # | Change | Why | Effort |
|---|---|---|---|
| 1 | **Back up the server DB and photos** (Litestream, or a nightly `sqlite3 .backup` + `rsync` to the Mac/cloud) | Today a dead SD card on `apple-pi-server` loses the season | S |
| 2 | **Real migrations** (Alembic with `render_as_batch=True`) instead of `_add_missing_columns` | The hand-rolled migrator can't rename, drop, or add NOT NULL columns | M |
| 3 | **Fleet health alerts**: a node or hub silent for more than 2 check-ins sends an email or push | The dashboard shows it, but nobody is watching at 3 a.m. | S |
| 4 | **ESP32 OTA with rollback** (two app partitions, `esp_ota_mark_app_valid_cancel_rollback`) | Reflashing traps in an orchard by USB doesn't scale | M |
| 5 | **Fixed lighting for each photo** (LED on, same hour daily) | Commercial traps (Trapview, Semios) shoot at a fixed time with controlled light, which cuts glare and blur rejects | M |
| 6 | **Model and data versioning** (record dataset hash and model version per capture; DVC optional) | `model_version` exists; tying it to a dataset hash makes results traceable | S |
| 7 | Keep inference **off the request path** (it already runs in the worker thread). Gemini's ARQ/Redis suggestion is overkill on one Pi | — | skip |

## Codebase organization
Gemini's research ([research_org.md](gemini-raw/research_org.md)) proposes a full move to an `apps/`, `packages/`
and `src/` layout. **I don't recommend the move this semester.** It churns every import, doc and service file for
little gain on a three-area repo. The changes that pay off cheaply:

| Change | Effort |
|---|---|
| Commit lockfiles: `uv lock` in `server/`, `device/`, `ml/`, and `uv sync --frozen` in CI | S |
| Add **ruff** (lint + format) with one root `ruff.toml` and a CI step; add pre-commit if the team will use it | S |
| Add a **PlatformIO build job** to CI (`pio run -d device/esp32-node`, with `node_config.example.h` copied in) so firmware breaks are caught | S |
| Pin weekday- or date-dependent tests to a fixed date (the current CI failure) | S |
| **One shared definition of the upload protocol**: the ESP32 → gateway → server field names live in three places (`main.cpp`, `gateway.py`, `app.py`). Put them in one doc table or JSON Schema that tests check against | M |
| Dependabot for `pip` and `github-actions` | S |
| Leave `ml/` as scripts, but move one-off and old ones into `ml/archive/` | S |

## Suggested next steps (in order)
1. Fix the weekday-flaky biofix test, since it breaks CI on Fridays and Saturdays.
2. Fix `train_v1.py --final` (`T` shadowing) before reporting any locked-test numbers.
3. Fix `reprocess_card` counter inflation and the liner-age ordering in `worker.py`.
4. Decide the OBLR biofix rule and make the code and label agree.
5. Set up server backups.
6. Fix the firmware drift-rate reference and guard the `photo_now` loop.
7. Add a CI firmware build and ruff, and commit lockfiles.
8. Work through the "not yet checked" list, verifying each claim before fixing it.
