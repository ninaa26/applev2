# ESP32 camera traps through a hub Pi

One Raspberry Pi in the orchard is the **hub**. More traps, each with an ESP32-S3 camera board instead
of a Pi, hang in Wi-Fi range of it. Every wake they photograph their liner, send the photo to the hub,
and deep-sleep. The hub uploads their photos to the server with its own.

```
ESP32 trap T2 ─┐  Wi-Fi (hub's access point)                 Tailscale
ESP32 trap T3 ─┼──────────────────────────► hub Pi T1 ───────────────────► server (Mac)
ESP32 trap T4 ─┘  POST photo, GET schedule   gateway.py: queue per trap,   /api/v1/captures,
                                             upload with each trap's key   /api/v1/hub/nodes
```

- **Server:** each ESP32 is a trap of its own, with its own key, page, liner, photos and counts. It is
  marked as an ESP32 camera and names its hub. Cameras are added and removed on the dashboard's
  **Set up traps** page (or `sentinel-server add-trap T2 --lure CM --kind esp32 --hub T1`). Removing
  one hides it and stops its key, and keeps its photos and counts. **Put back** undoes it.
- **Hub:** `sentinel_device/gateway.py`. Each wake it asks the server which ESP32 traps are its own
  (`GET /api/v1/hub/nodes`: their ids and key hashes, cached for wakes without a connection), so the
  hub needs no change when cameras are added or removed. The cycle opens the gateway while it
  photographs its own liner, and keeps it open for `[hub] window_s` (240 s), or less once every node
  has checked in. Then it uploads its own queue and every node's queue (`data_dir/nodes/<trap_id>/`)
  with each node's key, and powers off as before.
- **ESP32 trap:** `device/esp32-node/` (PlatformIO). Each wake it takes a photo and saves it to flash,
  joins the hub's Wi-Fi, and uploads everything queued, oldest first. It asks the hub when to wake
  next, then deep-sleeps. A photo stays on the ESP32 until the hub has it, so a missed window costs
  nothing but delay. The queue has 5.9 MB of flash, room for roughly 40–60 UXGA photos; when it is full the oldest go first.

## Timing

The hub wakes on its schedule (`[schedule] times`). Nodes aim for `node_offset_s` (60 s) after each
slot, when the hub has booted and its access point is up. Each reply from the hub carries the time and
the next 12 wake times, so a node that misses the hub once still wakes for the next slot.

The ESP32's sleep clock is an RC oscillator that can be off by a few percent. The node never sets its
clock. It measures the hub's time against its own on every contact, works out its drift from
successive contacts, and corrects the next sleep. It also wakes early by `15 s + 0.3%` of the sleep
(about 2.5 min before a 12 h slot) and keeps trying the hub's Wi-Fi for 2–5 min. A node that has
never reached the hub tries every 10 min, so run the hub's gateway standalone while installing nodes
(below).

What this costs the hub: each wake it stays on up to `window_s` longer, 4 min by default against about
1.5 min without nodes. The systemd unit allows the cycle 600 s.

## Wi-Fi between the hub and the traps

The hub's onboard Wi-Fi already connects it to the internet (orchard Wi-Fi or a phone hotspot), and one
radio can't reliably be a client and an access point at once. Choose one:

- **USB Wi-Fi adapter on the hub as the access point (recommended).** It needs one whose chipset
  supports AP mode on Linux (`iw list` shows `AP` under "Supported interface modes"). Choose one with
  a screw-on antenna: a bigger antenna on the hub also extends range to the traps. `wlan0` stays the
  uplink.
- **Onboard Wi-Fi as the access point**, if the hub reaches the internet some other way (Ethernet, or
  a USB LTE modem).

Access point with NetworkManager (Pi OS Bookworm). `ipv4.method shared` gives the hub 10.42.0.1 and
hands out addresses to the traps:

```bash
sudo nmcli con add type wifi ifname wlan1 con-name sentinel-hub autoconnect yes ssid sentinel-hub \
  mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 ipv4.method shared \
  wifi-sec.key-mgmt wpa-psk wifi-sec.psk 'choose-a-password'
sudo nmcli con up sentinel-hub
```

**Range is not measured yet.** Expect less than in open air: 2.4 GHz through leafy apple canopy loses
a lot. Every photo's metadata carries the node's signal strength (`device.rssi`). Before hanging a
trap, take its board to the spot and check that the hub hears it at better than about -80 dBm. For
traps further out, ESP32-S3 boards with an antenna connector (WROOM-1U modules) and an external
antenna are the next step.

## Adding and removing ESP32 traps

Once, on the hub: `[hub] enabled = true` in `/etc/sentinel/config.toml`, and its access point (above).

For each camera:

1. Dashboard → **Set up traps** → Add a camera: ESP32 camera, its hub, trap id, name, block and lure.
   The page shows the camera's key **once**, as the two lines for `node_config.h`.
2. Firmware: `cd device/esp32-node && cp include/node_config.example.h include/node_config.h`. Paste
   those two lines, fill in the hub's Wi-Fi name and password and the LED pin, and flash it:
   `pio run -t upload` ([esp32-node/README.md](../device/esp32-node/README.md)).
3. Hang it and power it. The hub accepts it from its next wake. To see the first photo straight away,
   run `sentinel-gateway --config /etc/sentinel/config.toml --forward-every 60` on the hub (it refreshes
   the camera list every minute), or do the first contact on the bench.

To take a camera out, press **Remove** on the same page. The hub stops taking its photos from its next
wake. Photos already queued on the hub still go up, and the server keeps all of them. A lost or
reflashed board can get a **New key**.

Cameras can also be listed by hand in the hub's config (`[hub.nodes.T2] api_key = "..."`), for a
bench hub that has no server to ask.

## Bench test without the orchard

The gateway runs on a Mac too. Put the Mac and the ESP32 on the same Wi-Fi, set `HUB_URL` to
`http://<mac's address>:8080`, and give the Mac a config with `data_dir` somewhere writable,
`server_url = "http://localhost:8000"`, the hub trap's `trap_id` and `api_key`, and `[hub] enabled = true`,
then run `sentinel-gateway --config that.toml --forward-every 30` beside `sentinel-server serve`.

## Status (Oct 8 2026)

- Built and tested: the gateway and the hub cycle (`device/tests/test_gateway.py`), adding and removing
  cameras on the dashboard (`server/tests/test_manage.py`), and on this Mac: a camera added on the
  dashboard, picked up by a real `sentinel-gateway`, a photo posted the way the firmware does with its
  key, and on its trap page seconds later. The node firmware compiles. The camera check found the board's pins (ESP32-S3-EYE / Freenove layout) and an OV3660,
  and took 1600×1200 photos over USB.
- Not yet done: the node on real Wi-Fi with a hub, drift correction over real sleeps, range in the
  orchard, and the ESP32's deep-sleep current (dev boards have a power LED and USB chip that draw
  power even while the ESP32 sleeps).
- ESP32 photos get no white-card correction (`flatfield.npz` is done on the Pi), so they reach the
  server uncorrected. Exposure is auto unless `CAM_AEC_VALUE`/`CAM_AGC_GAIN` are set. Calibrate per
  trap as for a Pi.
