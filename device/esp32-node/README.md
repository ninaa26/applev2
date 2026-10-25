# ESP32 camera trap firmware

An ESP32-S3 camera board in a delta trap that sends its photos through the hub (a Pi with no camera, always on). How it fits
together, the Wi-Fi setup and adding cameras on the dashboard: [docs/esp32-traps.md](../../docs/esp32-traps.md).

Each wake it photographs the liner and saves the photo to flash. It joins the hub's Wi-Fi, uploads
everything queued (`POST /node/v1/captures`), and asks when to wake next (`GET /node/v1/schedule`).
Then it deep-sleeps. Pressing the button wired to `BUTTON_PIN` (the BOOT button by default) wakes it
and marks the photo as a fresh liner.

- **Setup mode, for aiming the camera:** after it is powered on, or when the button is **held for 3 s**,
  the node joins the hub's Wi-Fi and serves a live preview for 2 min (`SETUP_PREVIEW_S`) with the LED
  on: a page at `http://<node's address>/` (640×480 video, and a full-size photo for checking focus).
  The hub lists it on its own page, `http://<hub>:8080/` (`http://10.42.0.1:8080/` on the hub's access
  point), so open that on a phone on the same Wi-Fi. When the preview ends the node takes its photo
  (a fresh liner if the button started it) and carries on as normal. Each power-on runs it once, so a
  power cut in the field costs one 2-minute preview.
- **Check-ins:** between photos the node wakes every `checkin_s` (from the hub's `[hub] checkin_min`,
  default 30 min) just to ask the hub whether **Take a photo now** was pressed on the dashboard. A
  check-in takes no photo, tries the hub's Wi-Fi for at most 20 s, and is a few seconds awake; if a
  photo was asked for, it takes and sends one. `checkin_min = 0` turns check-ins off.

## Build and flash

PlatformIO (`pip install platformio`, or the VS Code extension):

```bash
cd device/esp32-node
cp include/node_config.example.h include/node_config.h   # then fill it in; it is gitignored
pio run -t upload
pio device monitor                                        # 115200 baud
```

`flash-camera.sh` does the copy and the upload. With no arguments it wipes the board and flashes the
**release build** (`pio run -e release`), which has no trap id or key: the camera pairs with its hub and is
added on the dashboard, and the script prints its pairing code. With `T3 <key>` (the command the dashboard
shows for a camera added by hand) it flashes the dev build with that id and key. Either way the Wi-Fi and
pins stay in `node_config.h`. `release.sh` builds the file for updating cameras over the air from the
dashboard. How both work: [docs/esp32-traps.md](../../docs/esp32-traps.md#adding-and-removing-esp32-traps).

The board this was written for: a Freenove-style ESP32-S3 CAM (N8R8: 8 MB flash, 8 MB octal PSRAM,
CH343 USB serial, ESP32-S3-EYE camera pins) with an OV3660. On a Mac the CH343 garbles uploads above
115200 baud, which is why `upload_speed` is 115200 (about 20 s per flash). Other boards need their
camera pins in `node_config.h` and maybe `board_build.arduino.memory_type` in `platformio.ini`.

`partitions.csv` has two 2 MB app slots, for over-the-air updates (firmware 0.3.0), and gives the rest
of the flash (3.9 MB) to the photo queue. Before 0.3.0 it had one slot and a 5.9 MB queue: a board on 0.2.x
needs one flash over USB to change it.

## Serial output

What a normal wake looks like (format, not a recorded run):

```
sentinel node T2 fw 0.2.5 wake=scheduled boots=14 synced=1
captured /q/00000014-3f9a0c2e71b4d580 1600x1200 142311 bytes
restarting to upload
...
sentinel node T2 fw 0.2.5 wake=scheduled (upload) boots=14 synced=1
wifi sentinel-hub ip 10.42.0.23 rssi -64
upload /q/00000014-3f9a0c2e71b4d580 -> 201
sleeping 1800 s (check-in)
```

Since firmware 0.2.4 a wake that used the camera (a photo, or the setup preview) restarts the chip in a
0.2 s deep sleep after it and uploads from the fresh boot (`(upload)`, same boot count). Uploads in the
same boot as the camera crawled and failed on Oct 22 2026 (`-> -3`, `-> -1` for the rest of the wake),
while the check-ins between them sent 3 photos in a second.

A check-in wake prints `wake=checkin` and no `captured` line, unless the hub says
`photo asked for on the dashboard`. Setup mode prints `wake=setup` and `live preview at http://10.42.0.23/ for 120 s`.

Since 0.3.0 each boot first prints `SENTINEL_FW_VERSION=0.3.0;release` (or `;dev`). A camera not added yet
prints `sentinel node (not added) ...`, `not added yet: pairing code 7F3A2C` and `pair -> 202` until it is
added on the dashboard, then `added on the dashboard as T3` and restarts into setup mode. An update prints
`updating firmware 0.3.0 -> 0.3.1`, `firmware written: restarting into it`, then `wake=update` and
`firmware 0.3.1 reached the hub: keeping it`; if that wake can't reach the hub it prints `ERROR new firmware
didn't reach the hub: going back` and the old firmware starts. `button held 10 s` means it forgot its id and key.

If the hub's Wi-Fi is up but its gateway is not open yet (`upload ... -> -1`), the node tries again every
5 s until the end of its connect window (2–5 min), then sleeps. A node with no schedule from the hub
(never reached it since power-on) looks for it again after 10 min, 20 min, then every 30 min, without a
photo on those wakes (`wake=search`, firmware 0.2.2); one that has a schedule keeps to the hub's times, repeated daily. `wifi ... failed status N mac ...`:
1 means the network was not seen, 4 that it refused the node (the password, or a network that wants
the MAC registered).

`ERROR camera not found`: the ribbon cable is loose or upside down, or the camera's pins differ from
`node_config.h`. `ERROR hub not reachable`: out of range, the wrong Wi-Fi password, or the hub was not
awake (it is awake for a few minutes after each scheduled time). `ERROR hub not answering`: the node
joined the Wi-Fi but the gateway never took the photos before the connect window ran out. `ERROR hub does not know this trap's
key`: the camera was removed on the dashboard, given a new key, or not added yet.
