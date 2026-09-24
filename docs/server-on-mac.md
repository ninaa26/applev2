# Running the server on the team Mac

The Mac runs the API, the dashboard, and the worker that detects and counts insects, all in one process.
Moving to a real server later means copying the `data/` folder and running the same commands there.

## Setup (once)

```bash
brew install uv                       # if needed
cd server
uv venv --python 3.12 .venv
uv pip install -p .venv/bin/python -e '.[dev]'
cp .env.example .env                  # edit if needed
.venv/bin/sentinel-server init
.venv/bin/sentinel-server add-trap T1 --lure CM --name "Bench mockup"   # prints the trap's API key
```

## Run

```bash
caffeinate -s .venv/bin/sentinel-server serve     # caffeinate keeps the Mac awake while plugged in
```

Dashboard: http://localhost:8000 on the Mac, or `http://<mac's tailscale name>:8000` from teammates' laptops and the Pi.

### Keep it running (start at login, restart on crash)

`server/launchd/org.orchardsentinel.server.plist` runs the same command as a macOS LaunchAgent.
It is set up on Nina's MacBook Air; the paths in it are absolute, so edit them for another Mac.

```bash
cp server/launchd/org.orchardsentinel.server.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/org.orchardsentinel.server.plist
```

- Logs: `server/data/server.log`
- Restart after changing `.env` or pulling new code: `launchctl kickstart -k gui/$(id -u)/org.orchardsentinel.server`
- Stop for good: `launchctl bootout gui/$(id -u)/org.orchardsentinel.server`

Don't also start `sentinel-server serve` by hand while it's loaded: the second copy can't get port 8000.

## Tailscale on the Mac

Install the Tailscale app, log in with the team account, and turn on MagicDNS in the Tailscale admin console. The Mac's name (e.g. `sentinel-mac`) is what goes in each trap's `server_url`. Campus Wi-Fi usually blocks devices from reaching each other directly; Tailscale gets around that without opening any ports to the internet.

## Try it without a Pi

The device software has a fake camera that draws a liner collecting moths:

```bash
cd device && uv venv --python 3.12 .venv && uv pip install -p .venv/bin/python -e '.[dev]'
# config.toml: backend = "fake", server_url = "http://127.0.0.1:8000", data_dir = "./data", halt_after_cycle = false,
#              [led] enabled = false, [sensors] sht4x = false
for i in 1 2 3 4 5; do .venv/bin/sentinel-cycle --config config.toml --no-halt; done
```

## Better models (optional, needs ~3 GB of downloads)

| Setting | Install | What it does |
|---|---|---|
| `SENTINEL_DETECTOR=flatbug` | `uv pip install -p .venv/bin/python -e '.[flatbug]'` | Pretrained insect detector, which also works on crowded cards. Weights (50 MB) download to `data/models/` on first use |
| `SENTINEL_CLASSIFIER=bioclip` | `uv pip install -p .venv/bin/python -e '.[bioclip]'` | BioCLIP 2 zero-shot species ID (model v0) |

The default `baseline` detector needs no downloads: it finds the liner's printed grid (which gives the
scale in px/mm and, with a wide lens, how much to straighten the photo), removes the grid lines, and keeps dark blobs 3–30 mm long. Try either detector on
photos with `sentinel-server detect *.jpg --out overlays/ [--detector flatbug]`.

On Apple Silicon both run on the Mac's GPU (`mps`). After switching, re-run old photos with
`sentinel-server reprocess --card <id>`.

## Degree days

The trap only measures temperature when it wakes, which is too few readings for accurate daily max/min.
Import daily data from the nearest NEWA station as a CSV with columns `date,tmax_f,tmin_f`:

```bash
.venv/bin/sentinel-server import-weather ithaca_2026.csv --source newa:Ithaca
```

## Tests

```bash
.venv/bin/pytest -q
```
