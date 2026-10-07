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

**Who can open it.** The server listens on every network the Mac is on, not only Tailscale, so without a password
anyone on the same Wi-Fi can open the dashboard, submit reviews and press "New liner installed". Set
`SENTINEL_DASHBOARD_PASSWORD=<something>` in `.env` and restart: browsers then ask for it once (any user name).
Traps keep uploading with their own keys. The password travels unencrypted outside Tailscale, so it keeps
passers-by out; it is not a substitute for HTTPS on a real server.

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
| `SENTINEL_DETECTOR=yolo` + `SENTINEL_DETECTOR_MODEL=../ml/models/yolo11/<run>/weights/best.pt` | `uv pip install -p .venv/bin/python -e '.[yolo]'` | Our own YOLO11 from `ml/train_yolo.py`. The photo is shrunk to the px/mm the run was trained at, cut into overlapping tiles, and the tiles' boxes merged so an insect on a tile edge counts once. Not the default until a run has been scored on our own liners |
| `SENTINEL_CLASSIFIER=bioclip` | `uv pip install -p .venv/bin/python -e '.[bioclip]'` | BioCLIP 2 zero-shot species ID (model v0) |
| `SENTINEL_CLASSIFIER=bioclip-v1` + `SENTINEL_CLASSIFIER_HEAD=../ml/models/v1/head.npz` | same `[bioclip]` extra | BioCLIP 2 + the linear head from `ml/train_v1.py` (model v1) |
| `SENTINEL_CLASSIFIER=cnn-v2` + `SENTINEL_CLASSIFIER_MODEL=../ml/models/v2/efficientnet_b0.pt` | same `[bioclip]` extra (brings torch + torchvision) | fine-tuned CNN from `ml/train_v2.py` (model v2) |

The default `baseline` detector needs no downloads: it finds the liner's printed grid (which gives the
scale in px/mm and, with a wide lens, how much to straighten the photo), removes the grid lines, and keeps dark blobs 3–30 mm long. Try any detector on
photos with `sentinel-server detect *.jpg --out overlays/ [--detector flatbug|yolo]`.

Whatever the detector, three rules apply to every photo:

- **Only the card counts.** Where the photo shows a pale card inside a strongly coloured trap (the wide
  IMX219 sees the red walls), boxes off the card or within 4 mm of its edge are dropped; the overlay draws
  the card's outline in green. A photo that is all liner is left alone.
- **A photo whose scale is off is left out.** Every photo of a liner has the same px/mm. One that reads
  more than 20% away from the liner's other photos, or shows no grid when they did, is marked failed
  ("photo not used: …") and changes no counts: its boxes would be sized wrongly.
- **A blurred photo is left out** the same way: sharpness under 40% of the liner's other photos
  (repeat shots of one scene vary by about 30%; a blur of 3 px brings it to 20–25%).
- **Species comes from fresh photos.** A moth's photos count towards its species for 72 hours after it is
  first seen; after that it has lost scales to the glue and later photos only keep it in place.
- **One box per insect.** A box lying mostly inside a bigger one (a body inside its wings, one wing of a
  spread moth) is folded into it. On 16 OFM liner photos, Oct 7 2026: 800 → 768 counted for 328 boxed
  moths, 2 moths lost; 7 pinned specimens went from 31 boxes to 25, and 21 to 17.
- **Context is logged with every photo** (`captures.meta`): px/mm, sharpness, share of the card blown out
  by glare, the card's colour, the liner's age in days and how much of the moon is lit, next to the trap's
  own temperature, humidity and battery. `sentinel-server evaluate` sums them up under "Photos".
- **Two more events**, next to `card_full`: `glare` when over 2% of the card is blown out to white
  (insects there cannot be seen: diffuse or re-aim the LED), and `card_old` when a liner passes
  `SENTINEL_LINER_MAX_DAYS` (default 28: our own choice, not a measured limit).

Measured Oct 7 2026 on the M3 Mac, one 3280 × 2464 photo: baseline 4–5 s and 350 MB peak memory; YOLO11s
on 20–24 tiles 10–12 s. At six photos a day neither is a limit. The baseline shrinks the photo to 1,600 px
wide first (7.5 px/mm on the IMX219); working at full size found 1 more of 211 boxed OFM (189 vs 188),
counted 8% fewer false ones and took 2.4 times as long, so it stays at 1,600.
A photo is about 2.2 MB: six a day is 13 MB a day, about 2.4 GB per trap for a 180-day season on the
server, which keeps every photo. The trap keeps its last 200 sent photos (about a month).

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
