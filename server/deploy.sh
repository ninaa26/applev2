#!/usr/bin/env bash
# Deploy the server code from this checkout to the server, and put the last one back if it doesn't come up.
# Run from the Mac, in the repo, on the commit to deploy (normally master after a merge):
#   server/deploy.sh                      # to pi@apple-pi-server
#   server/deploy.sh pi@other-host
#   server/deploy.sh --rollback           # put back the code and database from before the last deploy
# Before copying anything it saves the code and a snapshot of the database to ~/deploy-backups/<time>/ on the
# server. After the restart it waits for /healthz; if that doesn't answer in 60 s, it restores that backup's
# code (the database is left alone: a new column is harmless to old code) and restarts again.
set -euo pipefail
cd "$(dirname "$0")"

rollback=0
if [[ ${1:-} == --rollback ]]; then rollback=1; shift; fi
host=${1:-pi@apple-pi-server}
app=applev2/server   # relative to the server user's home

remote() { ssh -o ConnectTimeout=10 "$host" "$@"; }

if (( rollback )); then
  remote bash -s "$app" <<'EOF'
set -euo pipefail
app=$1; last=$(ls -1d ~/deploy-backups/*/ 2>/dev/null | tail -1)
[[ -n $last ]] || { echo "no backups in ~/deploy-backups"; exit 1; }
echo "putting back $last"
rm -rf ~/$app/sentinel_server && tar xzf "$last/code.tgz" -C ~/$app
cp "$last/sentinel.db" ~/$app/data/sentinel.db.restore
sudo systemctl stop sentinel-server
mv ~/$app/data/sentinel.db.restore ~/$app/data/sentinel.db && rm -f ~/$app/data/sentinel.db-wal ~/$app/data/sentinel.db-shm
sudo systemctl start sentinel-server
for i in $(seq 60); do curl -sf http://127.0.0.1:8000/healthz >/dev/null && { echo "server is up on the old code"; exit 0; }; sleep 1; done
echo "server did not come back: journalctl -u sentinel-server"; exit 1
EOF
  exit
fi

sha=$(git rev-parse --short HEAD)
branch=$(git rev-parse --abbrev-ref HEAD)
if [[ -n $(git status --porcelain -- .) ]]; then echo "server/ has uncommitted changes: commit them first"; exit 1; fi
[[ $branch == master ]] || echo "note: deploying $branch, not master"

echo "backing up the server's code and database"
stamp=$(date +%Y%m%d-%H%M%S)
remote bash -s "$app" "$stamp" <<'EOF'
set -euo pipefail
app=$1; dir=~/deploy-backups/$2
mkdir -p "$dir"
tar czf "$dir/code.tgz" -C ~/$app sentinel_server pyproject.toml
~/$app/.venv/bin/python -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close()" \
  ~/$app/data/sentinel.db "$dir/sentinel.db"
ls -1d ~/deploy-backups/*/ | head -n -10 | xargs -r rm -rf   # keep the last 10
EOF

echo "copying $sha"
rsync -a --delete --exclude __pycache__ sentinel_server/ "$host:$app/sentinel_server/"
hash='import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())'
old_deps=$(remote "python3 -c '$hash' $app/pyproject.toml")
rsync -a pyproject.toml "$host:$app/pyproject.toml"
if [[ $old_deps != $(python3 -c "$hash" pyproject.toml) ]]; then
  echo "pyproject.toml changed: installing"
  remote "cd $app && .venv/bin/pip install -q -e ."
fi

remote bash -s "$app" "$stamp" "$sha" <<'EOF'
set -euo pipefail
app=$1; dir=~/deploy-backups/$2
sudo systemctl restart sentinel-server
for i in $(seq 60); do
  if curl -sf http://127.0.0.1:8000/healthz >/dev/null; then echo "$3 $(date -Iseconds)" > ~/$app/DEPLOYED; echo "deployed $3: server is up"; exit 0; fi
  sleep 1
done
echo "server did not come up on $3: putting the old code back"
journalctl -u sentinel-server -n 30 --no-pager || true
rm -rf ~/$app/sentinel_server && tar xzf "$dir/code.tgz" -C ~/$app
sudo systemctl restart sentinel-server
exit 1
EOF
