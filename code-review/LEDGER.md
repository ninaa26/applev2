# Orchard Sentinel ledger

Everything the reviews found, after checking: what to change or build, what we know, what turned out
wrong, and what's still open. One file, updated every review round. The published page is built from this
file (`python3 code-review/build_ledger.py`).

**Status marks:**
- ✅ checked against the code, the live data or the source
- 🟡 partly true, or plausible but not proven
- ❓ not checked yet
- ❌ checked and wrong

**Effort:** S is under a day, M is 2–5 days, L is over a week.

Last updated: **Oct 24 2026, round 2 (camera corrected; L-02 and L-06 fixed by PRs #27 and #28; P0 and P1 code rows in review as PRs #31–#48).**

## How to work from this ledger (for the Claude session that does the fixes)

This file is the list of fixes to make. Every row was checked by a reviewer against the code, the live
system or a source. The **Unverified** list (`UNVERIFIED.md`) is not: don't fix anything from it without
checking it yourself first.

1. **Order:** P0, then P1, then P2. Within a table, go top to bottom. Skip rows whose Status starts with `done`.
2. **One fix per branch and PR.** Subject lines start with the area (`Server:`, `Device:`, `ML:`, `Docs:`), as
   in `CLAUDE.md`. Name the ledger id in the PR body (e.g. "Fixes L-10").
3. **Test first.** For each bug, write a test that fails on `master` because of the bug, then fix it, then
   run that folder's whole suite (`CLAUDE.md` has the commands). Firmware (`device/esp32-node/`) has no unit
   tests: build it with PlatformIO, and say what you couldn't test without the board.
4. **Use the fix written in the row,** not the one in `gemini-raw/`. Several of Gemini's own fixes were wrong
   or incomplete; the row says so where it matters (L-02, L-04, L-10, L-17, L-35).
5. **Hardware and field rows** (L-03, L-08, L-20 to L-23) need a person with the parts. Write down what to
   measure and leave them open.
6. **Never run anything on the bench Pi (`apple-pi-hub`) without asking,** and don't run `device/install.sh` there.
7. **When a row's PR is open,** set its Status to `in review: PR #n`; **when it is merged,** `done <date> (PR #n)`. Then rebuild the page:
   `python3 code-review/make_unverified.py && python3 code-review/build_ledger.py`.
8. **If you check an Unverified item,** move it here (as a to-do, a fact, or a wrong claim) and delete it from
   `make_unverified.py`'s lists, or add its title to `CHECKED` there.

## Rounds

| Round | Date | Who did it | What | Raw output |
|---|---|---|---|---|
| 1 | Oct 23 | Gemini 3.8 Flash (17 chunks), checked by Claude | Full code review | `gemini-raw/review_*.md`, `REPORT.md` |
| 2 | Oct 24 | Gemini 4 Argon (Parts A–C), checked by Claude | Code, live system and design review | `gemini-raw/argon_ABC_review.md` |
| 2 | Oct 24 | Gemini Deep Research (D1–D4), checked by Claude | Pipeline, ML/CV, trap mount, grower needs | `gemini-raw/argon_D1…D4_*.md` |
| 2 | Oct 24 | Claude (read-only script on both Pis) | Live snapshot | `gemini-upload/06_live_snapshot.md` |

**How much to trust each source:**
- **Flash:** of its 85 critical and high claims, about 70 were checked on Oct 24: roughly 40% real, 30% true but minor, 30% wrong. Several of its suggested fixes were wrong or incomplete (see L-02, L-04, L-10, L-35). **Not checked:** about 15 high claims in ML and field-test scripts (on the Unverified tab), and all of its few hundred medium and low claims.
- **Argon Parts A–C:** about 60% held up, and two of its fixes were incomplete (L-10, L-17). The misses are listed under "Checked and wrong".
- **Deep Research:** 366 links and DOIs in total, 49 of them (13%) dead or cut off in copying. Every quote I opened said what was claimed, except one.

---

## To do: changes and things to build

Ordered by priority. Each item carries the evidence for it. Tick items off by changing **Status** to `done <date>`.

### P0: do before collecting more field data

| ID | What to do | Why (evidence) | Area | Effort | Status |
|---|---|---|---|---|---|
| L-01 | **Fix the grid scale.** Stop a liner's first photos from fixing its scale for good (`scale_problem`, `worker.py:48-62`). Clamp readings to the range the camera can actually give, measured per camera. The 130° OV5640 at 110 mm reads **10.3 px/mm** at the centre at 2048 × 1536, not the 15.3 of the old Pi camera. Through a fisheye, the grid pitch shrinks toward the edges, so the check has to work on the straightened grid. Later, use ArUco markers on a tray instead of the printed grid. **Lead on the ⅓ misreads:** `_agreed_pitch` also tries ½, ⅓ and ¼ of each spacing (`detect.py:537`), and choosing ⅓ gives exactly the live 3.4–3.8 px/mm. Log which fraction won on the failing photos. | ✅ **Live:** **21 of T2's last 25 photos failed**: 17 for scale, 3 for the `max()` error (L-02), 1 with no grid found. The scale misreads were 2.5–3.8 px/mm (about ⅓ of the true value) or 32.5–32.8 (about 3×), against 10.3. Right now the pipeline uses almost no photos. README already lists this as a known problem. | Server CV | S (clamp) / M (ArUco) | in review: PR #31 (camera-scale clamp + fraction log; ArUco tray still to do). After merge: `sentinel-server set-scale T2 10.3` on the server, then reprocess T2's liner |
| L-02 | **Fix the grid finder's crash: `ValueError: max() iterable argument is empty`.** In `_agreed_pitch` (`detect.py:538`), when the two measured line spacings disagree and all are under 12 px, `cands` is empty and `max()` fails. Fix: return "no grid found" (score 0) in that case. ❌ Don't use Flash's fix (return the median spacing): it stores a nonsense scale that a liner's first photos then lock in (L-01). | ✅ **Reproduced:** `_agreed_pitch([7.0, 10.0], …)` raises exactly the live error. **Live:** 15 failures in 3 days. ❌ Argon's diagnosis (NoClassifier) was wrong. Found by Flash. | Server CV | S | done Oct 24 (PR #27) |
| L-03 | **Measure the ESP32 board's sleep current, then cut it.** A USB power meter or multimeter on the battery lead gives the number. Fixes: a timer/load switch that cuts power between photos (e.g. TPL5110), removing the power LED, or a bare-module board. Then redo the battery size. | ✅ **Source** (McDaid 2024, this exact Freenove ESP32-S3-WROOM CAM board): about **17.5 mA in deep sleep**, against about 8 µA for the chip alone. At 17.5 mA, 2×18650 (about 6,000 mAh) lasts **about 2 weeks**. ❌ Argon's "78 days" assumed 5 mA. | Hardware / firmware | S (measure), M (fix) | open, needs the board: measure deep-sleep current with a USB power meter or multimeter in series with the battery lead (board asleep between photos; note LED on/off), then pick the fix |
| L-04 | **Fix the firmware's clock-drift correction.** It only updates after more than an hour between hub contacts, but nodes check in every 10–30 min. Keep a separate reference point, **a clock reading together with the offset at that moment**, and move both only when the rate is updated (`main.cpp:196-201`). ❌ Flash's fix moves only the clock reading and keeps overwriting the offset on every contact, so the drift it measures is only the drift since the last contact: wrong. | ✅ **Live:** `drift_ppm` is **0 in 255 of 255** camera reports; the correction never ran. | Firmware | S | in review: PR #32 (fw 0.2.6). After flashing, check `drift_ppm` in the hub's `status.jsonl` turns non-zero after an hour |
| L-05 | **Back up the server.** Litestream to cheap object storage, or a nightly `sqlite3 .backup` plus `rsync` of `data/media` to the team Mac. | ✅ No backup exists in the code or docs. One dead SD card loses the season. | Ops | S | in review: PR #33 (`sentinel-server backup` + nightly timer). After merge: set up the SSH key to the team Mac, enable the timer, do one test restore |
| L-06 | **Fix the date-dependent biofix test.** Pin `utcnow` to a fixed mid-season date in the test (e.g. Wednesday 2026-06-17) instead of "N days ago". A fixed Monday alone isn't enough. | ✅ It fails on Fridays and Saturdays (`test_review_policy.py:55`), so CI fails on those days. ✅ It also fails in early January, when "12 days ago" falls in the previous season (Flash). | Tests | S | done Oct 24 (PR #28) |
| L-07 | **Fix `train_v1.py --final`.** `T` (the text embeddings) gets overwritten by the scalar temperature at line 209, then line 215 crashes. Rename the temperature. | ✅ Read the code. The locked-test evaluation can't run until this is fixed. | ML | S | in review: PR #34 |
| L-08 | **Cool the server Pi.** Fit the official Active Cooler or a heatsink and fan. | ✅ **Live:** `throttled=0xe0000` (thermal limiting and CPU-frequency capping have happened) at 49.9 °C. ❌ Argon called it under-voltage, but that flag (0x10000) is not set. | Ops | S | open, needs the parts: fit the Active Cooler, then check `vcgencmd get_throttled` stays 0x0 (after a reboot) and `vcgencmd measure_temp` under a reprocess |
| L-09 | **Put field settings back before deploying.** `checkin_min = 10` and 48 photo slots a day are the window-day test settings in `hub.toml`. | ✅ **Live config.** Check-ins are cheap (0.21 s awake each), but each one is still a Wi-Fi connection. | Ops | S | open, needs the bench Pi: when the window-day test ends, `field-tests/esp32-window-day/finish.sh` puts back `hub.toml.before-window-test` (repo default: `checkin_min = 30`, 6 slots) |

### P1: correctness fixes

| ID | What to do | Why (evidence) | Area | Effort | Status |
|---|---|---|---|---|---|
| L-10 | **Reprocessing inflates reviewed insects' counters.** Reset `n_seen`, `misses`, `prob_sum` and `n_classified` on kept tracks before the replay (`worker.py:188-205`). **Also** don't count a miss for photos taken before the track's `first_seen_at`. Otherwise a reviewed insect that landed in photo 6 collects misses from photos 1–5, and a reviewed candidate can be dropped. Gemini's fix leaves this out. | ✅ Code. Found by Flash and Argon. | Server | S | in review: PR #35 |
| L-11 | **Liner age is computed before the false-new-liner check.** Call `_keep_liner_if_unchanged` first (`worker.py:120-130`). | ✅ Code. | Server | S | in review: PR #36 |
| L-12 | **Settle the OBLR biofix rule.** The code applies 2+ moths for 2 weeks to every lure; the OBLR label says "first catch" (`phenology.py:59`, `services.py:326`, `evaluate.py:196`). Decide per pest, then make the code and label agree. | ✅ CM: "first sustained moth catch" (Cornell CM fact sheet). ✅ OFM: "first sustained capture of two or more moths per trap" (Penn State). ❓ OBLR: Deep Research's Penn State citation doesn't say it. Check NEWA's OBLR model page by hand. | Phenology | S | in review: PR #37 (sustained, as the code does: Cornell's OBLR guidance says catches "over two to three successive days"; NEWA's OBLR page uses base 43 °F and doesn't define a biofix) |
| L-13 | **Add a biofix override and confirm step.** Let a person confirm or change the biofix date. The trap page already says when the biofix rests on unconfirmed catches (`biofix_sure`). | 🟡 D4's top-2 feature. Cheap, and protects the season's clock from one false positive. | Dashboard | S | in review: PR #38 |
| L-14 | **Show hubs even with no camera rows.** The hub table sits inside `{% if rows %}` (`overview.html:17-86`). | ✅ Code. Found by Flash and Argon. | Dashboard | S | in review: PR #39 |
| L-15 | **Stop the photo-request loop on a node whose clock runs behind.** Mark the request answered on a `"requested"` wake (`gateway.py:202`). | ✅ Code (only with clock skew; L-04 makes skew likelier). | Hub | S | in review: PR #40 |
| L-35 | **The hub tells a camera to skip its next photo if they talk within 2 minutes before it.** The cameras' schedule uses the hub's own 2-minute boot margin (`gateway.py:165`, `min_gap=2 min`). Fix: use about 10 s for the cameras' replies, and add a test. ❌ Flash's walrus-operator fix is convoluted; the one-number change is enough. | ✅ **Reproduced:** a check-in at 09:59:10 gets "next wake 14:01", skipping 10:01. With `min_gap=30 s` it gets 10:01. Found by Flash (device BUG-01). | Hub | S | in review: PR #41 (60 s gap, the firmware's own floor, not 10 s) |
| L-36 | **When the hub is down, each photo wake keeps Wi-Fi on for 5 minutes.** `connect_s = min(300, 120 + 2·144.6)` (`main.cpp:488-490`). After one failed photo wake, cap the next ones at about 30–60 s until the hub answers again. | ✅ Code. With L-03 this decides battery life during hub outages. Found by Flash. | Firmware | S | in review: PR #42 |
| L-37 | **Test fixes.** `test_pipeline.py:456-465`: if the wait fails, `up` was never assigned and the `finally` block raises `UnboundLocalError`, which hides the real failure. Set `up = None` first. | ✅ Code. Found by Flash. | Tests | S | in review: PR #43 (both threaded upload tests) |
| L-38 | **Score false positives on empty cards.** `count_accuracy` returns None when the hand count is 0 (`evaluate.py:66-67`), so a card with 0 real moths and 5 automatic ones is never counted against the model. Report false positives per empty card separately. | ✅ Code. Found by Flash. | Evaluation | S | in review: PR #44 |
| L-16 | **Store the lure per liner, not per trap.** Changing a trap's lure today reinterprets every past catch (`models.py:36`, `services.lure_catch_dates`). | ✅ Code. | Server | S–M | in review: PR #45 |
| L-17 | **Make `upload_capture` a plain `def`.** It's `async def` but does blocking database and image work (`app.py:112`). With `def`, `data = await image.read()` must also become `data = image.file.read()`. Argon's one-word fix would be a syntax error. Add a size cap while there (the gateway caps size; the server doesn't). | ✅ Code. Low impact at a few traps. | Server | S | in review: PR #46 |
| L-18 | **Fix the stray root file `Patti's code`.** Move it into `ml/` with a proper name, or delete it if it's been superseded. | ✅ Flash. | Repo | S | in review: PR #47 (moved to `ml/mobilenet_cm_patti.py`, not deleted) |
| L-19 | **Warn about the bench Pi in `docs/bring-up.md:31`.** It says to run `device/install.sh`, which CLAUDE.md forbids there. | ✅ Flash. | Docs | S | in review: PR #48 |

### P2: build out (design and features)

| ID | What to build | Why (evidence) | Area | Effort | Status |
|---|---|---|---|---|---|
| L-20 | **Camera mount, version 2: inside the roof peak, no roof cutout.** With the 130° lens, the camera can sit at the peak (lens about 110 mm over the card) and still see the whole card (`hardware/CAMERAS.md`). That is D3's "Alternative A". Its recommended design (a turret through a 50 mm roof hole, with a 100° lens) assumed a lens we don't have. Keep the rest of D3's design: the **battery in a separate pod strapped to the branch**, so the trap carries only the camera and tray (about 130 g by D3's estimate), plus a stiffener along the ridge, side struts and a slide-in ArUco tray. Keep the turret from hanging into the entrance. | 🟡 D3. ✅ Geometry: the measured 110 mm peak gives an 83° apex angle. ❓ The gram weights are estimates; weigh the real parts. ❓ Confirm all four card corners are in frame (the step in `CAMERAS.md`). | Hardware | M | open |
| L-33 | **Decide the photo resolution.** At full 2592 × 1944 (`FRAMESIZE_QSXGA`), the centre goes from about 10.3 to about 13 px/mm and the edges gain too, for photos of maybe 150–200 kB instead of about 97. Try it on the bench (PSRAM 8 MB is enough) and compare CM vs OFM crops at the card edges. | 🟡 Computed. Both are below the 15 px/mm target in `CAMERAS.md`, so the edges matter for OFM. | Firmware / ML | S | open |
| L-34 | **Update `hardware/CAMERAS.md` and the brief.** Both still say the OV3660 is in use and the OV5640 is "to replace it". Record the 130° OV5640 as the trap camera, with its measured px/mm, the corner check and its focus distance. | ✅ That's why Gemini's D1–D3 reasoned about the wrong lens. | Docs | S | open |
| L-21 | **Run a catch test against a plain trap.** Put 6–10 pairs out for 4 weeks, rotating positions. | ✅ Frewin et al. 2022 (*J. Econ. Entomol.*, doi 10.1093/jee/toac132): camera-equipped Semios traps caught codling moth equal to a standard delta trap. Still check that our housing doesn't change catch. | Field test | M | open |
| L-22 | **Cut glare.** Diffuse the LED, or use cross-polarizing film on the LED and lens; measure the share of blown-out pixels before and after. | 🟡 D2 and D3. Today 10–13% of the card is blown out (README). ❓ The size of the gain is unproven. | Hardware | S–M | open |
| L-23 | **Test Wi-Fi range through leafed-out canopy.** | 🟡 Argon and D1. Wet leaves absorb 2.4 GHz; a bench test won't show it. | Field test | S | open |
| L-24 | **Alerts.** Hub offline, node missed 2+ check-ins, 3+ photos in a row rejected for scale, liner too old, battery low. By email or SMS. | 🟡 D1, D4 and Argon all rank this high; README lists alerts as not done. | Server | S–M | open |
| L-25 | **Grower front page.** A plain-language "what to do this week" banner per block (spray / scout / nothing, with the degree-day date). Under it, a trap health strip (hub, battery, last photo, liner age, lure age) and a photo view with boxes coloured by sure / unsure / not a target. | 🟡 D4 F-01 to F-04. Thresholds checked: ✅ CM about 5 moths/trap (Cornell, "provisional ballpark"); ✅ OFM >10 moths/trap/week for 2nd–3rd brood (Penn State). | Dashboard | M | open |
| L-26 | **Measure missed moths, not just wrong labels.** The 1-in-10 spot check only samples insects the detector found (`services.py:241`). Also send a small share of whole photos to a person who marks every moth. | ✅ Code logic. Argon ML-02. | ML / review | M | open |
| L-27 | **Real migrations (Alembic).** `_add_missing_columns` can't rename, drop or add NOT NULL columns. | ✅ Code. | Server | M | open |
| L-28 | **Over-the-air firmware updates with rollback.** The partition table has one app slot today. | ✅ `partitions.csv`. | Firmware | M | open |
| L-29 | **Security before the server goes public.** HTTPS (e.g. Cloudflare Tunnel or Caddy), session login instead of Basic Auth, CSRF tokens on dashboard forms, an upload size cap. | ✅ Code. Basic Auth is safe today only because Tailscale encrypts the traffic. | Server | M | open |
| L-30 | **Classifier inputs and data.** Add the insect's measured size in mm and the trap's lure as inputs; get OFM from a second trap or camera; add an "other tortricid" class. | 🟡 D2 and Argon. Matches `docs/ml-research-status.md` (one OFM source). ❌ Ignore D2's "+18 pts" style gain numbers; they're invented. | ML | M | open |
| L-31 | **Tooling.** Commit `uv` lockfiles, add ruff, add a PlatformIO firmware build to CI, turn on Dependabot. | 🟡 Round 1 research. | Repo | S each | open |
| L-32 | **Agree the upload protocol in one place.** The fields and status codes from ESP32 to hub to server are written three times (`main.cpp`, `gateway.py`, `app.py`). Make one table or schema that tests check. | 🟡 Round 1. | Repo | M | open |

---

## What we know (checked facts)

**Live system** (Oct 24 2026 snapshot):

| Fact | Value | Where from |
|---|---|---|
| ESP32 camera hardware | **Taidacent OV5640, 5 MP, 130° lens (21 mm, 24-pin 0.5 mm DVP)** on the Freenove ESP32-S3-WROOM CAM. The board's own OV3660 is no longer used. | the user, Oct 24 |
| Scale that camera should give | about 10.3 px/mm at the card centre with the lens 110 mm up at 2048 × 1536, and about 13 at full 2592 × 1944 (fisheye, f ≈ 2.0 mm, 1.4 µm pixels). The edges read lower. | computed; ✅ matches the live 10.3 |
| ESP32 camera T2 firmware | 0.2.5, 248 boots, Wi-Fi −49 dBm, chip 28.7 °C | hub `status.jsonl` |
| Awake time per wake | 2.56 s per photo wake, 0.21 s per check-in (median) | 30 status rows |
| Photo size | about 97 kB median (26 photos) | gateway log |
| Liner scale on T2 | 10.3–10.4 px/mm when read right | server database |
| Server database | 2 traps, 3 liners, 117 photos, 303 tracked insects, 2 reviews | read-only query |
| Server Pi | 49.9 °C, `throttled=0xe0000` (past thermal throttling) | `vcgencmd` |
| Clock drift correction | 0 ppm in every report: never ran | status rows |

**Research** (opened and checked):
- **Biofix:** Cornell's CM fact sheet: degree days base 50 °F "accumulated from the date of first sustained moth catch (the biofix)". First spray at 250 DD50 after biofix. A provisional threshold of about 5 CM per trap.
- **OFM:** Penn State: biofix is the "first sustained capture of two or more moths per trap". Thresholds of >10 moths/trap/week (2nd–3rd brood) and >15 (4th brood).
- **Camera traps and catch:** Frewin et al. 2022: camera-equipped traps catch codling moth equal to a standard delta trap.
- **Board sleep current:** the Freenove ESP32-S3-WROOM CAM measured about 17.5 mA in deep sleep (McDaid 2024 blog).

---

## Checked and wrong (don't act on these)

| Claim | From | Why it's wrong |
|---|---|---|
| "NoClassifier makes `consensus()` crash on `max()`" | Argon SRV-01 | `track.py:75` already returns early on an empty dict. The live errors are real but come from somewhere else (see L-02). |
| "`photo_requested_at` compares naive and UTC times" | Argon SRV-07 | Both are naive UTC: `app.py:125` converts, and `services.py:107` uses `utcnow()`. |
| "Server Pi is under-voltage" | Argon OPS-03 | `0xe0000` has no under-voltage bit (0x10000); it's thermal (L-08). |
| "Battery lasts about 78 days" | Argon B3 | It assumed 5 mA asleep; this board measures about 17.5 mA (L-03). |
| "Clamp scale to 13.8–16.8 px/mm" | D1, D2 | Based on the old Pi camera's 15.3 px/mm. The ESP32 camera reads 10.3, so this would reject every good photo. |
| "+25 / +18 accuracy points per fix" | D2 | Invented numbers with no source. |
| "Swap the narrow OV3660 for a wide OV5640" and "cut a roof hole for a 100° turret" | D1 HW-02, D3 | The 130° OV5640 is already in use, and it sees the whole card from inside the peak (L-20). The brief was out of date (L-34). |
| Penn State defines the OBLR biofix | D4 | The cited Penn State OBLR page doesn't define a biofix. |
| "OBLR biofix is the first catch" (the code's label) | `phenology.py:59` | Cornell's OBLR guidance says sustained flight, catches over two to three successive days (L-12). |
| "409 from the server blocks the ESP32 queue" | Flash | The gateway answers duplicates with `200 {"duplicate": true}` (`gateway.py:214`). |
| "moon_illumination crashes on aware datetimes" | Flash | `app.py:125` normalises every timestamp to naive UTC. |
| "`node_config.h` isn't gitignored" | Flash | `device/esp32-node/.gitignore` covers it. |
| "Trap-style crops drop their group" | Flash | `build_dataset.py:246-248` inherits it from `source_path`. |
| "`card_at` returns None and crashes upload" | Flash | That branch runs only when an open card exists. |
| "`daily_counts` drops catches ahead of UTC" | Flash | The query starts a full day early. |
| "`test.env` is missing from the repo" | Argon (first try) | It was left out of the upload on purpose. |
| "`be_degree_days` raises a math domain error near the base temperature" | Flash | Ran it with the claimed values (49.99999999999999 / 50.00000000000001 / base 50): it returns 0.0 or 2e-15, no error. |
| "New tracks have uninitialised `n_seen` / `misses`" | Flash | The model sets defaults (`models.py:104-114`). |
| "Path traversal through `cap.image_path`" (`worker.py:77`) | Flash | The server builds that path itself, from the trap id, the date and a regex-checked uid (`app.py:128, 153`). |
| "`cap.card_id` is stale after `undo_new_card`" | Flash | `undo_new_card` re-points this photo's own row in the same session. |
| "Server crashes at startup without `media_dir`" | Flash | `settings.py:72` creates it. |
| "`Queue.add` raises SameFileError" | Flash | `uploader.py:38` already compares the resolved paths. |
| "`np.bitwise_count` needs NumPy 2" | Flash | Both requirements files pin `numpy>=2.0`. |
| "Open files exhaust file descriptors" (`eval_detector_roboflow.py:163`) | Flash | CPython closes each one straight away; this is only style. |
| "`setdefault` lets test field cards leak into training" | Flash | Field-card rows set `held_out` themselves from `test_cards.txt` (`liner_crops.py:129`); `TEST_GROUPS` covers the web liners. |
| "Box overlap check is inverted" | Flash | Requiring each box's centre inside the other is intentional, and used in three scripts. |
| "`start.sh` exits on a healthy Pi under `set -e`" | Flash | Ran the exact loop under `set -euo pipefail`: it reaches the end. |
| "`finish.sh` crontab cleanup fails when there are no other cron lines" | Flash | The remote pipeline's exit status is `crontab -`'s, which succeeds. |
| "`test_old_database_gets_new_columns` crashes" | Flash | The suite passes. |

---

## True but minor (fix when touching the file)

- `train_yolo.py:325` defaults to `--device mps`, while the other trainers use `auto`.
- `train_yolo.py:150`: a `ppm` of `0` in labels.csv would divide by zero.
- `classify.py:86-92`: a linear head trained on exactly 2 classes would break (training uses 6).
- `model_playground.py:203` reads an upload of any size (it's a local tool).
- `app.py:70-73`: the worker thread isn't joined on shutdown (SQLite rolls back an unfinished write).
- `server_log.py:25` and `check.sh:26` crash on a mistyped trap id or before the first log row.
- `finish.sh:31`: `tar` stops the cleanup if a photo file is missing.
- `make_markers.py`: the print sheet lays out the markers in a different order from the gluing order; harmless, since each marker is labelled.
- `main.cpp:310-377`: the preview's still and stream share the camera with a plain flag, and the preview stops after a fixed 500 ms. This only matters during the 2-minute setup preview.

## Ideas to weigh (not decided)

- **Hang the battery on the branch, not the trap** (D3). It takes about 200 g off the flimsy trap and lets the battery sit in shade or sun as needed.
- **Fixed camera height as the scale reference**, with the grid only as a cross-check (D1, D2, Argon). This is simpler than ArUco if the mount is rigid.
- **Change detection between consecutive photos vs. tracking across all photos.** Argon says shifting light would break change detection; D2 suggests combining the two. Keep tracking for now.
- **Run detection on the hub** to cut cellular data. Today it's about 97 kB × 48 = 4.7 MB per trap per day at test settings, and about 0.6 MB at 6 photos a day. Probably not worth it this season.
- **Move the worker to its own process.** Argon blames Python's GIL; most of the heavy work (OpenCV, torch) releases it. Do this only if uploads time out while the worker runs.
- **A phone app that works offline (PWA)** (Argon UI-01). That's L effort, for later.

## Open questions

- **Not yet checked:** everything Gemini claimed that hasn't been checked is on the **Unverified** tab (`UNVERIFIED.md`): 15 high-severity code claims, 15 partly checked Argon findings, 19 research claims and 240 Flash medium and low findings.


1. Which fraction (½, ⅓, ¼) wins on the photos that read about ⅓ scale (L-01)?
2. ~~The NEWA OBLR biofix rule: first catch, or sustained (L-12)?~~ Sustained (Oct 24): Cornell (Jentsch 2019) sets it on catches "over two to three successive days"; NEWA's OBLR page doesn't define it. Still open: whether OBLR should use that per-day rule instead of the CM/OFM 2-weeks one.
3. Our board's real sleep current, and which fix to use (L-03)?
4. Does the 50 mm roof cutout and turret change catch? This needs the field test (L-21).
5. How far does Wi-Fi reach with leaves on (L-23)?
6. How heavy is the finished mount on a scale, and does the trap sag after a week in the sun (L-20)?
