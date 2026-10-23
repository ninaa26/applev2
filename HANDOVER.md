# Handover, Oct 22 2026 ~20:00 EDT

## Done (merged to master, deployed)
- PR #24 merged, which also merged PR #15 (Oct 10 audit fixes). It adds the fix for liner re-runs holding the
  SQLite write lock, the field-test report counting `search` wakes at check-in current, and two
  field-test commits that had never been pushed.
- Deployed to `apple-pi-server` (server restarted, worker OK) and `apple-pi-hub` (gateway restarted). Backups
  are in `~/sentinel_server.bak-20261022-pre-pr24.tgz` and `~/sentinel-hub.bak-20261022-pre-pr24.tgz`.
- Archived the finished sessions. Kept: the window-test session (its worktree
  `.claude/worktrees/blissful-pike-d77a2f` holds the live run in `field-tests/esp32-window-day/runs/20261022-1858`;
  archiving it would delete that), its parent "ESP32/Pi camera system setup" (archiving that also archives
  the test session) and "Delta trap housing design" (PR #16 open).

## In progress: this branch `claude/esp32-after-preview-upload` (not merged)
- Bug: after the ESP32's 5-min setup preview, every upload to the hub failed for the rest of that wake while
  Wi-Fi still read as connected. Seen twice today (0.2.1 at test start, 0.2.2 at 19:45). The photo then waits
  for the next wake. Cause not confirmed: there was no serial log, and opening the serial port resets this board.
- Fix in firmware 0.2.3 (`device/esp32-node/src/main.cpp`): drop Wi-Fi after the preview and reconnect fresh,
  and reconnect after every 3rd failed upload on any wake.
- 0.2.3 was flashed to T2 at 19:54 over USB (`/dev/cu.usbmodem5B414842831`). The preview started 19:54:26 and
  ended ~19:59:26. **Not yet verified.** Check:
  `ssh pi@apple-pi-hub 'journalctl -u sentinel-gateway --since "19:59" -o cat | grep T2'`
  It should show `node T2: queued ...` and `node T2 status: {... "fw": "0.2.3" ...}` within ~2 min of 19:59:26.
  If it does, open a PR for this branch and merge it. If it doesn't, the photo goes up at the next search
  wake ~10 min later, and the cause needs a serial log (start `pio device monitor` before powering it).
- The node_config.h for T2 (gitignored) is at `device/esp32-node/include/node_config.h` in the main checkout.

## Next for the user
- Once 0.2.3 is confirmed, unplug the ESP32 from USB and put it on the wall charger at the window. That's a
  power-on, so it runs a 5-min preview (aim the camera), then follows the test schedule. Run
  `field-tests/esp32-window-day/check.sh` from the blissful-pike worktree after its next wake.
- Every deploy and flash today is logged in the test's `events.csv` (`./event.sh note ...`).

## Open decisions (user's answers)
- Dashboard reachable from RedRover over HTTP with a weak password, any user name: user said leave it.
- PR #16 (trap housing): designed around a Pi 5 camera from before the ESP32 + hub layout. User said leave it
  open for a redesign.
- Untracked `docs/presentation/` sits in the `apple-orchard-moth-icons-dd988a` worktree (no session). Untouched.
