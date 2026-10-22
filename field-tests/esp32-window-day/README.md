# Field test: an ESP32 camera on a window for a day

A proof of concept of the whole chain, with no trap and no liner: the ESP32 camera (T2) on an outside
window → the hub (`apple-pi-hub`, gateway only) → the server (`apple-pi-server`), for about a day, with
both Pis left on. It runs separately from the regular code: these scripts only change the hub's schedule
(and put it back), add two 10-minute logging jobs, and collect everything into `runs/<start>/` (gitignored).

What it answers:
- **Reliability:** a photo for every slot, and an explanation for each one missing.
- **Drift correction over real sleeps:** never tested before, and the most useful single result.
- **Delays:** at each hop, and how the system catches up after an outage.
- **The camera's conditions:** signal through the window, and its temperature in the sun.
- **Resets and duplicates:** no crashes or brownouts, and no photo counted twice.
- **The new features:** check-ins and Take a photo now.
- **Power:** how long the camera is awake, as an estimate of what it uses.

Settings are in [test.env](test.env). The test schedule is a photo every 30 min (about 48 a day) with
check-ins every 10 min, so it also exercises Take a photo now. It needs the camera on firmware 0.2.1 or
later, which reports its awake time.

## Before you leave it

1. **Power and place the ESP32.** Use a USB wall charger (not a power bank, which may switch off while
   it sleeps), or this laptop's USB if you want its serial log (set `ESP32_PORT` in `test.env`). Put
   it at its final spot and plug it in. It starts with a 5-minute live preview (setup mode), then takes
   its first photo.
2. **Run `./start.sh`.** It:
   - runs the health checks on both Pis (clock synchronised, throttling, temperature, disk, memory,
     address, Tailscale, any out-of-memory or under-voltage messages) and saves them;
   - records the hub's RedRover address, since the ESP32 has it built in;
   - sets the hub to the test schedule, keeping its config as `hub.toml.before-window-test`;
   - makes both Pis keep their journals across reboots;
   - installs the loggers and records the camera's starting point (firmware, boots, signal, temperature).
3. **Run `./check.sh` after the first photo from its final spot.** Signal (`rssi`) better than about
   -80 dBm is fine; worse than that through glass means some photos will be lost.
4. **Think about the enclosure.** Direct sun on a sealed box gets hot, and the lens may fog overnight.
   The chip temperature is logged.
5. **Tell the team** the bench Pi is tied up for a day.

## During the day

`./check.sh` any time: the camera's last three wakes, the hub (whether its address changed, the gateway,
the queue, throttling), and the server (photos, processing, memory, errors). On the dashboard
(`http://apple-pi-server:8000`) the hub should show online, and T2's newest photo should be under about
30 min old.

The failure tests each exercise code that has never run outside the bench. Space them out so their
effects don't overlap. Each command logs its time, so the report marks it on every chart.

| Test | Commands | What should happen |
|---|---|---|
| Server down for an hour | `./event.sh server-stop`, about an hour later `./event.sh server-start` | The hub queues the photos, then uploads them all: none lost, no duplicates |
| Hub gateway down across two slots | `./event.sh gateway-stop`, an hour later `./event.sh gateway-start` | The ESP32 keeps its photos in flash and uploads them all at the next contact |
| Hub reboot | `./event.sh hub-reboot` (waits for the gateway to come back) | The gateway starts by itself; the hub shows online again within a minute |
| Power cut on the ESP32 | unplug it for 10 s, then `./event.sh note "ESP32 unplugged 10 s"` | Its next photos are dated by the hub on arrival (`clock_lost`); it runs a 5-minute preview first |
| BOOT pressed once | press it, then `./event.sh note "BOOT pressed"` | An immediate photo with `wake_reason` `manual`, and a fresh liner on the server |
| Take a photo now | `./event.sh photo-now` (or the button on T2's page) | A photo with `wake_reason` `requested` within about 10 min (the check-in interval) |

## At the end

`./finish.sh` saves everything to `runs/<start>/`, puts the hub back on its usual schedule, removes the
loggers, and builds `report.html`. What it saves:
- **Logs:** the gateway's and the server's journals since the start, and both loggers' CSVs.
- **The camera's side:** its end-of-wake statuses, and the server's rows for its photos with the photos themselves.
- **Health:** the same checks as at the start.

`./finish.sh --keep-running` collects and builds the report without ending the test.

`report.html` has the measures below, a chart of each over the day with the events marked, and photos
at dawn, noon, dusk and night. With `LED_PIN -1`, night photos will be black, which shows the light is
needed. `summary.md` has the same numbers as a list.

| Measure | What it tells you |
|---|---|
| Scheduled photos received against slots | Overall reliability. Every missing slot needs an explanation (events, errors) |
| Photo time minus (slot + 60 s), across the day | Drift correction: it should start a few seconds off and get tighter, not wander |
| Camera → hub and hub → server delay | Delay at each hop, and how long it took to catch up after each outage |
| Signal (rssi) and chip temperature | Signal through the window, and heat when the sun is on it |
| Boots | No resets (power loss or crash), and wakes that didn't reach the hub |
| Duplicate photos (`node_capture_id`) | Should be none, even after the outage tests |
| Server status | All `processed`, or `failed` with the expected "no liner grid" reason; none stuck at `new` |
| Take a photo now | Time from each request to its photo |
| Hub address, throttling, memory, database locks | Whether the Pis held up |
| Awake time and power | An estimate (below) |

**Power.** The ESP32 can't measure its own current. Each wake it reports how long it was awake, and the
report multiplies that by assumed currents: `--photo-ma 180`, `--checkin-ma 120` and `--sleep-ma 5`.
The sleep current of a dev board (USB chip, power LED) isn't known and probably dominates the total.
For a real figure, put a logging USB power meter between the charger and the ESP32 for the day. Then
re-run `python3 report.py runs/<start> --sleep-ma <measured>`, or compare the meter's own log.

**Afterwards:** add a dated entry to the Status section of
[docs/esp32-traps.md](../../docs/esp32-traps.md). Say what it was measured on, with the reliability,
drift and rssi results from `summary.md`.

## Paths on the bench Pis

- **The hub** runs from `~/sentinel-hub` (not the `install-hub.sh` layout). Its queue is
  `~/sentinel-hub/data/nodes/T2/{queue,sent}`, and the camera's statuses are in
  `~/sentinel-hub/data/nodes/T2/status.jsonl`.
- **The loggers** write `~/window-test/*.csv` on each Pi.
