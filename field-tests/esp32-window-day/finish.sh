#!/usr/bin/env bash
# End the window day test: save every log and the photos to runs/current/, put the hub back on its
# usual schedule, remove the loggers, and build the report.   ./finish.sh   (or ./finish.sh --keep-running
# to collect and report without stopping the test)
set -euo pipefail
cd "$(dirname "$0")"
source test.env
RUN=runs/current
source "$RUN/run.env"
END=$(date -u +%Y-%m-%dT%H:%M:%S+00:00)
[ "${1:-}" = "--keep-running" ] || printf 'END=%s\n' "$END" >> "$RUN/run.env"
SINCE=$(python3 -c "import sys; from datetime import datetime, timezone; print(datetime.fromisoformat(sys.argv[1]).astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))" "$START")
echo "collecting $START .. $END into $RUN"

health() {
  ssh -o BatchMode=yes "$1" 'echo "== $(hostname) $(date -u +%FT%TZ)"; uptime; timedatectl | grep -E "synchronized|NTP service"
    vcgencmd get_throttled; vcgencmd measure_temp; df -h / | tail -1; free -h | head -3; ip -4 -br addr show wlan0
    tailscale status --self 2>&1 | head -1; sudo dmesg -T | grep -i -E "oom|under-voltage" | tail -20 || true'
}
{ health "$HUB"; health "$SERVER"; } > "$RUN/health-end.txt"

ssh -o BatchMode=yes "$HUB" "sudo journalctl -u sentinel-gateway --since '$SINCE' --no-pager" > "$RUN/hub-gateway.log"
ssh -o BatchMode=yes "$SERVER" "sudo journalctl -u sentinel-server --since '$SINCE' --no-pager" > "$RUN/server.log"
scp -q "$HUB:window-test/hub.csv" "$RUN/"
scp -q "$SERVER:window-test/server.csv" "$RUN/"
ssh -o BatchMode=yes "$HUB" "cat $HUB_DATA/nodes/$TRAP/status.jsonl 2>/dev/null" > "$RUN/status.jsonl"
ssh -o BatchMode=yes "$SERVER" "$SERVER_DIR/.venv/bin/python ~/window-test/export_captures.py $SERVER_DIR $TRAP $START" > "$RUN/captures.json"

# The photos themselves, for dawn / noon / dusk / night.
mkdir -p "$RUN/photos"
python3 -c "import json, sys; print('\n'.join(c['image_path'] for c in json.load(open(sys.argv[1]))['captures']))" "$RUN/captures.json" \
  | ssh -o BatchMode=yes "$SERVER" "cd $SERVER_DIR/data/media && tar -cf - -T -" | tar -xf - -C "$RUN/photos"

if [ "${1:-}" != "--keep-running" ]; then
  ssh -o BatchMode=yes "$HUB" "[ -e $HUB_CONFIG.before-window-test ] && mv $HUB_CONFIG.before-window-test $HUB_CONFIG; sudo systemctl restart sentinel-gateway; crontab -l 2>/dev/null | grep -v window-test/ | crontab -"
  ssh -o BatchMode=yes "$SERVER" "crontab -l 2>/dev/null | grep -v window-test/ | crontab -"
  echo "hub back on its usual schedule; loggers removed"
fi

python3 report.py "$RUN"
echo "report: $RUN/report.html"
