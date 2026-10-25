#!/usr/bin/env bash
# Writes 06_live_snapshot.md next to this script: status, logs and database counts from the server Pi and the hub
# Pi. Everything here only reads: no restarts, no writes on either Pi (the database is opened read-only).
# Anything that looks like a key, token or password is redacted, and the server's .env shows variable names only.
set -uo pipefail
cd "$(dirname "$0")"
SERVER=${SERVER:-pi@apple-pi-server}
HUB=${HUB:-pi@apple-pi-hub}
OUT=06_live_snapshot.md
SSH="ssh -o BatchMode=yes -o ConnectTimeout=10"

{
  echo "# Live snapshot of the deployed pipeline"
  echo
  echo "Taken $(date -u '+%Y-%m-%d %H:%M UTC') from this laptop over Tailscale. ESP32 cameras have no shell: what"
  echo "they report (firmware, free flash, signal, errors, wake times) is in the hub's per-camera status files below."
  echo
  echo "# Server Pi ($SERVER)"
  $SSH "$SERVER" 'bash -s' < live-scripts/server.sh 2>&1 || echo "(could not reach $SERVER)"
  echo
  echo "## Database"
  $SSH "$SERVER" 'cd /home/pi/applev2/server && .venv/bin/python -' < live-scripts/server_db.py 2>&1 || echo "(database query failed)"
  echo
  echo "# Hub Pi ($HUB)"
  $SSH "$HUB" 'bash -s' < live-scripts/hub.sh 2>&1 || echo "(could not reach $HUB)"
} > "$OUT"

echo "Wrote $OUT ($(wc -c < "$OUT") bytes). Skim it before uploading."
