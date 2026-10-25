#!/usr/bin/env bash
# Install a hub: a Raspberry Pi (4 or 5, Raspberry Pi OS Bookworm or later) with no camera, on mains power,
# that takes photos from the ESP32 cameras near it and sends them to the server. No camera, LED, sensor,
# RTC or power-off setup: for a Pi camera trap use install.sh instead.
# Run from the repo's device/ folder, with the line the dashboard shows when the hub is added (Set up traps):
#   sudo ./install-hub.sh T1 <key> http://apple-pi-server:8000
# That writes the three into /etc/sentinel/config.toml and starts the gateway. Run again with a new key after
# New key on the dashboard.
#
# With no arguments (preparing a hub for someone else): it makes a pairing code, prints it for the hub's
# sticker, and starts the gateway, which waits for the code to be entered on the dashboard (Set up traps →
# Hub → Pairing code) and then fetches its key by itself. server_url in /etc/sentinel/config.toml must be
# the server's address (hub.example.toml has apple-pi-server). A hub that already has a key just restarts.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then echo "run with sudo"; exit 1; fi
if [[ $# -ne 0 && $# -ne 3 ]]; then echo "usage: sudo ./install-hub.sh [<trap id> <key> <server url>]"; exit 1; fi
if [[ $# -eq 3 ]]; then
  [[ $1 =~ ^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$ ]] || { echo "trap id: letters, digits, _ and - only"; exit 1; }
  [[ $2 =~ ^[A-Za-z0-9_-]{16,}$ ]] || { echo "that doesn't look like a key from the dashboard"; exit 1; }
  [[ $3 =~ ^https?://[A-Za-z0-9.:_/-]+$ ]] || { echo "server url: like http://apple-pi-server:8000"; exit 1; }
fi

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
  [[ $# -eq 3 ]] || echo "Edit /etc/sentinel/config.toml (trap_id, api_key, server_url, schedule) before starting the hub."
fi

install -m 644 systemd/sentinel-gateway.service /etc/systemd/system/
systemctl daemon-reload

if [[ $# -eq 3 ]]; then
  sed -i -e "s|^trap_id = .*|trap_id = \"$1\"|" -e "s|^api_key = .*|api_key = \"$2\"|" \
         -e "s|^server_url = .*|server_url = \"$3\"|" /etc/sentinel/config.toml
  systemctl enable sentinel-gateway
  systemctl restart sentinel-gateway
  cat <<MSG

Hub $1 is running. The dashboard shows it online within a minute; add its ESP32 cameras there.
Its photo times are [schedule] times in /etc/sentinel/config.toml (then sudo systemctl restart sentinel-gateway).
Check it:  journalctl -u sentinel-gateway -f   ("gateway listening on 0.0.0.0:8080 for ...")
MSG
  exit 0
fi

systemctl enable sentinel-gateway
if grep -q '^api_key = ""' /etc/sentinel/config.toml && [[ ! -f /var/lib/sentinel/identity.json ]]; then
  code_file=/var/lib/sentinel/claim_code
  if [[ ! -f $code_file ]]; then
    python3 -c 'import secrets; print("".join(secrets.choice("23456789ABCDEFGHJKMNPQRSTUVWXYZ") for _ in range(10)))' > $code_file
  fi
  chown sentinel:sentinel $code_file && chmod 600 $code_file
  code=$(cat $code_file)
  systemctl restart sentinel-gateway
  cat <<MSG

Installed, waiting to be added. Write this pairing code on the hub's sticker:

    ${code:0:4}-${code:4}

On the dashboard: Set up traps → Hub (Raspberry Pi, no camera) → Pairing code. Once the hub is plugged in
and online, it fetches its key within a minute and shows as online. Server: $(sed -n 's/^server_url = "\(.*\)".*/\1/p' /etc/sentinel/config.toml)
Check it:  journalctl -u sentinel-gateway -f
MSG
else
  systemctl restart sentinel-gateway
  echo "Installed; the hub already has its key and is running. Check it:  journalctl -u sentinel-gateway -f"
fi
