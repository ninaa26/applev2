# Code Review: Orchard Sentinel (Chunk 2 of 3)

This review covers the Chunk 2 files in scope: `docs/ml-research-status.md`, `docs/server-on-linux.md`, `docs/server-on-mac.md`, `docs/wiring.md`, and the `field-tests/esp32-window-day/` suite (`.gitignore`, `README.md`, `check.sh`, `event.sh`, `finish.sh`, `export_captures.py`, `hub_log.py`, `server_log.py`).

---

## 1. Bugs (Correctness, Crashes, Race Conditions, Error Handling)

### [CRITICAL] `finish.sh:31-38` — Tar pipeline aborts on empty captures or missing image paths, bypassing schedule/crontab cleanup
- **Severity:** Critical
- **Relevant Code:**
  ```bash
  31| python3 -c "import json, sys; print('\n'.join(c['image_path'] for c in json.load(open(sys.argv[1]))['captures']))" "$RUN/captures.json" \
  32|   | ssh -o BatchMode=yes "$SERVER" "cd $SERVER_DIR/data/media && tar -cf - -T -" | tar -xf - -C "$RUN/photos"
  33| 
  34| if [ "${1:-}" != "--keep-running" ]; then
  35|   ssh -o BatchMode=yes "$HUB" "[ -e $HUB_CONFIG.before-window-test ] && mv $HUB_CONFIG.before-window-test $HUB_CONFIG; sudo systemctl restart sentinel-gateway; crontab -l 2>/dev/null | grep -v window-test/ | crontab -"
  36|   ssh -o BatchMode=yes "$SERVER" "crontab -l 2>/dev/null | grep -v window-test/ | crontab -"
  37|   echo "hub back on its usual schedule; loggers removed"
  38| fi
  ```
- **Concrete Failure Scenario:**
  1. If a test run records no captures (e.g. during outage tests or if the camera failed to associate), `captures` is `[]`.
  2. GNU `tar -cf - -T -` on the remote Pi receives an empty input stream and exits with code 2: `tar: Cowardly refusing to create an empty archive`.
  3. Because `set -euo pipefail` is active (line 5), the pipeline immediately terminates the script.
  4. Lines 34–38 never execute: the hub configuration is never restored, test logging crontabs remain running permanently on both machines, and `report.html` is never generated.
  5. In addition, if any capture failed before saving an image (`c['image_path']` is `None`), Python's `str.join()` crashes with `TypeError: sequence item expected str instance, NoneType found`.
- **Suggested Fix:**
  Extract non-null paths into a variable first, execute `tar` only if non-empty, and bind cleanup to an `EXIT` trap so it runs regardless of failure:
  ```bash
  trap 'cleanup' EXIT
  cleanup() {
    if [ "${KEEP_RUNNING:-0}" -eq 0 ]; then
      ssh -o BatchMode=yes "$HUB" "[ -e $HUB_CONFIG.before-window-test ] && mv $HUB_CONFIG.before-window-test $HUB_CONFIG; sudo systemctl restart sentinel-gateway; (crontab -l 2>/dev/null | grep -v window-test/ || true) | crontab -"
      ssh -o BatchMode=yes "$SERVER" "(crontab -l 2>/dev/null | grep -v window-test/ || true) | crontab -"
    fi
  }

  PATHS=$(python3 -c "import json, sys; print('\n'.join(c['image_path'] for c in json.load(open(sys.argv[1]))['captures'] if c.get('image_path')))" "$RUN/captures.json")
  if [ -n "$PATHS" ]; then
    echo "$PATHS" | ssh -o BatchMode=yes "$SERVER" "cd $SERVER_DIR/data/media && tar -cf - -T -" | tar -xf - -C "$RUN/photos"
  fi
  ```

---

### [HIGH] `finish.sh:35-36` — `grep -v` exit code 1 causes remote crontab cleanup to fail under `set -e`
- **Severity:** High
- **Relevant Code:**
  ```bash
  35|   ssh -o BatchMode=yes "$HUB" "[ -e $HUB_CONFIG.before-window-test ] && mv $HUB_CONFIG.before-window-test $HUB_CONFIG; sudo systemctl restart sentinel-gateway; crontab -l 2>/dev/null | grep -v window-test/ | crontab -"
  36|   ssh -o BatchMode=yes "$SERVER" "crontab -l 2>/dev/null | grep -v window-test/ | crontab -"
  ```
- **Concrete Failure Scenario:**
  If a machine had no other crontab entries prior to the test, `grep -v window-test/` produces no matching output lines and returns exit code 1. This causes the compound remote command to fail with code 1. Under `set -e`, `finish.sh` aborts at line 35. Line 36 (restoring server crontab) and line 40 (`python3 report.py`) are never executed.
- **Suggested Fix:**
  Add `|| true` to the grep pipeline:
  ```bash
  (crontab -l 2>/dev/null | grep -v window-test/ || true) | crontab -
  ```

---

### [HIGH] `check.sh:26-32` — Empty/missing `server.csv` causes `KeyError` and aborts status output
- **Severity:** High
- **Relevant Code:**
  ```bash
  26| ROW=$(ssh -o BatchMode=yes "$SERVER" "tail -1 ~/window-test/server.csv")
  27| python3 - "$ROW" <<'EOF'
  28| import sys
  29| keys = ("at server photos photos_last_hour last_photo_age_min new processed failed hub_last_seen_min photo_requested "
  30|         "mem_used_mb swap_used_mb cpu_temp_c throttled load1 db_locked_10min tracebacks_10min").split()
  31| r = dict(zip(keys, sys.argv[1].strip().split(",")))
  32| print(f"  {r['at'][11:19]} UTC  server {r['server']}, {r['photos']} photos ({r['photos_last_hour']} last hour, newest {r['last_photo_age_min']} min old)")
  ```
- **Concrete Failure Scenario:**
  1. If `check.sh` is run immediately after `start.sh` before the 10-minute cron writes to `~/window-test/server.csv`, `tail -1` fails. Unlike line 9 (`tail -3 ... || true`), line 26 has no fallback, so `ssh` exits with code 1 and aborts `check.sh`.
  2. If `server.csv` exists but is empty, `ROW` is `""`. `"".strip().split(",")` returns `[""]`. `zip(keys, [""])` only maps the `at` key to `""`. Line 32 immediately throws `KeyError: 'server'`. The script terminates without printing event logs or health summary.
- **Suggested Fix:**
  Add `|| true` to line 26, and in Python validate that row data was received:
  ```bash
  ROW=$(ssh -o BatchMode=yes "$SERVER" "tail -1 ~/window-test/server.csv 2>/dev/null || true")
  ```
  ```python
  if not sys.argv[1].strip():
      print("  no server log entries yet")
      sys.exit(0)
  values = sys.argv[1].strip().split(",")
  if len(values) < len(keys):
      print(f"  partial server log entry ({len(values)}/{len(keys)} fields)")
      sys.exit(0)
  r = dict(zip(keys, values))
  ```

---

### [HIGH] `remote/server_log.py:25, 39-40` — `TypeError` crashes logger when hub or trap is absent in SQLite
- **Severity:** High
- **Relevant Code:**
  ```python
  25| one = lambda sql, *a: db.execute(sql, a).fetchone()[0]
  ...
  39|     "hub_last_seen_min": age(one("select last_seen_at from traps where id = ?", hub)),
  40|     "photo_requested": bool(one("select photo_requested_at from traps where id = ?", trap)),
  ```
- **Concrete Failure Scenario:**
  If `server_log.py` executes before the hub or trap is registered in `sentinel.db` (or if a trap ID is misspelled in `test.env`), `db.execute(...).fetchone()` returns `None`. Indexing `[0]` immediately throws `TypeError: 'NoneType' object is not subscriptable`, crashing the cron job and stopping telemetry collection.
- **Suggested Fix:**
  Safely unpack scalar queries with a fallback:
  ```python
  def one(sql, *a, default=None):
      row = db.execute(sql, a).fetchone()
      return row[0] if row is not None else default
  ```

---

### [MEDIUM] `check.sh:16-18` — `TypeError` crash on null `awake_ms` in camera status
- **Severity:** Medium
- **Relevant Code:**
  ```python
  16|     s = json.loads(line)
  17|     print(f"  {s['at'][11:19]} UTC  {s.get('wake', '?'):9} awake {s.get('awake_ms', 0) / 1000:5.1f} s  "
  18|           f"rssi {s.get('rssi')}  chip {s.get('cpu_temp_c') or 0:.0f} C  boots {s.get('boots')}  error {s.get('last_error')}")
  ```
- **Concrete Failure Scenario:**
  If an ESP32 wake status is emitted with `"awake_ms": null` (e.g. brownout during boot before timer initialization), `s.get('awake_ms', 0)` returns `None` (not `0`, because the key is present). `None / 1000` raises `TypeError: unsupported operand type(s) for /: 'NoneType' and 'int'`. (Notice line 18 uses `s.get('cpu_temp_c') or 0` to defend against `null`, but line 17 does not).
- **Suggested Fix:**
  ```python
  (s.get('awake_ms') or 0) / 1000:5.1f
  ```

---

### [MEDIUM] `remote/server_log.py:26-27` — Offset-aware vs naive timestamp subtraction crash in `age()`
- **Severity:** Medium
- **Relevant Code:**
  ```python
  26| naive = lambda d: d.replace(tzinfo=None).isoformat(sep=" ")
  27| age = lambda t: round((now.replace(tzinfo=None) - datetime.fromisoformat(t)).total_seconds() / 60, 1) if t else ""
  ```
- **Concrete Failure Scenario:**
  If `last_seen_at` in the `traps` table contains an ISO string with a timezone offset (e.g. `2026-10-23T14:15:00+00:00` or `...Z`), `datetime.fromisoformat(t)` produces an offset-aware datetime. `now.replace(tzinfo=None)` is offset-naive. Python raises `TypeError: can't subtract offset-naive and offset-aware datetimes`, halting `server_log.py`.
- **Suggested Fix:**
  Normalize timestamps to UTC before stripping tzinfo:
  ```python
  def age(t):
      if not t:
          return ""
      dt = datetime.fromisoformat(t)
      if dt.tzinfo is not None:
          dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
      return round((now.replace(tzinfo=None) - dt).total_seconds() / 60, 1)
  ```

---

### [MEDIUM] `remote/hub_log.py:46-48` and `remote/server_log.py:49-51` — Unhandled `FileNotFoundError` when `~/window-test` is absent
- **Severity:** Medium
- **Relevant Code:**
  In `hub_log.py`:
  ```python
  46| out = Path.home() / "window-test" / "hub.csv"
  47| new = not out.exists()
  48| with out.open("a", newline="") as f:
  ```
- **Concrete Failure Scenario:**
  If the destination directory `~/window-test` has not been explicitly created beforehand, calling `.open("a")` raises `FileNotFoundError: [Errno 2] No such file or directory`. In addition, if `hub.csv` exists but is 0 bytes (e.g. created by `touch`), `new` evaluates to `False` and the header row is permanently skipped.
- **Suggested Fix:**
  ```python
  out.parent.mkdir(parents=True, exist_ok=True)
  new = not out.exists() or out.stat().st_size == 0
  with out.open("a", newline="") as f:
  ```

---

### [MEDIUM] `event.sh:20-30, 31-35` — Error handling gaps: silent failures exit with status 0
- **Severity:** Medium
- **Relevant Code:**
  ```bash
  29|     done
  30|     echo "!! the hub's gateway isn't back after 5 min" ;;
  31|   photo-now)
  32|     ssh -o BatchMode=yes "$SERVER" "pw=\$(grep '^SENTINEL_DASHBOARD_PASSWORD=' $SERVER_DIR/.env | cut -d= -f2- | sed 's/ *#.*//');
  33|       curl -s -o /dev/null -w '%{http_code}' -u \"x:\$pw\" -X POST http://localhost:8000/traps/$TRAP/request-photo" | grep -q 303 \
  34|       && log photo-now || echo "!! the server refused the request"
  35|     ;;
  ```
- **Concrete Failure Scenario:**
  If `hub-reboot` times out because the gateway fails to restart within 5 minutes, line 30 prints a message to stdout but does not exit non-zero. The script finishes with exit code 0. Any wrapper script calling `event.sh hub-reboot` incorrectly registers success. In `photo-now`, if HTTP 303 is not returned, it prints to stdout and returns code 0.
- **Suggested Fix:**
  Route failure messages to stderr and exit with code 1:
  ```bash
  echo "!! the hub's gateway isn't back after 5 min" >&2; exit 1 ;;
  ```
  ```bash
  ... && log photo-now || { echo "!! the server refused the request" >&2; exit 1; }
  ```

---

### [LOW] `hub_log.py:30, 38, 40`, `server_log.py:24, 29, 43`, `export_captures.py:13` — Unclosed file descriptors and database connections
- **Severity:** Low
- **Relevant Code:**
  In `server_log.py`:
  ```python
  24| db = sqlite3.connect(f"file:{server_dir}/data/sentinel.db?mode=ro", uri=True, timeout=30)
  29| mem = dict(line.split(":", 1) for line in open("/proc/meminfo"))
  43|     "cpu_temp_c": int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000,
  ```
- **Concrete Failure Scenario:**
  File handles and SQLite read-only connections are left unclosed, relying on process termination for cleanup. In test environments or when imported, this leaks file descriptors and produces `ResourceWarning`.
- **Suggested Fix:**
  Use context managers (`with open(...) as f:`) and explicit `db.close()`.

---

## 2. Security Issues

### [HIGH] `finish.sh:31-32` — Path traversal vulnerability via unvalidated `image_path` in `tar`
- **Severity:** High
- **Relevant Code:**
  ```bash
  31| python3 -c "import json, sys; print('\n'.join(c['image_path'] for c in json.load(open(sys.argv[1]))['captures']))" "$RUN/captures.json" \
  32|   | ssh -o BatchMode=yes "$SERVER" "cd $SERVER_DIR/data/media && tar -cf - -T -" | tar -xf - -C "$RUN/photos"
  ```
- **Concrete Failure Scenario:**
  `image_path` is retrieved directly from database records that originate from remote camera node requests. If an attacker submits a path containing `../` sequences or absolute paths (e.g. `/etc/shadow`), `tar -cf - -T -` on the server packages those files. When extracted locally via `tar -xf - -C "$RUN/photos"`, files can be written outside `$RUN/photos` or overwrite local files.
- **Suggested Fix:**
  Validate each path before feeding it to `tar`, ensuring it is relative and contains no `..` components:
  ```python
  import json, os, sys
  valid = []
  for c in json.load(open(sys.argv[1]))['captures']:
      p = c.get('image_path')
      if p and not os.path.isabs(p) and '..' not in p.split(os.sep):
          valid.append(p)
  print('\n'.join(valid))
  ```

---

### [MEDIUM] `event.sh:32-34` — Password exposure in process listing and broken parsing on `#` symbols
- **Severity:** Medium
- **Relevant Code:**
  ```bash
  32|     ssh -o BatchMode=yes "$SERVER" "pw=\$(grep '^SENTINEL_DASHBOARD_PASSWORD=' $SERVER_DIR/.env | cut -d= -f2- | sed 's/ *#.*//');
  33|       curl -s -o /dev/null -w '%{http_code}' -u \"x:\$pw\" -X POST http://localhost:8000/traps/$TRAP/request-photo" | grep -q 303 \
  ```
- **Concrete Failure Scenario:**
  1. Passing `-u "x:$pw"` exposes the dashboard password in cleartext in the process table (`ps aux`) on the server to unprivileged users.
  2. The regex `sed 's/ *#.*//'` strips any `#` characters inside passwords (e.g. `tr@p#key123`), corrupting valid passwords and causing 401 Unauthorized.
  3. If quotes enclose the password in `.env` (e.g. `SENTINEL_DASHBOARD_PASSWORD="secret"`), the literal quotes remain in `$pw`.
- **Suggested Fix:**
  Pass credentials via standard input or netrc, and parse `.env` values while preserving quoted literals.

---

### [LOW] `event.sh:13, 36` — CSV injection and formatting corruption on unescaped quotes
- **Severity:** Low
- **Relevant Code:**
  ```bash
  13| log() { printf '%s,%s,"%s"\n' "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)" "$1" "${2:-}" >> runs/current/events.csv; echo "logged: $1 ${2:-}"; }
  ...
  36|   note) log note "${2:?say what happened, in quotes}" ;;
  ```
- **Concrete Failure Scenario:**
  If a user runs `./event.sh note 'ESP32 reported "brownout", resetting'`, the output string is `...,note,"ESP32 reported "brownout", resetting"`. The internal double quotes are not escaped as `""`, corrupting `events.csv`. In addition, notes starting with `=, +, -, @` trigger formula execution if opened in Excel.
- **Suggested Fix:**
  Escape internal quotes by replacing `"` with `""`:
  ```bash
  log() {
    local msg="${2:-}"
    msg="${msg//\"/\"\"}"
    printf '%s,%s,"%s"\n' "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)" "$1" "$msg" >> runs/current/events.csv
    echo "logged: $1 ${2:-}"
  }
  ```

---

## 3. Deprecated APIs / Outdated Patterns

### [LOW] `finish.sh:12` — Deprecated / non-standard systemd `journalctl` time string format
- **Severity:** Low
- **Relevant Code:**
  ```bash
  12| SINCE=$(python3 -c "import sys; from datetime import datetime, timezone; print(datetime.fromisoformat(sys.argv[1]).astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))" "$START")
  ```
- **Concrete Failure Scenario:**
  Appending literal `UTC` to the timestamp string (`YYYY-MM-DD HH:MM:SS UTC`) is rejected or misinterpreted by older versions of systemd `parse_timestamp()`, causing `journalctl --since` at lines 22–23 to fail or fall back to local time.
- **Suggested Fix:**
  Use standard ISO 8601 `YYYY-MM-DD HH:MM:SS` or UTC offset notation:
  ```python
  strftime('%Y-%m-%d %H:%M:%S')
  ```

---

### [LOW] `remote/export_captures.py:12` and `remote/server_log.py:26` — Stripping timezones to naive datetimes with space separator
- **Severity:** Low
- **Relevant Code:**
  ```python
  12| start = start.astimezone(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
  ```
- **Concrete Failure Scenario:**
  Using space separators (`sep=" "`) and stripping tzinfo to match SQLite datetime strings introduces subtle bugs when comparing against standard ISO 8601 strings that use `T` delimiters. In ASCII sorting, `' '` (32) sorts before `'T'` (84), causing range comparisons like `received_at >= ?` to return unexpected boundary records.
- **Suggested Fix:**
  Store and query ISO 8601 UTC strings with standard `'T'` separators consistently across schemas and scripts.

---

## 4. Inconsistencies

### [LOW] `docs/ml-research-status.md:59` vs `docs/ml-research-status.md:159` — Conflicting training dataset ratios
- **Severity:** Low
- **Relevant Code:**
  Line 59:
  ```markdown
  59| | Mixing target-domain data into training (5% → +13–15 pts) | Done | `liner_crops.py`: 1,611 real-liner crops, 6% of training, now with 881 real non-target moths...
  ```
  Line 159:
  ```markdown
  159| | Mix in 5–50% trap-domain data; distil for the edge | Done at 4% / Not ours |
  ```
- **Concrete Failure Scenario:**
  Documentation reports two conflicting proportions (6% vs 4%) for the target-domain real-liner data mix.
- **Suggested Fix:**
  Standardize the percentage figure across both sections.

---

### [LOW] `docs/server-on-linux.md:46` vs `docs/server-on-linux.md:50` — Inconsistent binary path prefix
- **Severity:** Low
- **Relevant Code:**
  ```markdown
  45| .venv/bin/sentinel-server init
  46| .venv/bin/sentinel-server add-trap T1 --kind hub --name "Fieldhouse hub"     # prints the hub's key
  ...
  50| own kind has the hub as a Pi camera trap: `sentinel-server set-kind T1 hub` turns it into a hub, which
  ```
- **Concrete Failure Scenario:**
  Lines 45–46 instruct the user to invoke `.venv/bin/sentinel-server`, while line 50 drops `.venv/bin/`. A user executing line 50 in a shell where `.venv/bin` is not on `$PATH` gets `command not found: sentinel-server`.
- **Suggested Fix:**
  Use `.venv/bin/sentinel-server set-kind T1 hub`.

---

### [LOW] `docs/ml-research-status.md:36-39` — Research table numbering out of order
- **Severity:** Low
- **Relevant Code:**
  ```markdown
  36| | 16 | Storing results as Darwin Core / Camtrap DP...
  37| | 18 | More correctly labelled photos of the targets...
  38| | 19 | An OFM check from a second source...
  39| | 17 | Comparing with Trapview's reported precision (> 90%)...
  ```
- **Concrete Failure Scenario:**
  Item 17 appears after Items 18 and 19 in the numbered list, hindering visual navigation.
- **Suggested Fix:**
  Reorder rows so Item 17 appears before Item 18.

---

## 5. Dead Code, Duplication, and Organization Problems

### [MEDIUM] `remote/hub_log.py:16-20, 29-31, 38` and `remote/server_log.py:15-19, 29-30, 43` — Hardware inspection code duplicated across remote loggers
- **Severity:** Medium
- **Relevant Code:**
  In `hub_log.py`:
  ```python
  16| def run(*cmd):
  17|     try:
  18|         return subprocess.run(cmd, capture_output=True, text=True, timeout=20).stdout.strip()
  ...
  30| mem = dict(line.split(":", 1) for line in open("/proc/meminfo"))
  31| kb = lambda k: int(mem[k].split()[0])
  38|     "cpu_temp_c": int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000,
  ```
  In `server_log.py`:
  ```python
  15| def run(*cmd):
  16|     try:
  17|         return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
  ...
  29| mem = dict(line.split(":", 1) for line in open("/proc/meminfo"))
  30| kb = lambda k: int(mem[k].split()[0])
  43|     "cpu_temp_c": int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000,
  ```
- **Concrete Failure Scenario:**
  System metrics collection (parsing `/proc/meminfo`, reading `/sys/class/thermal/thermal_zone0/temp`, invoking `vcgencmd get_throttled`, and executing subprocesses) is copy-pasted between the hub and server logging scripts. Notice subtle divergent bugs: `hub_log.py` strips `stdout` in `run()`, while `server_log.py` forgets to strip it.
- **Suggested Fix:**
  Consolidate system inspection into a shared single module or pass a role flag (`--mode hub|server`) to a unified telemetry script.

---

### [MEDIUM] `field-tests/esp32-window-day/.gitignore:1` — Gaps in test directory gitignore
- **Severity:** Medium
- **Relevant Code:**
  ```gitignore
  1| runs/
  ```
- **Concrete Failure Scenario:**
  Running `finish.sh` or `report.py` creates `__pycache__/` and `.pyc` files inside `remote/` and `field-tests/esp32-window-day/`. Additionally, `test.env` (containing device IP addresses and SSH parameters) and backup files like `hub.toml.before-window-test` are not ignored and risk accidental git commits.
- **Suggested Fix:**
  Update `.gitignore`:
  ```gitignore
  runs/
  test.env
  *.env
  __pycache__/
  *.py[cod]
  *.before-window-test
  ```

---

## 6. Performance / Optimization Opportunities

### [MEDIUM] `remote/export_captures.py:19-23` — N+1 query pattern on detections count
- **Severity:** Medium
- **Relevant Code:**
  ```python
  18| out = []
  19| for r in rows:
  20|     d = dict(r)
  21|     d["meta"] = json.loads(d["meta"] or "{}")
  22|     d["detections"] = db.execute("select count(*) from detections where capture_id = ?", (r["id"],)).fetchone()[0]
  23|     out.append(d)
  ```
- **Concrete Failure Scenario:**
  For every capture record, a separate SQL query is dispatched to SQLite. During tests with multiple days or multiple captures per hour, this generates dozens of unnecessary queries instead of aggregating in a single query.
- **Suggested Fix:**
  Include detection counts in the initial query using a `LEFT JOIN`:
  ```sql
  SELECT c.id, c.uid, c.card_id, c.captured_at, c.received_at, c.processed_at, c.status,
         c.error, c.wake_reason, c.image_path, c.meta, COUNT(d.id) AS detections
  FROM captures c
  LEFT JOIN detections d ON d.capture_id = c.id
  WHERE c.trap_id = ? AND c.received_at >= ?
  GROUP BY c.id
  ORDER BY c.captured_at
  ```

---

### [LOW] `remote/hub_log.py:36-37` — Excessive Path object allocations via `list(...glob())`
- **Severity:** Low
- **Relevant Code:**
  ```python
  36|     "queued": len(list((node / "queue").glob("*.jpg"))),
  37|     "sent_total": len(list((node / "sent").glob("*.jpg"))),
  ```
- **Concrete Failure Scenario:**
  Constructing a full list of `Path` objects in memory every 10 minutes on an SD card-backed Raspberry Pi hub wastes memory and I/O as the `sent/` directory grows over thousands of captures.
- **Suggested Fix:**
  Count using an iterator generator:
  ```python
  "queued": sum(1 for _ in (node / "queue").glob("*.jpg")),
  "sent_total": sum(1 for _ in (node / "sent").glob("*.jpg")),
  ```

---

## 7. Test Coverage Gaps

### [MEDIUM] `field-tests/esp32-window-day/` — Absence of unit tests and static analysis
- **Severity:** Medium
- **Relevant Code:**
  All shell scripts (`check.sh`, `event.sh`, `finish.sh`) and Python loggers (`remote/*.py`).
- **Concrete Failure Scenario:**
  None of the scripts in `field-tests/esp32-window-day/` are checked by `shellcheck` in CI or tested with mock SQLite databases. All script bugs (such as `tar` crashing on empty captures, `KeyError` on empty CSVs, and `TypeError` on missing records) are only discovered when physical hardware is already tethered and deployed.
- **Suggested Fix:**
  1. Add `shellcheck` step in `.github/workflows/tests.yml` targeting `field-tests/**/*.sh`.
  2. Add unit test coverage using temporary SQLite databases for `export_captures.py` and `server_log.py`.

---

## Prioritized Next Steps

1. **Protect cleanup in `finish.sh`**: Wrap lines 34–38 in an `EXIT` trap, append `|| true` to remote `grep -v` pipelines, and skip `tar` if no capture images exist.
2. **Harden `check.sh`**: Add fallback handling for missing `server.csv` files and guard against `null` in `awake_ms`.
3. **Fix unhandled query results in `server_log.py`**: Implement a safe scalar fetch helper to eliminate `TypeError` when a trap or hub record is missing.
4. **Sanitize `tar` input**: Ensure `image_path` entries are checked against path traversal (`..` and leading `/`) before bundling on the server.
5. **Update `.gitignore`**: Add `test.env`, `*.env`, `hub.toml.before-window-test`, and `__pycache__/` to `field-tests/esp32-window-day/.gitignore`.
