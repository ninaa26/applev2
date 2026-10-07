#!/usr/bin/env bash
# Install the trap software on a Raspberry Pi 5 running Raspberry Pi OS (Bookworm or later).
# Run from the repo's device/ folder:  sudo ./install.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then echo "run with sudo"; exit 1; fi

apt-get update
apt-get install -y python3-picamera2 python3-gpiozero python3-lgpio python3-venv i2c-tools

# I2C for the SHT45 / INA219 sensors.
raspi-config nonint do_i2c 0

id -u sentinel >/dev/null 2>&1 || useradd --system --create-home --groups video,gpio,i2c sentinel

# The venv sees the apt-installed picamera2/libcamera (they are not on PyPI in a usable form).
python3 -m venv --system-site-packages /opt/sentinel/venv
/opt/sentinel/venv/bin/pip install --upgrade pip
/opt/sentinel/venv/bin/pip install .

install -d -o sentinel -g sentinel /var/lib/sentinel
install -d /etc/sentinel
if [[ ! -f /etc/sentinel/config.toml ]]; then
  install -m 640 -g sentinel config.example.toml /etc/sentinel/config.toml
  echo "Edit /etc/sentinel/config.toml (trap_id, api_key, server_url) before enabling the service."
fi

# Let the cycle power the board off and program the RTC wake alarm.
cat > /etc/sudoers.d/sentinel <<'EOF'
sentinel ALL=(root) NOPASSWD: /usr/bin/systemctl poweroff
EOF
chmod 440 /etc/sudoers.d/sentinel
cat > /etc/udev/rules.d/99-sentinel-rtc.rules <<'EOF'
SUBSYSTEM=="rtc", KERNEL=="rtc0", RUN+="/bin/chgrp sentinel /sys/class/rtc/rtc0/wakealarm", RUN+="/bin/chmod g+w /sys/class/rtc/rtc0/wakealarm"
EOF
udevadm control --reload && udevadm trigger --subsystem-match=rtc

install -m 644 systemd/sentinel-cycle.service /etc/systemd/system/
systemctl daemon-reload

cat <<'MSG'

Installed. Next steps (see docs/bring-up.md):
  1. Low-power shutdown: sudo rpi-eeprom-config --edit  ->  POWER_OFF_ON_HALT=1  and  WAKE_ON_GPIO=0
  2. Bench test:  sudo -u sentinel /opt/sentinel/venv/bin/sentinel-cycle --config /etc/sentinel/config.toml --no-halt
  3. Field mode:  sudo systemctl enable sentinel-cycle   (runs every boot, then powers off)
MSG
