#!/usr/bin/env bash
# Update a hub's gateway from this checkout over Tailscale, and put the last one back if it doesn't come up.
# Run from the Mac, in the repo, on the commit to deploy:
#   device/deploy-hub.sh pi@apple-pi-hub
#   device/deploy-hub.sh --rollback pi@apple-pi-hub
# The code goes to ~/sentinel-src on the hub and is installed into /opt/sentinel/venv; the one before it is
# kept as ~/sentinel-src.prev. Packages are installed at the versions in uv.lock (as constraints.txt, made here
# with uv, since the hub has only pip). The hub's config, key and queued photos are not touched, so a camera's photo
# waiting on the hub is never lost. Its cameras keep their own firmware: that goes through the dashboard.
# A deploy that comes up is tagged hub-<hub name>-<time> (pushed to GitHub when the commit is on origin/master).
set -euo pipefail
cd "$(dirname "$0")"

rollback=0
if [[ ${1:-} == --rollback ]]; then rollback=1; shift; fi
[[ $# -eq 1 ]] || { echo "usage: $0 [--rollback] <user@hub>"; exit 1; }
host=$1
remote() { ssh -o ConnectTimeout=10 "$host" "$@"; }

check='for i in $(seq 45); do curl -sf http://127.0.0.1:8080/healthz >/dev/null && exit 0; sleep 1; done; exit 1'

if (( rollback )); then
  remote "test -d ~/sentinel-src.prev || { echo 'no earlier version kept on this hub'; exit 1; }
    rm -rf ~/sentinel-src.bad; mv ~/sentinel-src ~/sentinel-src.bad; mv ~/sentinel-src.prev ~/sentinel-src
    sudo /opt/sentinel/venv/bin/pip install -q \$(test -f ~/sentinel-src/constraints.txt && echo -c ~/sentinel-src/constraints.txt) ~/sentinel-src && sudo systemctl restart sentinel-gateway && $check \
      && echo 'hub is back on the earlier version'"
  exit
fi

sha=$(git rev-parse --short HEAD)
if [[ -n $(git status --porcelain -- .) ]]; then echo "device/ has uncommitted changes: commit them first"; exit 1; fi

echo "copying $sha to $host"
uv export --locked --no-dev --no-emit-project --no-hashes --no-header --no-annotate -q -o constraints.txt.new
rsync -a --delete --exclude .venv --exclude __pycache__ --exclude esp32-node/.pio --exclude tests \
  --exclude constraints.txt.new ./ "$host:sentinel-src.new/"
rsync -a constraints.txt.new "$host:sentinel-src.new/constraints.txt" && rm constraints.txt.new
remote bash -s "$sha" "$check" <<'EOF'
set -euo pipefail
sha=$1; check=$2
sudo /opt/sentinel/venv/bin/pip install -q -c ~/sentinel-src.new/constraints.txt ~/sentinel-src.new
sudo install -m 644 ~/sentinel-src.new/systemd/sentinel-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart sentinel-gateway
if bash -c "$check"; then
  rm -rf ~/sentinel-src.prev
  [[ -d ~/sentinel-src ]] && mv ~/sentinel-src ~/sentinel-src.prev
  mv ~/sentinel-src.new ~/sentinel-src
  echo "$sha $(date -Iseconds)" > ~/sentinel-src/DEPLOYED
  echo "deployed $sha: gateway is up"
  exit 0
fi
echo "gateway did not come up on $sha:"
journalctl -u sentinel-gateway -n 30 --no-pager || true
if [[ -d ~/sentinel-src ]]; then
  echo "putting the earlier version back"
  sudo /opt/sentinel/venv/bin/pip install -q $(test -f ~/sentinel-src/constraints.txt && echo -c ~/sentinel-src/constraints.txt) ~/sentinel-src
  sudo install -m 644 ~/sentinel-src/systemd/sentinel-gateway.service /etc/systemd/system/
  sudo systemctl daemon-reload && sudo systemctl restart sentinel-gateway
fi
exit 1
EOF

tag=hub-${host#*@}-$(date +%Y-%m-%d-%H%M)
git tag -a "$tag" -m "gateway deployed to $host" HEAD
if git fetch -q origin master 2>/dev/null; git merge-base --is-ancestor HEAD origin/master; then
  git push -q origin "$tag" || echo "note: could not push tag $tag; push it later with: git push origin $tag"
else
  echo "tagged $tag here only: the commit isn't on origin/master"
fi
