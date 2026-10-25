# Read-only status of the server Pi. Lines that look like secrets are redacted.
red() { sed -E 's/((key|token|secret|password|passwd|psk|auth)[A-Za-z_]*["'"'"' ]*[:=] *)[^ ,}]+/\1<redacted>/Ig; s/Bearer [A-Za-z0-9._-]+/Bearer <redacted>/g'; }
D=/home/pi/applev2/server
echo "## Host"; echo '```'; hostname; uname -a; uptime; cat /etc/os-release | head -2; vcgencmd measure_temp 2>/dev/null; vcgencmd get_throttled 2>/dev/null; free -m; df -h / $D/data 2>/dev/null; echo '```'
echo "## Code deployed"; echo '```'; cd $D/.. && git log -1 --format='%h %ad %s' --date=iso 2>/dev/null; git status --short 2>/dev/null | head -20; cd $D; ls -la data | head; du -sh data/media 2>/dev/null; ls data/../ 2>/dev/null | head -30; echo '```'
echo "## Environment variables set (names only)"; echo '```'; grep -oE '^[A-Z_]+' .env 2>/dev/null; echo '```'
echo "## Python packages"; echo '```'; .venv/bin/python -V; .venv/bin/python -m pip list 2>/dev/null | grep -iE 'fastapi|uvicorn|sqlalchemy|torch|ultralytics|opencv|numpy|pillow|onnx|open_clip|starlette|jinja'; echo '```'
echo "## Models on disk"; echo '```'; find $D/.. -maxdepth 4 \( -name '*.pt' -o -name '*.onnx' -o -name '*.npz' \) -printf '%TY-%Tm-%Td %10s %p\n' 2>/dev/null | head -20; echo '```'
echo "## systemd"; echo '```'; systemctl status sentinel-server --no-pager 2>&1 | head -15; systemctl list-timers --no-pager 2>/dev/null | grep -i sentinel; echo '```'
echo "## Server log: warnings and errors, last 3 days (last 150)"; echo '```'; journalctl -u sentinel-server --since '-3 days' --no-pager 2>/dev/null | grep -iE 'warn|error|traceback|exception|fail|locked' | tail -150 | red; echo '```'
echo "## Server log: last 120 lines"; echo '```'; journalctl -u sentinel-server -n 120 --no-pager 2>/dev/null | red; echo '```'
echo "## Server log: message counts, last 3 days"; echo '```'; journalctl -u sentinel-server --since '-3 days' --no-pager -o cat 2>/dev/null | sed -E 's/[0-9a-f]{8,}|[0-9]+/N/g' | cut -c1-110 | sort | uniq -c | sort -rn | head -40 | red; echo '```'
