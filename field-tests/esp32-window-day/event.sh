#!/usr/bin/env bash
# The failure tests and anything else worth marking on the report's charts. Each is logged with its time
# to runs/current/events.csv.
#
#   ./event.sh server-stop        then about an hour later:  ./event.sh server-start
#   ./event.sh gateway-stop       across two photo slots, then: ./event.sh gateway-start
#   ./event.sh hub-reboot
#   ./event.sh photo-now          press "Take a photo now" for the camera (same as the dashboard button)
#   ./event.sh note "unplugged the ESP32 for 10 s"     (for the things done by hand: unplug, BOOT press, ...)
set -euo pipefail
cd "$(dirname "$0")"
source test.env
log() { printf '%s,%s,"%s"\n' "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)" "$1" "${2:-}" >> runs/current/events.csv; echo "logged: $1 ${2:-}"; }

case "${1:-}" in
  server-stop)   ssh -o BatchMode=yes "$SERVER" "sudo systemctl stop sentinel-server"; log server-stop ;;
  server-start)  ssh -o BatchMode=yes "$SERVER" "sudo systemctl start sentinel-server"; log server-start ;;
  gateway-stop)  ssh -o BatchMode=yes "$HUB" "sudo systemctl stop sentinel-gateway"; log gateway-stop ;;
  gateway-start) ssh -o BatchMode=yes "$HUB" "sudo systemctl start sentinel-gateway"; log gateway-start ;;
  hub-reboot)
    log hub-reboot
    ssh -o BatchMode=yes "$HUB" "sudo systemctl reboot" || true
    echo "waiting for the hub's gateway to come back..."
    for _ in $(seq 1 60); do
      sleep 5
      if [ "$(ssh -o BatchMode=yes -o ConnectTimeout=5 "$HUB" 'systemctl is-active sentinel-gateway' 2>/dev/null)" = active ]; then
        log hub-back "gateway active again"; exit 0
      fi
    done
    echo "!! the hub's gateway isn't back after 5 min" ;;
  photo-now)
    ssh -o BatchMode=yes "$SERVER" "pw=\$(grep '^SENTINEL_DASHBOARD_PASSWORD=' $SERVER_DIR/.env | cut -d= -f2- | sed 's/ *#.*//');
      curl -s -o /dev/null -w '%{http_code}' -u \"x:\$pw\" -X POST http://localhost:8000/traps/$TRAP/request-photo" | grep -q 303 \
      && log photo-now || echo "!! the server refused the request"
    ;;
  note) log note "${2:?say what happened, in quotes}" ;;
  *) sed -n '2,10p' "$0"; exit 1 ;;
esac
