# Read-only status of the hub Pi (gateway only). Lines that look like secrets are redacted.
red() { sed -E 's/((key|token|secret|password|passwd|psk|auth)[A-Za-z_]*["'"'"' ]*[:=] *)[^ ,}]+/\1<redacted>/Ig; s/Bearer [A-Za-z0-9._-]+/Bearer <redacted>/g'; }
H=/home/pi/sentinel-hub; DATA=$H/data
echo "## Host"; echo '```'; hostname; uname -a; uptime; vcgencmd measure_temp 2>/dev/null; vcgencmd get_throttled 2>/dev/null; free -m; df -h / $DATA; ip -4 -br addr; echo '```'
echo "## Code deployed"; echo '```'; ls -la $H | head -20; (cd $H && git log -1 --format='%h %ad %s' --date=iso 2>/dev/null); cat $H/*/sentinel_device/__init__.py $H/sentinel_device/__init__.py 2>/dev/null | head -5; echo '```'
echo "## Hub config (secrets redacted)"; echo '```toml'; red < $H/hub.toml; echo '```'
echo "## systemd"; echo '```'; systemctl status sentinel-gateway --no-pager 2>&1 | head -15; systemctl list-units --no-pager 2>/dev/null | grep -iE 'sentinel|hostapd|dnsmasq|tailscale'; crontab -l 2>/dev/null | red; echo '```'
echo "## Per-camera queues"; echo '```'
for n in $DATA/nodes/*/; do t=$(basename $n); echo "$t: queued $(ls $n/queue/*.jpg 2>/dev/null | wc -l), sent $(ls $n/sent/*.jpg 2>/dev/null | wc -l), newest sent $(ls -t $n/sent/*.jpg 2>/dev/null | head -1 | xargs -r basename)"; done
ls $DATA; echo '```'
echo "## Hub's own queue"; echo '```'; for d in $DATA/queue $DATA/sent; do echo "$d: $(ls $d 2>/dev/null | wc -l) files"; done; echo '```'
for n in $DATA/nodes/*/; do t=$(basename $n); echo "## Camera $t: last 30 end-of-wake statuses"; echo '```json'; tail -30 $n/status.jsonl 2>/dev/null | red; echo '```'; done
echo "## Gateway log: warnings and errors, last 3 days (last 150)"; echo '```'; journalctl -u sentinel-gateway --since '-3 days' --no-pager 2>/dev/null | grep -iE 'warn|error|traceback|exception|fail|refus|timeout' | tail -150 | red; echo '```'
echo "## Gateway log: last 120 lines"; echo '```'; journalctl -u sentinel-gateway -n 120 --no-pager 2>/dev/null | red; echo '```'
echo "## Gateway log: message counts, last 3 days"; echo '```'; journalctl -u sentinel-gateway --since '-3 days' --no-pager -o cat 2>/dev/null | sed -E 's/[0-9a-f]{8,}|[0-9]+/N/g' | cut -c1-110 | sort | uniq -c | sort -rn | head -40 | red; echo '```'
