#!/usr/bin/env bash
# Start the window day test: pre-flight checks, the starting point, the hub's test schedule, the loggers.
# Run from this folder on a laptop that reaches both Pis over Tailscale:  ./start.sh
set -euo pipefail
cd "$(dirname "$0")"
source test.env

RUN="runs/$(date +%Y%m%d-%H%M)"
mkdir -p "$RUN"
ln -sfn "$(basename "$RUN")" runs/current
START=$(date -u +%Y-%m-%dT%H:%M:%S+00:00)
printf 'START=%s\n' "$START" > "$RUN/run.env"
echo "run folder: $RUN (start $START)"

health() {  # the morning/evening checks from the README, on one Pi
  ssh -o BatchMode=yes "$1" 'echo "== $(hostname) $(date -u +%FT%TZ)"; uptime; timedatectl | grep -E "synchronized|NTP service"
    vcgencmd get_throttled; vcgencmd measure_temp; df -h / | tail -1; free -h | head -3; ip -4 -br addr show wlan0
    tailscale status --self 2>&1 | head -1; sudo dmesg -T | grep -i -E "oom|under-voltage" | tail -5 || true'
}
{ health "$HUB"; health "$SERVER"; } | tee "$RUN/health-start.txt"

# Wi-Fi power saving off on both Pis. With it on (the Pi default), the hub's Wi-Fi stopped taking incoming
# connections 10 min into the first run (Oct 22 2026), so the ESP32 couldn't reach it. Takes a reconnect.
for pi in "$HUB" "$SERVER"; do
  ssh -o BatchMode=yes "$pi" 'c=$(nmcli -t -g GENERAL.CONNECTION dev show wlan0); [ -n "$c" ] || exit 0
    if [ "$(nmcli -g 802-11-wireless.powersave con show "$c")" != disable ]; then
      sudo nmcli con mod "$c" 802-11-wireless.powersave 2
      sudo nohup sh -c "sleep 1; nmcli con up \"$c\"" >/tmp/window-test-reconnect.log 2>&1 &
      echo "$(hostname): Wi-Fi power saving turned off; reconnecting $c"
    fi'
done
sleep 20

# Keep the journal across reboots (the hub-reboot test would otherwise lose the gateway's log so far).
for pi in "$HUB" "$SERVER"; do
  ssh -o BatchMode=yes "$pi" '[ -d /var/log/journal ] || { sudo mkdir -p /var/log/journal && sudo systemd-tmpfiles --create --prefix /var/log/journal && sudo systemctl restart systemd-journald; }'
done

warn=0
grep -q "synchronized: no" "$RUN/health-start.txt" && { echo "!! a Pi's clock is not synchronised (timedatectl)"; warn=1; }
# vcgencmd get_throttled: the low bits are now (under-voltage, capped, throttled), bits 16+ since boot.
for v in $(grep -o "throttled=0x[0-9a-f]*" "$RUN/health-start.txt" | cut -d= -f2); do
  (( v & 0xf )) && { echo "!! a Pi is under-voltage or throttled right now ($v)"; warn=1; }
  (( v & 0xf0000 )) && echo "note: a Pi was under-voltage or throttled earlier since boot ($v); the loggers record it"
done
HUB_IP=$(ssh -o BatchMode=yes "$HUB" "ip -4 -br addr show wlan0 | awk '{print \$3}' | cut -d/ -f1")
printf 'HUB_IP=%s\n' "$HUB_IP" >> "$RUN/run.env"
echo "hub address on its Wi-Fi: $HUB_IP (the ESP32 has this built in; check it again at the end)"

# The hub's test schedule. The hub config before the test is kept once, as hub.toml.before-window-test.
ssh -o BatchMode=yes "$HUB" "cd $HUB_DIR && { [ -e $HUB_CONFIG.before-window-test ] || cp $HUB_CONFIG $HUB_CONFIG.before-window-test; } && python3 - $HUB_CONFIG $PHOTO_EVERY_MIN $CHECKIN_MIN" <<'EOF'
import re, sys
path, every, checkin = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
s = open(path).read()
times = ", ".join(f'"{m // 60:02d}:{m % 60:02d}"' for m in range(0, 24 * 60, every))
s = re.sub(r"^times = \[.*?\].*$", f"times = [{times}]   # window day test", s, count=1, flags=re.M)
s = re.sub(r"^checkin_min = .*\n", "", s, flags=re.M)
s = s.replace("[hub]\n", f"[hub]\ncheckin_min = {checkin}   # window day test\n", 1)
open(path, "w").write(s)
EOF
ssh -o BatchMode=yes "$HUB" "sudo systemctl restart sentinel-gateway && sleep 3 && systemctl is-active sentinel-gateway"
echo "hub schedule: a photo every $PHOTO_EVERY_MIN min, check-ins every $CHECKIN_MIN min"

# The loggers, every 10 min. Earlier CSVs from another run are moved aside.
ssh -o BatchMode=yes "$HUB" "mkdir -p ~/window-test && for f in ~/window-test/*.csv; do [ -e \"\$f\" ] && mv \"\$f\" \"\$f.\$(date +%s)\"; done; true"
ssh -o BatchMode=yes "$SERVER" "mkdir -p ~/window-test && for f in ~/window-test/*.csv; do [ -e \"\$f\" ] && mv \"\$f\" \"\$f.\$(date +%s)\"; done; true"
scp -q remote/hub_log.py "$HUB:window-test/"
scp -q remote/server_log.py remote/export_captures.py "$SERVER:window-test/"
ssh -o BatchMode=yes "$HUB" "(crontab -l 2>/dev/null | grep -v window-test/; echo '*/10 * * * * /usr/bin/python3 \$HOME/window-test/hub_log.py $HUB_DATA $TRAP >> \$HOME/window-test/cron.log 2>&1') | crontab - && python3 ~/window-test/hub_log.py $HUB_DATA $TRAP"
ssh -o BatchMode=yes "$SERVER" "(crontab -l 2>/dev/null | grep -v window-test/; echo '*/10 * * * * $SERVER_DIR/.venv/bin/python \$HOME/window-test/server_log.py $SERVER_DIR $TRAP $HUB_TRAP >> \$HOME/window-test/cron.log 2>&1') | crontab - && $SERVER_DIR/.venv/bin/python ~/window-test/server_log.py $SERVER_DIR $TRAP $HUB_TRAP"
echo "loggers: every 10 min to ~/window-test/*.csv on both Pis"

# The starting point: the camera's last end-of-wake status (firmware 0.2.1+) and its last photo.
LAST=$(ssh -o BatchMode=yes "$HUB" "tail -1 $HUB_DATA/nodes/$TRAP/status.jsonl 2>/dev/null || true")
echo "last status from $TRAP: ${LAST:-none yet (it reports at the end of its next wake: run ./check.sh then)}" | tee "$RUN/start-camera.txt"
python3 - "$LAST" <<'EOF' | tee -a "$RUN/start-camera.txt"
import json, sys
try:
    s = json.loads(sys.argv[1])
except ValueError:
    sys.exit()
print(f"firmware {s.get('fw')}, boots {s.get('boots')}, rssi {s.get('rssi')} dBm, chip {s.get('cpu_temp_c')} C, at {s.get('at')}")
if (s.get("rssi") or 0) < -80:
    print("!! rssi worse than -80 dBm at its spot: expect lost photos")
EOF
[ -z "$ESP32_PORT" ] || echo "ESP32 serial: run  pio device monitor -p $ESP32_PORT | tee $RUN/esp32-serial.log  in another terminal"

cat <<MSG

Started. Before you leave it:
  - The ESP32 at its final spot: power-cycle it there, then ./check.sh after its first photo for the rssi there.
  - Enclosure: sun on a sealed box gets hot, and the lens may fog overnight (chip temperature is logged).
  - Tell the team the bench Pi ($HUB) is tied up for a day.
During the day: ./check.sh, and the failure tests with ./event.sh (README).
At the end: ./finish.sh
MSG
[ $warn = 0 ] || echo "!! fix the warnings above"
