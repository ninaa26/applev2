# Running the server on Linux (the Pi 5 now, a cloud server later)

The server takes the photos the hub sends, detects, classifies and counts insects, and serves the
dashboard. It all runs in one process (`sentinel-server serve`). Since Oct 22 2026 it runs on a
Raspberry Pi 5 (`apple-pi-server`) standing in for a cloud server we'll rent later. The same steps
work on any Linux machine: moving means copying `server/data/` and changing the hub's `server_url`.
For the Mac, see [server-on-mac.md](server-on-mac.md).

## How big a machine

| | Need |
|---|---|
| Memory | **8 GB**. The server with the v1 classifier (BioCLIP 2) uses about 2.2–3 GB. On the 4 GB Pi 5 a second copy of the model, loaded by hand while the server ran, ran it out of memory (Oct 22 2026), and the server itself went into swap on a cluttered photo. |
| CPU | Light. On the 4 GB Pi 5, 20–30 s per ESP32 photo with the classifier; 20 traps × 6 photos a day is under an hour of work a day. No GPU needed. |
| Disk | ESP32 photos are about 200 kB: about 0.2 GB per trap per season. 20–50 GB is plenty. |

Candidates for later: AWS Lightsail's 8 GB plan ($44 a month: 2 vCPUs, 160 GB SSD, 5 TB transfer,
from AWS's price list on Oct 22 2026), a similar machine elsewhere, or a Pi 5 with 8 GB and an NVMe SSD.

## Setup (once)

On Raspberry Pi OS (64-bit) or Ubuntu, logged in as the user that will run it (`pi` below):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh                  # uv, which brings Python 3.12
git clone https://github.com/ninaa26/applev2.git ~/applev2
cd ~/applev2/server && ~/.local/bin/uv sync --locked --python 3.12 --extra bioclip  # torch + open_clip for the classifier
```

The classifier's head is not in git: copy it from the machine that trained it, for example
`scp ml/models/v1/head.npz pi@apple-pi-server:applev2/ml/models/v1/`.

`cp .env.example .env` and set:

```
SENTINEL_CLASSIFIER=bioclip-v1
SENTINEL_CLASSIFIER_HEAD=../ml/models/v1/head.npz
SENTINEL_DASHBOARD_PASSWORD=<something>
```

Then create the database and the hub:

```bash
.venv/bin/sentinel-server init
.venv/bin/sentinel-server add-trap T1 --kind hub --name "Fieldhouse hub"     # prints the hub's key
```

The ESP32 cameras are added on the dashboard (**Set up traps**). A database from before hubs had their
own kind has the hub as a Pi camera trap: `sentinel-server set-kind T1 hub` turns it into a hub, which
drops it from the trap table and the orchard totals.

## Keep it running

[server/systemd/sentinel-server.service](../server/systemd/sentinel-server.service) starts it at boot and
restarts it if it stops (edit the user and paths for another machine):

```bash
sudo cp ~/applev2/server/systemd/sentinel-server.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now sentinel-server
journalctl -u sentinel-server -f        # "worker started (baseline-cv-0.4+bioclip2-v1:v1)"
```

The first start downloads BioCLIP 2 (about 1.6 GB, to `~/.cache/huggingface`). After `git pull` or a
change to `.env`: `sudo systemctl restart sentinel-server`.

## Deploying a fix

From the Mac, in the repo, on the commit to deploy (normally `master` after the pull request is merged):

```bash
server/deploy.sh                 # to pi@apple-pi-server; server/deploy.sh <user@host> for another
server/deploy.sh --rollback      # put back the code and database from before the last deploy
```

It saves the server's code and a snapshot of its database to `~/deploy-backups/<time>/` (the last 10 are
kept), copies `server/sentinel_server/` over, installs the versions in `uv.lock` if it or `pyproject.toml` changed, and
restarts. If `/healthz` doesn't answer within 60 s it puts the old code and packages back and restarts again. The deployed commit is
in `~/applev2/server/DEPLOYED`. Hubs and cameras: [esp32-traps.md](esp32-traps.md#fixing-and-updating-in-the-field).

## Back it up

Everything the season produces is in `server/data/`: the database and the photos. One dead SD card loses
it all, so a copy goes to another machine every night. `sentinel-server backup` takes a snapshot of the
database with SQLite's backup API (safe while the server is writing), copies new photos next to it,
keeps the last 14 snapshots, and with `--push` rsyncs the folder somewhere else. Nothing is deleted on
the far side.

On the far machine (the team Mac): turn on **Remote Login** in System Settings and add the Pi's SSH key
(`ssh-keygen` on the Pi if it has none, then `ssh-copy-id USER@TEAM-MAC` over Tailscale). Then on the Pi:

```bash
.venv/bin/sentinel-server backup ~/sentinel-backup --push USER@TEAM-MAC:sentinel-backup   # try it once
# edit USER@TEAM-MAC in the ExecStart line, then:
sudo cp ~/applev2/server/systemd/sentinel-backup.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now sentinel-backup.timer
systemctl list-timers sentinel-backup      # next run, 03:30
journalctl -u sentinel-backup              # "backed up sentinel-….db and N new photos"
```

To restore, stop the server, copy the newest `sentinel-*.db` to `server/data/sentinel.db` and the
`media/` folder to `server/data/media/`, and start it again. Restore once on a spare machine to check the
backup works before relying on it.

## Reaching it

Install Tailscale and log in with the team account (`sudo tailscale up --ssh --hostname apple-pi-server`).
The dashboard is then `http://apple-pi-server:8000` from any device on the tailnet, and the hub's
`server_url` is the same address. Turn off key expiry for the server in the Tailscale admin console,
or it drops off the tailnet after about 6 months. A cloud server for growers will want a domain name and
HTTPS (for example Caddy with Let's Encrypt) instead.

**On Cornell's network** a Pi has to be registered before it gets real internet: until then every
website it looks up resolves to Cornell's registration page. Register its Wi-Fi MAC at
mycomputers.cit.cornell.edu (Add Device with No Browser), then reconnect its Wi-Fi. Registration
expires (the Pi 5's runs to Jan 22 2027). If `curl` fails with "certificate is not yet valid", the
clock is wrong: `sudo timedatectl set-ntp true` once it has internet.
