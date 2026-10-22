# ESP32 camera traps through a hub

The traps' cameras are ESP32-S3 camera boards. Every wake each one photographs its liner, sends the
photo to the **hub**, and deep-sleeps. The hub is a Raspberry Pi with **no camera**, on mains power
(the orchard's fieldhouse or anywhere with constant power), with a cellular connection to the server.
It keeps every photo until the server has it. The server detects, classifies and counts, and serves
the dashboard.

```
ESP32 trap T2 ─┐  Wi-Fi (hub's access point,      cellular + Tailscale
ESP32 trap T3 ─┼─────────────────────────────► hub T1 ────────────────────► server
ESP32 trap T4 ─┘  or the fieldhouse Wi-Fi)        gateway.py, always on:    Pi 5 now (apple-pi-server),
                  POST photo, GET schedule        queue per trap, upload    a cloud server later:
                                                  with each trap's key      detect, classify, dashboard
```

- **Server:** each ESP32 is a trap of its own, with its own key, page, liner, photos and counts, marked
  as an ESP32 camera and naming its hub. The hub is on the dashboard too, as a **Hub** with no camera:
  it has no counts and no row in the trap table, and shows as online while it keeps checking in.
  Hubs and cameras are added and removed on the dashboard's **Set up traps** page (or
  `sentinel-server add-trap T1 --kind hub` and `sentinel-server add-trap T2 --kind esp32 --hub T1 --lure CM`).
  Removing one hides it and stops its key, and keeps its photos and counts. **Put back** undoes it.
- **Hub:** `sentinel_device/gateway.py`, run always on by `systemd/sentinel-gateway.service`. Every 30 s
  it asks the server which ESP32 traps are its own (`GET /api/v1/hub/nodes`: their ids and key hashes,
  cached for when the server can't be reached), so the hub needs no change when cameras are added or
  removed, and the dashboard sees that the hub is online. It takes photos from the cameras at any time
  and uploads each camera's queue (`data_dir/nodes/<trap_id>/`) with that camera's key every 30 s.
  It needs no camera, LED, sensor or real-time clock.
- **ESP32 trap:** `device/esp32-node/` (PlatformIO). Each wake it takes a photo and saves it to flash,
  joins the hub's Wi-Fi, and uploads everything queued, oldest first. It asks the hub when to wake
  next, then deep-sleeps. A photo stays on the ESP32 until the hub has it, so a missed contact costs
  nothing but delay. The queue has 5.9 MB of flash, room for roughly 40–60 UXGA photos; when it is full the oldest go first.

Which camera module to put on the ESP32 (OV3660 for bring-up, OV5640 wide-angle to buy):
[hardware/CAMERAS.md](../hardware/CAMERAS.md).

A Pi camera trap (`sentinel-cycle`, [bring-up.md](bring-up.md)) can still be a hub as well: its cycle keeps
the gateway open for `[hub] window_s` during each wake. That was the first design; the plan now is
ESP32 cameras only, with an always-on hub.

## Timing

The hub's `[schedule] times` sets when the cameras wake. Each reply from the hub carries the time and
the next 12 wake times, so a camera that misses the hub once still wakes for the next slot. Cameras aim
for `node_offset_s` (60 s) after each slot. With an always-on hub the offset isn't needed, but it does no harm.

A wake takes about 10 s: on the Oct 22 2026 bench run the photo reached the hub 6 s after it was taken,
and the camera asked for its next wake half a second later. Fewer slots means longer batteries: the
example config has 6 a day. The bench hub uses every 15 min for testing.

**Check-ins** (firmware 0.2.0): between photos each camera also wakes every `[hub] checkin_min` (30 min
by default) just to ask whether **Take a photo now** was pressed on its dashboard page. A check-in takes
no photo and gives up on the hub's Wi-Fi after 20 s. So a photo asked for arrives within about
`checkin_min`, plus the server's processing. Its battery cost is not measured yet: 48 Wi-Fi-only
wakes a day against 6 photo wakes. If it shows, raise `checkin_min`, or set it to 0 to turn
check-ins off (then a photo asked for comes with the next scheduled photo).

The ESP32's sleep clock is an RC oscillator that can be off by a few percent. The node never sets its
clock. It measures the hub's time against its own on every contact, works out its drift from
successive contacts, and corrects the next sleep. It also wakes early by `15 s + 0.3%` of the sleep
(about 2.5 min before a 12 h slot) and keeps trying the hub's Wi-Fi for 2–5 min if it can't reach it.
A node that has never reached the hub tries every 10 min.

## Setting up a hub

On a Raspberry Pi 4 or 5 (2 GB is plenty) with Raspberry Pi OS:

1. Network and remote access: get it online (below), install Tailscale (`curl -fsSL https://tailscale.com/install.sh | sh`,
   then `sudo tailscale up --ssh --hostname <name>`) and log it into the team account.
2. Dashboard → **Set up traps** → add it as a **Hub (Raspberry Pi, no camera)**. The page shows its
   `trap_id`, `api_key` and `server_url` **once**.
3. From the repo's `device/` folder: `sudo ./install-hub.sh`. Paste the three lines into
   `/etc/sentinel/config.toml` and set `[schedule] times`
   ([hub.example.toml](../device/hub.example.toml)).
4. `sudo systemctl enable --now sentinel-gateway`, then `journalctl -u sentinel-gateway -f` should show
   `gateway listening on 0.0.0.0:8080 for ...`, and the dashboard shows the hub as online within a minute.

To change the schedule: edit `times` in `/etc/sentinel/config.toml` and
`sudo systemctl restart sentinel-gateway`. Each camera picks up the new times at its next wake.

## The hub's connections

**Uplink to the server: cellular** (not yet tried). Any of these gives the Pi an internet connection:
an LTE router in the fieldhouse that the Pi joins over Ethernet (simplest, and leaves the Pi's Wi-Fi
free for the cameras), a USB LTE modem, or an LTE HAT, both set up with ModemManager/NetworkManager.
Tailscale works over cellular, including behind the carrier's NAT, so the hub reaches the server and
the team can still SSH in. Data use is small: an ESP32 photo is about 200 kB, so 20 cameras at 6
photos a day send about 25 MB a day (0.7 GB a month), plus a little for the hub checking in. If
the fieldhouse has its own Wi-Fi or Ethernet, the hub can use that instead.

**Wi-Fi for the cameras: the hub's own access point.** With cellular or Ethernet as the uplink, the
Pi's onboard Wi-Fi is free to be the access point. NetworkManager's shared mode gives the hub
10.42.0.1 and hands out addresses to the cameras, so `HUB_URL` is `http://10.42.0.1:8080` and never
changes (Pi OS Bookworm):

```bash
sudo nmcli con add type wifi ifname wlan0 con-name sentinel-hub autoconnect yes ssid sentinel-hub \
  mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 ipv4.method shared \
  wifi-sec.key-mgmt wpa-psk wifi-sec.psk 'choose-a-password'
sudo nmcli con up sentinel-hub
```

If the hub's onboard Wi-Fi is its uplink instead (fieldhouse Wi-Fi), use a USB Wi-Fi adapter as the
access point (`ifname wlan1`). It needs a chipset that supports AP mode on Linux (`iw list` shows
`AP` under "Supported interface modes"). One with a screw-on antenna also extends range to the traps.

**Range is not measured yet.** Expect less than in open air: 2.4 GHz through leafy apple canopy loses
a lot. Every photo's metadata carries the node's signal strength (`device.rssi`). Before hanging a
trap, take its board to the spot and check that the hub hears it at better than about -80 dBm. For
traps further out, ESP32-S3 boards with an antenna connector (WROOM-1U modules) and an external
antenna are the next step, and a fieldhouse far from the blocks may need the access point on a mast
or a second hub.

## Adding and removing ESP32 traps

For each camera:

1. Dashboard → **Set up traps** → Add: ESP32 camera, its hub, trap id, name, block and lure.
   The page shows the camera's key **once**, as the two lines for `node_config.h`.
2. Firmware: `cd device/esp32-node && cp include/node_config.example.h include/node_config.h`. Paste
   those two lines, fill in the hub's Wi-Fi name and password, `HUB_URL` and the LED pin, and flash it:
   `pio run -t upload` ([esp32-node/README.md](../device/esp32-node/README.md)).
3. Hang it and power it. The hub accepts it within a minute. Powering it on starts **setup mode**: for
   5 min it streams a live preview, with the LED on, so you can aim it. On a phone on the hub's Wi-Fi,
   open the hub's page, `http://10.42.0.1:8080/` (or `http://<hub's address>:8080/` on other Wi-Fi), and
   follow the camera's **live preview** link. It has a full-size photo for checking focus. When the
   preview ends the camera takes its first photo.
4. Once it points at its liner, **hold BOOT for 3 s**: another preview, then a photo that starts a fresh
   liner on the server. A short press skips the preview and just starts the fresh liner.

To see a camera's liner between scheduled photos, press **Take a photo now** on its page on the
dashboard. It comes at the camera's next check-in (within `checkin_min`, see Timing).

To take a camera out, press **Remove** on the same page. The hub stops taking its photos within a
minute. Photos already queued on the hub still go up, and the server keeps all of them. A lost or
reflashed board can get a **New key**.

Cameras can also be listed by hand in the hub's config (`[hub.nodes.T2] api_key = "..."`), for a
bench hub that has no server to ask.

## Bench test without the orchard

**Hub Pi and ESP32 on the same Wi-Fi (Oct 8 and Oct 22 2026 on RedRover).** No access point is needed
if the Pi and the ESP32 join one network that lets devices reach each other. Cornell's RedRover does:
it took the ESP32 without registering its MAC, and routes between its /16s. A Pi does need registering
(mycomputers.cit.cornell.edu → Add Device with No Browser, with the Pi's Wi-Fi MAC); until then every
website it looks up resolves to Cornell's registration page. In `node_config.h` set `WIFI_SSID "RedRover"`,
`WIFI_PASSWORD ""` and `HUB_URL` to the hub's address on that network (`ip -4 -br addr` on the Pi). That
address comes from DHCP and can change, so check it before a test, and reflash the ESP32 if it moved.

**Hub on a Mac.** The gateway runs on a Mac too. Put the Mac and the ESP32 on the same Wi-Fi, set `HUB_URL` to
`http://<mac's address>:8080`, and give the Mac a config with `data_dir` somewhere writable,
`server_url = "http://localhost:8000"`, the hub's `trap_id` and `api_key`, and `[hub] enabled = true`,
then run `sentinel-gateway --config that.toml --forward-every 30` beside `sentinel-server serve`.

## Status (Oct 22 2026)

- Bench run of the whole chain (Oct 22 2026): ESP32-S3 (OV3660) T2 on RedRover → hub `apple-pi-hub` (the
  bench Pi, gateway only, no camera, every-15-min schedule) → server on a 4 GB Pi 5 (`apple-pi-server`, over
  Tailscale) with the v1 classifier. 23 queued photos went up, and each later wake took about 10 s. The
  ESP32 was pointed at a desk, not a liner, so its photos failed the grid and scale checks: they say
  nothing about accuracy. The 4 GB Pi 5 was too tight for BioCLIP alongside the server (one load ran it
  out of memory); see [server-on-linux.md](server-on-linux.md).
- Earlier bench run (Oct 8 2026): the ESP32 on RedRover at -52 dBm, the gateway on the bench Pi, and a
  scratch `sentinel-server` on the Mac over Tailscale.
- Built and tested: the gateway and the hub cycle (`device/tests/test_gateway.py`), adding and removing
  hubs and cameras on the dashboard and the hub's check-ins (`server/tests/test_manage.py`). The node
  firmware compiles. The camera check found the board's pins (ESP32-S3-EYE / Freenove layout) and an
  OV3660, and took 1600×1200 photos over USB.
- Not yet done: the hub on cellular, the ESP32 on the hub's own access point, drift correction over real
  sleeps, range in the orchard, and the ESP32's deep-sleep current (dev boards have a power LED and
  USB chip that draw power even while the ESP32 sleeps).
- ESP32 photos get no white-card correction (`flatfield.npz` is done on a Pi camera), so they reach the
  server uncorrected. Exposure is auto unless `CAM_AEC_VALUE`/`CAM_AGC_GAIN` are set.
