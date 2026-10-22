#!/usr/bin/env bash
# Install a hub: a Raspberry Pi (4 or 5, Raspberry Pi OS Bookworm or later) with no camera, on mains power,
# that takes photos from the ESP32 cameras near it and sends them to the server. No camera, LED, sensor,
# RTC or power-off setup: for a Pi camera trap use install.sh instead.
# Run from the repo's device/ folder:  sudo ./install-hub.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then echo "run with sudo"; exit 1; fi

apt-get update
apt-get install -y python3-venv

id -u sentinel >/dev/null 2>&1 || useradd --system --create-home sentinel

python3 -m venv /opt/sentinel/venv
/opt/sentinel/venv/bin/pip install --upgrade pip
/opt/sentinel/venv/bin/pip install .

install -d -o sentinel -g sentinel /var/lib/sentinel
install -d /etc/sentinel
if [[ ! -f /etc/sentinel/config.toml ]]; then
  install -m 640 -g sentinel hub.example.toml /etc/sentinel/config.toml
  echo "Edit /etc/sentinel/config.toml (trap_id, api_key, server_url, schedule) before starting the hub."
fi

install -m 644 systemd/sentinel-gateway.service /etc/systemd/system/
systemctl daemon-reload

cat <<'MSG'

Installed. Next steps (see docs/esp32-traps.md):
  1. Dashboard → Set up traps → add this Pi as a Hub; put its key in /etc/sentinel/config.toml
  2. Start it now and at every boot:  sudo systemctl enable --now sentinel-gateway
  3. Check it:  journalctl -u sentinel-gateway -f   ("gateway listening on 0.0.0.0:8080 for ...")
MSG
