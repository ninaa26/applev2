#!/usr/bin/env bash
# Deploy the server code from this checkout to the server, and put the last one back if it doesn't come up.
# Run from the Mac, in the repo, on the commit to deploy (normally master after a merge):
#   server/deploy.sh                      # to pi@apple-pi-server
#   server/deploy.sh pi@other-host
#   server/deploy.sh --rollback           # put back the code and database from before the last deploy
# Before copying anything it saves the code and a snapshot of the database to ~/deploy-backups/<time>/ on the
# server, with a list of its installed packages. Packages are installed at the versions in uv.lock, and only
# when pyproject.toml or uv.lock changed. After the restart it waits for /healthz; if that doesn't answer in
# 60 s, it restores that backup's code and packages and restarts again. The database is put back too if the new
# code migrated it (its Alembic revision changed): it then matches the old code again, and anything the server
# saved in the database between the backup and the failed start is lost (the photo files stay).
# A deploy that comes up is tagged server-<time> (pushed to GitHub when the commit is on origin/master), so
# `git tag -l 'server-*'` lists what ran when, and `git diff server-A server-B` is what changed between two.
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
[[ -f $last/packages.txt ]] && ~/.local/bin/uv pip install -q -p ~/$app/.venv/bin/python -r "$last/packages.txt"
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
if [[ -n $(git status --porcelain -- .) ]]; then echo "server/ has uncommitted changes: commit them first"; exit 1; fi
git fetch -q origin master 2>/dev/null || true
[[ $(git rev-parse HEAD) == $(git rev-parse origin/master) ]] || echo "note: deploying $sha, which is not origin/master"

echo "backing up the server's code and database"
stamp=$(date +%Y%m%d-%H%M%S)
remote bash -s "$app" "$stamp" <<'EOF'
set -euo pipefail
app=$1; dir=~/deploy-backups/$2
mkdir -p "$dir"
tar czf "$dir/code.tgz" -C ~/$app sentinel_server pyproject.toml $(cd ~/$app && ls uv.lock 2>/dev/null)
~/.local/bin/uv pip freeze -q -p ~/$app/.venv/bin/python --exclude-editable > "$dir/packages.txt"
~/$app/.venv/bin/python -c "import sqlite3,sys; s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect(sys.argv[2]); s.backup(d); d.close()" \
  ~/$app/data/sentinel.db "$dir/sentinel.db"
ls -1d ~/deploy-backups/*/ | head -n -10 | xargs -r rm -rf   # keep the last 10
EOF

echo "copying $sha"
rsync -a --delete --exclude __pycache__ sentinel_server/ "$host:$app/sentinel_server/"
hash='import hashlib,os,sys; print(hashlib.sha256(b"".join(open(f,"rb").read() for f in sys.argv[1:] if os.path.exists(f))).hexdigest())'
old_deps=$(remote "python3 -c '$hash' $app/pyproject.toml $app/uv.lock")
deps_changed=0
if [[ $old_deps != $(python3 -c "$hash" pyproject.toml uv.lock) ]]; then
  deps_changed=1
  echo "pyproject.toml or uv.lock changed: installing the locked versions"
  # constraints, not requirements: the server keeps the extras it has (bioclip), each at its locked version
  uv export --locked --all-extras --no-emit-project --no-emit-package flat-bug --no-hashes --no-header \
    --no-annotate -q -o constraints.txt.new
  rsync -a pyproject.toml uv.lock "$host:$app/"
  rsync -a constraints.txt.new "$host:$app/constraints.txt" && rm constraints.txt.new
  remote "cd $app && ~/.local/bin/uv pip install -q -p .venv/bin/python -e . -c constraints.txt"
fi

remote bash -s "$app" "$stamp" "$sha" "$deps_changed" <<'EOF'
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
(( $4 )) && ~/.local/bin/uv pip install -q -p ~/$app/.venv/bin/python -r "$dir/packages.txt"
rev='import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); t=c.execute("SELECT 1 FROM sqlite_master WHERE name=?", ("alembic_version",)).fetchone(); print(sorted(r[0] for r in c.execute("SELECT version_num FROM alembic_version")) if t else [])'
if [[ $(~/$app/.venv/bin/python -c "$rev" "$dir/sentinel.db") != $(~/$app/.venv/bin/python -c "$rev" ~/$app/data/sentinel.db) ]]; then
  echo "the new code migrated the database: putting back the one from the backup"
  cp "$dir/sentinel.db" ~/$app/data/sentinel.db.restore
  sudo systemctl stop sentinel-server
  mv ~/$app/data/sentinel.db.restore ~/$app/data/sentinel.db && rm -f ~/$app/data/sentinel.db-wal ~/$app/data/sentinel.db-shm
fi
sudo systemctl restart sentinel-server
exit 1
EOF

tag=server-$(date +%Y-%m-%d-%H%M)
git tag -a "$tag" -m "server deployed to $host" HEAD
if git merge-base --is-ancestor HEAD origin/master; then
  git push -q origin "$tag" || echo "note: could not push tag $tag; push it later with: git push origin $tag"
else
  echo "tagged $tag here only: the commit isn't on origin/master"
fi
