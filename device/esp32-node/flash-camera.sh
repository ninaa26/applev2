#!/usr/bin/env bash
# Flash an ESP32 camera over USB. The hub's Wi-Fi, HUB_URL and pins come from include/node_config.h, filled
# in once; every camera after that is one command.
#   device/esp32-node/flash-camera.sh              # a new camera for pairing: it has no trap id or key, and asks
#                                                  # to be added when switched on near a hub. Prints the code
#                                                  # for its sticker.
#   device/esp32-node/flash-camera.sh T3 <key>     # a camera already added on the dashboard (Set up traps):
#                                                  # puts its trap id and key in node_config.h and flashes it
set -euo pipefail
cd "$(dirname "$0")"

if [[ $# -ne 0 && $# -ne 2 ]]; then echo "usage: $0 [<trap id> <key>]   (both shown on the dashboard when the camera is added)"; exit 1; fi
if [[ $# -eq 2 ]]; then
  trap_id=$1 key=$2
  if [[ ! $trap_id =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$ ]]; then echo "trap id: letters, digits, _ and - only"; exit 1; fi
  if [[ ! $key =~ ^[A-Za-z0-9_-]{16,}$ ]]; then echo "that doesn't look like a key from the dashboard"; exit 1; fi
fi

cfg=include/node_config.h
if [[ ! -f $cfg ]]; then
  cp include/node_config.example.h "$cfg"
  echo "Made $cfg from the example. Fill in WIFI_SSID, WIFI_PASSWORD and HUB_URL for the hub"
  echo "(and LED_PIN), then run this again. Every camera after this one reuses them."
  exit 1
fi
if grep -q '^#define WIFI_PASSWORD "change-me"' "$cfg"; then
  echo "$cfg still has the example Wi-Fi password: fill in the hub's WIFI_SSID, WIFI_PASSWORD and HUB_URL first."
  exit 1
fi
command -v pio >/dev/null || { echo "PlatformIO not found: pip install platformio"; exit 1; }

if [[ $# -eq 0 ]]; then
  log=$(mktemp)
  pio run -e release -t erase   # a board that was another trap forgets its trap id, key and photos
  pio run -e release -t upload | tee "$log"
  mac=$(sed -n 's/^MAC: *\([0-9a-fA-F:]*\).*/\1/p' "$log" | head -1 | tr -d : | tr a-f A-F)
  rm -f "$log"
  cat <<MSG

Flashed for pairing. Write this code on the camera's sticker:  ${mac: -6}

Switched on near its hub, the camera asks to be added. It shows on the dashboard (Set up traps → New cameras
waiting) under that code within a minute; add it there and it gets its trap id and key by itself.
MSG
  exit 0
fi

sed -i.bak -e "s|^#define TRAP_ID .*|#define TRAP_ID \"$trap_id\"|" \
           -e "s|^#define API_KEY .*|#define API_KEY \"$key\"|" "$cfg"
rm -f "$cfg.bak"
grep -q "^#define TRAP_ID \"$trap_id\"" "$cfg" && grep -q "^#define API_KEY \"$key\"" "$cfg" \
  || { echo "couldn't set TRAP_ID and API_KEY in $cfg: check it has both #define lines"; exit 1; }

echo "Flashing $trap_id (hub Wi-Fi: $(sed -n 's/^#define WIFI_SSID "\(.*\)"/\1/p' "$cfg"))"
pio run -e node -t upload

cat <<MSG

$trap_id is flashed. Hang it and power it: for 2 min it shows a live preview for aiming, linked from the
hub's page (http://10.42.0.1:8080/ on the hub's Wi-Fi), then takes its first photo. The hub accepts it
within a minute, and it shows on the dashboard after its first photo.
MSG
