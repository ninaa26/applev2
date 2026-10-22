#!/usr/bin/env bash
# How the window day test is going, any time:  ./check.sh
set -euo pipefail
cd "$(dirname "$0")"
source test.env
source runs/current/run.env

echo "== camera $TRAP: last 3 end-of-wake statuses (hub)"
ssh -o BatchMode=yes "$HUB" "tail -3 $HUB_DATA/nodes/$TRAP/status.jsonl 2>/dev/null" | python3 -c '
import json, sys
for line in sys.stdin:
    s = json.loads(line)
    print(f"  {s[\"at\"][11:19]} UTC  {s.get(\"wake\",\"?\"):9} awake {s.get(\"awake_ms\",0)/1000:5.1f} s  rssi {s.get(\"rssi\")}  "
          f"chip {s.get(\"cpu_temp_c\",0):.0f} C  boots {s.get(\"boots\")}  error {s.get(\"last_error\")}")'

echo "== hub"
ssh -o BatchMode=yes "$HUB" "ip=\$(ip -4 -br addr show wlan0 | awk '{print \$3}' | cut -d/ -f1); echo \"  address \$ip (start $HUB_IP)\$([ \"\$ip\" = \"$HUB_IP\" ] || echo '  !! CHANGED: the ESP32 cannot reach the hub')\"
  echo \"  gateway \$(systemctl is-active sentinel-gateway), queued \$(ls $HUB_DATA/nodes/$TRAP/queue/*.jpg 2>/dev/null | wc -l), sent \$(ls $HUB_DATA/nodes/$TRAP/sent/*.jpg 2>/dev/null | wc -l), \$(vcgencmd get_throttled), up \$(uptime -p)\""

echo "== server (last logger row)"
ssh -o BatchMode=yes "$SERVER" "tail -1 ~/window-test/server.csv" | python3 -c '
import sys
keys = "at server photos photos_last_hour last_photo_age_min new processed failed hub_last_seen_min photo_requested mem_used_mb swap_used_mb cpu_temp_c throttled load1 db_locked_10min tracebacks_10min".split()
row = dict(zip(keys, sys.stdin.read().strip().split(",")))
print(f"  {row[\"at\"][11:19]} UTC  server {row[\"server\"]}, {row[\"photos\"]} photos ({row[\"photos_last_hour\"]} last hour, newest {row[\"last_photo_age_min\"]} min old)")
print(f"  processed {row[\"processed\"]}, failed {row[\"failed\"]}, waiting {row[\"new\"]}; hub seen {row[\"hub_last_seen_min\"]} min ago; photo asked for: {row[\"photo_requested\"]}")
print(f"  memory {row[\"mem_used_mb\"]} MB, swap {row[\"swap_used_mb\"]} MB, {row[\"cpu_temp_c\"]} C, throttled {row[\"throttled\"]}, db locked {row[\"db_locked_10min\"]}, tracebacks {row[\"tracebacks_10min\"]}")'
[ -s runs/current/events.csv ] && { echo "== events so far"; sed 's/^/  /' runs/current/events.csv; } || true
