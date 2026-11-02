# Radio bridge: the hub's 900 MHz radio

An ESP32 with an SX1262 radio module, on the hub Pi's USB. Cameras beyond the hub's Wi-Fi
(`HUB_LINK_RADIO` in their `node_config.h`, [../esp32-node/README.md](../esp32-node/README.md#radio-link))
send their requests over the radio; this board passes every frame it hears to the Pi and transmits what the
Pi gives back. The protocol lives on the Pi, in `sentinel-radio` (`sentinel_device/radio_link.py`), which
replays each camera's request to the gateway on localhost, so the gateway and the server don't change. Why
this radio, and what else was considered: [docs/radio-range.md](../../docs/radio-range.md).

```
camera (ESP32 + SX1262) ))) 915 MHz ((( bridge (ESP32 + SX1262) --USB--> sentinel-radio --HTTP--> sentinel-gateway
```

The radio settings (915 MHz, 250 kbps GFSK, +22 dBm) and the frame layout are in
[../radio-common/sentinel_radio.h](../radio-common/sentinel_radio.h), shared with the camera firmware, so both
ends always match. More cameras need nothing here: each has its own radio address (from its MAC) and the Pi
keeps their requests apart.

## Wiring (Waveshare Core1262-HF, or an Ebyte E22-900M22S)

| Module | ESP32 DevKit (`env:esp32`) | ESP32-S3 DevKitC (`env:esp32s3`) |
|---|---|---|
| VCC | 3V3 (with 100 µF to GND at the module) | 3V3 |
| GND | GND | GND |
| CS (NSS) | GPIO 5 | GPIO 10 |
| CLK (SCK) | GPIO 18 | GPIO 12 |
| MOSI | GPIO 23 | GPIO 11 |
| MISO | GPIO 19 | GPIO 13 |
| RESET | GPIO 27 | GPIO 9 |
| BUSY | GPIO 26 | GPIO 8 |
| DIO1 | GPIO 25 | GPIO 7 |
| RXEN, TXEN | not connected: the module's DIO2 drives its RF switch | |
| ANT (IPEX) | the 915 MHz antenna, upright | |

Other boards or pins: set `-DRADIO_SCK=...` and the rest in `platformio.ini`. If the module's RF switch
needs the ESP32 to drive it (nothing is heard beyond a metre or two), wire RXEN and TXEN to two free GPIOs
and set `-DRADIO_RXEN=` and `-DRADIO_TXEN=`.

Never power the module without its antenna on: transmitting into nothing can damage it.

## Flash it and plug it into the hub

```bash
cd device/esp32-radio-bridge
pio run -e esp32 -t upload        # or -e esp32s3
pio device monitor                # SLIP frames, not text: just check it resets cleanly, then close it
```

On the hub (`deploy-hub.sh` installs `sentinel-radio` and its service with the rest of the hub code):

```bash
ls /dev/serial/by-id/                                     # the bridge's stable name
echo "RADIO_PORT=/dev/serial/by-id/usb-..." | sudo tee /etc/sentinel/radio.env
sudo systemctl enable --now sentinel-radio
journalctl -u sentinel-radio -f
```

It logs `bridge ready: bridge 0.1.0, 915.0 MHz 250 kbps, TCXO 1.8 V, ...` on start and every minute (with
counts of frames heard, sent and dropped), and one line per camera request:

```
node 3c4d5e6f: POST /node/v1/captures -> 201 (153 kB in 11.2 s, 641 chunks, 9 resent, -88 dBm)
node 3c4d5e6f: GET /node/v1/schedule -> 200 (0 kB in 0.3 s, 2 chunks, 0 resent, -87 dBm)
```

The gateway then handles the photo as one sent over Wi-Fi; `device.hub_rssi` and `device.link: radio` in its
metadata say how strongly the hub heard the camera.

## When it doesn't work

- `radio did not start (RadioLib -2)` in the log: the ESP32 can't talk to the module. Check CS, CLK, MOSI,
  MISO, BUSY and power. `-707`/`-706`: the TCXO setting; it already falls back to a plain crystal, so look at
  the wiring.
- `bridge speaks radio protocol N`: the bridge and `sentinel-radio` are from different versions. Reflash one.
- No `node ...` lines while a camera is awake: check both ends use the same `RADIO_NET` and frequency, both
  antennas are on, and the camera's serial log shows `radio ... address ...` (its radio started).
- Lots of `resent`: weak signal. Raise the hub's antenna, keep it upright, and see docs/radio-range.md.

Written Nov 2 2026; not yet run on the hardware.
