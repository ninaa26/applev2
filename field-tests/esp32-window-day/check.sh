#!/usr/bin/env bash
# How the window day test is going, any time:  ./check.sh
set -euo pipefail
cd "$(dirname "$0")"
source test.env
source runs/current/run.env

echo "== camera $TRAP: last 3 end-of-wake statuses (hub)"
STATUS=$(ssh -o BatchMode=yes "$HUB" "tail -3 $HUB_DATA/nodes/$TRAP/status.jsonl 2>/dev/null || true")
python3 - "$STATUS" <<'EOF'
import json, sys
lines = [l for l in sys.argv[1].splitlines() if l.strip()]
if not lines:
    print("  none yet")
for line in lines:
    s = json.loads(line)
    print(f"  {s['at'][11:19]} UTC  {s.get('wake', '?'):9} awake {s.get('awake_ms', 0) / 1000:5.1f} s  "
          f"rssi {s.get('rssi')}  chip {s.get('cpu_temp_c') or 0:.0f} C  boots {s.get('boots')}  error {s.get('last_error')}")
EOF

echo "== hub"
ssh -o BatchMode=yes "$HUB" "ip=\$(ip -4 -br addr show wlan0 | awk '{print \$3}' | cut -d/ -f1); echo \"  address \$ip (start $HUB_IP)\$([ \"\$ip\" = \"$HUB_IP\" ] || echo '  !! CHANGED: the ESP32 cannot reach the hub')\"
  echo \"  gateway \$(systemctl is-active sentinel-gateway), queued \$(ls $HUB_DATA/nodes/$TRAP/queue/*.jpg 2>/dev/null | wc -l), sent \$(ls $HUB_DATA/nodes/$TRAP/sent/*.jpg 2>/dev/null | wc -l), \$(vcgencmd get_throttled), up \$(uptime -p)\""

echo "== server (last logger row)"
ROW=$(ssh -o BatchMode=yes "$SERVER" "tail -1 ~/window-test/server.csv")
python3 - "$ROW" <<'EOF'
import sys
keys = ("at server photos photos_last_hour last_photo_age_min new processed failed hub_last_seen_min photo_requested "
        "mem_used_mb swap_used_mb cpu_temp_c throttled load1 db_locked_10min tracebacks_10min").split()
r = dict(zip(keys, sys.argv[1].strip().split(",")))
print(f"  {r['at'][11:19]} UTC  server {r['server']}, {r['photos']} photos ({r['photos_last_hour']} last hour, newest {r['last_photo_age_min']} min old)")
print(f"  processed {r['processed']}, failed {r['failed']}, waiting {r['new']}; hub seen {r['hub_last_seen_min']} min ago; photo asked for: {r['photo_requested']}")
print(f"  memory {r['mem_used_mb']} MB, swap {r['swap_used_mb']} MB, {r['cpu_temp_c']} C, throttled {r['throttled']}, "
      f"db locked {r['db_locked_10min']}, tracebacks {r['tracebacks_10min']}")
EOF
if [ -s runs/current/events.csv ]; then echo "== events so far"; sed 's/^/  /' runs/current/events.csv; fi
