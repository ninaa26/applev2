#!/usr/bin/env bash
# Put the labelling site on a Pi and keep it running, behind Tailscale Funnel.
#
#   ml/label_site/deploy.sh pi@100.81.208.95          # first time and after every code change or new photos
#   ml/label_site/deploy.sh pi@100.81.208.95 --fetch  # bring site.db and an export back to the Mac
#
# Everything goes in ~/orchard-labels/ on the Pi, in a venv, under a systemd *user* service, so no sudo is needed
# except once, by you, for the two lines it prints (Tailscale operator rights for Funnel, and lingering so the
# service runs while nobody is logged in). The Pi's site.db is the record once people label: this script never
# overwrites it. New photos reach it as new rows of labels.csv, imported with `init` (only what's new) and shared
# out with `assign`. Run from the repo root.
set -euo pipefail
HOST=${1:?usage: deploy.sh user@host [--fetch]}
MODE=${2:-}
HERE=$(cd "$(dirname "$0")/../.." && pwd)
DATA=${LABEL_SITE_DATA:-$HERE/ml/data}
SITE=$DATA/review/labelling_site
R='~/orchard-labels'
PORT=8765

if [ "$MODE" = "--fetch" ]; then
  ssh "$HOST" "cd $R/ml && .venv/bin/python -m label_site export && .venv/bin/python - <<'EOF'
import sqlite3, time
src = sqlite3.connect('data/review/labelling_site/site.db'); dst = sqlite3.connect('/tmp/site-fetch.db')
src.backup(dst); dst.close()
EOF"
  mkdir -p "$SITE/from_pi"
  rsync -az "$HOST:/tmp/site-fetch.db" "$SITE/from_pi/site-$(date +%Y%m%d-%H%M%S).db"
  rsync -az "$HOST:$R/ml/data/review/labelling_site/exports/" "$SITE/from_pi/exports/"
  echo "fetched into $SITE/from_pi/"
  exit 0
fi

[ -f "$SITE/labels.csv" ] || { echo "no $SITE/labels.csv: run check_liner_photos.py and prelabel_liners.py first"; exit 1; }
[ -f "$SITE/auth/users.json" ] || { echo "no logins: python -m label_site users ... first"; exit 1; }

echo "== code"
ssh "$HOST" "mkdir -p $R/ml/data/review/labelling_site/inbox $R/server/sentinel_server/pipeline"
rsync -az --delete "$HERE/ml/label_site/" "$HOST:$R/ml/label_site/" --exclude __pycache__
rsync -az "$HERE/ml/paths.py" "$HERE/ml/crop_field_cards.py" "$HERE/ml/field_lengths.py" "$HOST:$R/ml/"
rsync -az "$HERE/server/sentinel_server/__init__.py" "$HOST:$R/server/sentinel_server/"
rsync -az "$HERE/server/sentinel_server/pipeline/__init__.py" "$HERE/server/sentinel_server/pipeline/detect.py" \
  "$HOST:$R/server/sentinel_server/pipeline/"

echo "== photos and labels (site.db on the Pi is left alone)"
rsync -azL --info=stats1 "$SITE/inbox/" "$HOST:$R/ml/data/review/labelling_site/inbox/"
rsync -az "$SITE/photo_checks.csv" "$SITE/labels.csv" "$HOST:$R/ml/data/review/labelling_site/"
[ -d "$SITE/guide" ] && rsync -az "$SITE/guide/" "$HOST:$R/ml/data/review/labelling_site/guide/"
ssh "$HOST" "mkdir -p $R/ml/data/review/labelling_site/auth && chmod 700 $R/ml/data/review/labelling_site/auth"
rsync -az --chmod=F600 "$SITE/auth/users.json" "$SITE/auth/secret" "$HOST:$R/ml/data/review/labelling_site/auth/"  # never passwords.txt

echo "== venv, service, nightly backup"
ssh "$HOST" bash -s -- "$PORT" <<'EOF'
set -euo pipefail
PORT=$1
cd ~/orchard-labels/ml
[ -x .venv/bin/python ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q pillow numpy opencv-python-headless
.venv/bin/python -m label_site init
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/orchard-labels.service <<UNIT
[Unit]
Description=Orchard Sentinel labelling site
After=network-online.target

[Service]
WorkingDirectory=%h/orchard-labels/ml
ExecStart=%h/orchard-labels/ml/.venv/bin/python -m label_site serve --host 127.0.0.1 --port $PORT --secure
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
UNIT
cat > ~/.config/systemd/user/orchard-labels-backup.service <<UNIT
[Unit]
Description=Back up the labelling site's database

[Service]
Type=oneshot
WorkingDirectory=%h/orchard-labels/ml
ExecStart=%h/orchard-labels/ml/.venv/bin/python -c "import sqlite3, time, pathlib; d = pathlib.Path('data/review/labelling_site/backups'); d.mkdir(exist_ok=True); s = sqlite3.connect('data/review/labelling_site/site.db'); b = sqlite3.connect(d / time.strftime('site-%%Y%%m%%d.db')); s.backup(b); b.close(); [p.unlink() for p in sorted(d.glob('site-*.db'))[:-30]]"
UNIT
cat > ~/.config/systemd/user/orchard-labels-backup.timer <<UNIT
[Unit]
Description=Nightly backup of the labelling site

[Timer]
OnCalendar=*-*-* 03:15
Persistent=true

[Install]
WantedBy=timers.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now orchard-labels.service orchard-labels-backup.timer
systemctl --user restart orchard-labels.service
sleep 2
systemctl --user --no-pager --lines=3 status orchard-labels.service | head -5
curl -s -o /dev/null -w "local check: /login answers %{http_code}\n" http://127.0.0.1:$PORT/login
if tailscale funnel --bg $PORT >/dev/null 2>&1; then
  tailscale funnel status | head -4
else
  echo
  echo "Funnel isn't on yet. Once, on the Pi (needs your password):"
  echo "  sudo tailscale set --operator=\$USER        # lets this account run tailscale funnel"
  echo "  sudo loginctl enable-linger \$USER          # keeps the site running when nobody is logged in"
  echo "and allow Funnel for this machine in the Tailscale admin console (Access controls: nodeAttrs \"funnel\")."
  echo "Then run this script again, or: tailscale funnel --bg $PORT"
fi
loginctl show-user "$USER" -p Linger | grep -q yes || echo "note: lingering is off, so the site stops when you log out of the Pi (sudo loginctl enable-linger \$USER)"
EOF
