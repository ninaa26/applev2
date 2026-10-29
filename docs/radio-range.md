# Reaching traps further from the hub

Options for getting photos from ESP32 traps to the hub through apple canopy, when the traps are out of
reach of the hub's own Wi-Fi. Researched Oct 27–29 2026; prices are from that week's listings and change.
Nothing here has been tried in the orchard yet. Numbers marked \* are our estimates, not measurements
or quotes.

The constraints: no Wi-Fi or internet in the field, only the hub's cellular uplink. Each photo is about
200 kB, 6 a day per trap. Cameras are battery powered and deep-sleep between wakes.

## Why the current Wi-Fi runs out

2.4 GHz loses a lot in leafy canopy, worst with the antennas low in the trees:

- Young apple orchard, low-power 2.4 GHz nodes: about 10% packet loss at 20–40 m, up to 80% beyond 40 m,
  worst at low heights ([Propagation model for 2.4 GHz WSN](https://www.proquest.com/scholarly-journals/propagation-model-2-4-ghz-wireless-sensor-network/docview/1661322493/se-2)).
  An orchard channel study recommends antennas about 3.5 m high
  ([Springer](https://link.springer.com/chapter/10.1007/978-3-642-27278-3_34)); near the canopy top the
  leaves matter much less ([plum orchard](https://www.sciencedirect.com/science/article/abs/pii/S1537511012001481)).
- An ESP32 with a 3 dBi external antenna read 7 dB stronger than its onboard antenna at 50 m
  ([conference paper](https://prosiding.pnj.ac.id/index.php/SNTE/article/download/6198/3398/31970)).
  With onboard antennas "any minor obstruction" broke a link beyond about 50 m
  ([ArduPilot forum](https://discuss.ardupilot.org/t/simple-esp-telemetry-serial-bridges/75536)).
- Espressif's long-range Wi-Fi mode (`WIFI_PROTOCOL_LR`) showed no range gain in the reports we found
  ([esp32.com](https://esp32.com/viewtopic.php?p=18535)).

Expect about 40–100 m from the hub inside the canopy with today's boards\*, more down an open row.
Every extra hub costs another cellular modem, power setup and data plan, so range decides the cost.

Free improvements whichever option is chosen: put the hub's antenna high (3.5 m or more) at the end of
the rows, looking down the aisles; hang traps as high in the canopy as monitoring allows; lower
`CAM_JPEG_QUALITY` or the frame size so an upload spends less time on air.

## The two options

Both use 900 MHz, which goes through leaves much better than 2.4 GHz. Buy US 902–928 MHz versions.

| | Today: hub's Wi-Fi | **A. Wi-Fi HaLow** | **B. DIY FSK radio (Si4463)** |
|---|---|---|---|
| Hub parts | the Pi's own Wi-Fi | GL.iNet HaLowLink 2, Ethernet to the Pi | Si4463 module (e.g. NiceRF RF4463PRO) on an ESP32 plugged into the Pi by USB, or on the Pi's SPI |
| Hub cost | $0 | $129 | ~$10–20\* |
| Per-trap parts | Freenove ESP32-S3 + OV5640 | Seeed Wio-WM6180 HaLow module + 900 MHz antenna on the Freenove | Si4463 module + 900 MHz antenna on the Freenove |
| Per-trap cost | $0 | ~$19 | ~$5–10\* |
| Hub + 20 traps, added | $0 | ~$510 | ~$110–220\* |
| Range in canopy | ~40–100 m\* | 300–530 m measured in an apple orchard | likely similar to HaLow at the same speed\*; not measured |
| One 200 kB photo | ~1 s | ~1–4 s; ~30 s at the edge of range | ~2–10 s\* |
| Networking | HTTP, as now | HTTP, as now (still Wi-Fi) | our own: chunks, acknowledgements, retries |
| Firmware updates, live preview | yes | yes | slow; no preview |
| Firmware work | none | port Wi-Fi to Morse Micro's ESP-IDF driver | write the transfer protocol on both ends; FCC rules may need channel hopping |
| Maturity | works | measured in an orchard; new on ESP32 | no published image or orchard test found |

All three still need the base hub: the Pi, a cellular modem or router (~$40–150\*), a data plan
(~$5–20 a month\*), a box, and solar (~$100–200\*) if it can't be on mains power.

### A. Wi-Fi HaLow (802.11ah)

Wi-Fi in the 900 MHz band, so the cameras still join a network and POST photos over HTTP; wake
scheduling, firmware updates and the live preview carry over.

- **Evidence.** LUMA Lab's ESP32-S3 HaLow camera (Heltec HT-HC33) to a Heltec HT-HD01 access point in
  an apple orchard: 1.16 Mbps upload at 301 m, 0.40 Mbps at 534 m (−90 dBm), 0.05 Mbps at 640 m. Their
  earlier 4G version "could not maintain a consistently stable connection" there
  ([Heltec/LUMA](https://wiki.heltec.org/news/into-the-orchard-real-world-long-range-wi%E2%80%91fi%E2%80%91halow-testing/into-the-orchard-real-world-long-range-wi%E2%80%91fi%E2%80%91halow-testing)).
  A 14-acre farm trial kept 1.3 Mbps at its most obstructed points
  ([Wi-Fi Alliance](https://www.wi-fi.org/beacon/neil-weste/the-future-of-farming-testing-the-rural-range-of-wi-fi-certified-halow)).
  Both are vendor or trade-group results.
- **Hub.** [GL.iNet HaLowLink 2](https://www.cnx-software.com/2026/01/13/halowlink-2-wi-fi-halow-access-point-and-extender-offers-up-to-1-km-range-supports-up-to-1000-iot-end-devices/),
  $129: Morse Micro MM8108, OpenWrt, two Ethernet ports, 5 V 2 A over USB-C (measure its draw if the
  hub is on solar), 0–40 °C so it needs a shaded box. A standalone access point is safer than a Pi HAT:
  the Alfa AHPI7292S image is 2022 Bullseye and kernel upgrades break its driver
  ([BeyondLogic](https://www.beyondlogic.org/building-an-updated-802-11ah-driver-for-the-alfa-network-ahpi7292s/)).
  Heltec's HT-H7608 (~$80–157) and HT-HD01 ($69–138) are alternatives.
- **Trap.** [Seeed Wio-WM6180 for XIAO](https://www.seeedstudio.com/Wio-WM6180-Wi-Fi-HaLow-Module-for-XIAO-p-6395.html),
  $14.90, client only (fine for a camera), keeps the calibrated OV5640. Check that it fits the
  Freenove's free pins. The alternative is the [Heltec HT-HC33](https://heltec.org/project/ht-hc33/)
  ($24–27, ESP32-S3 + HaLow + camera on one board, 120° or 160° lenses), but its camera sensor is not
  stated (listings suggest 2–3 MP), so it would need a new camera check and calibration.
- **Firmware.** Morse Micro's driver is an ESP-IDF component
  ([registry](https://components.espressif.com/components/morsemicro/halow/versions/2.11.2-esp32-2/readme));
  `device/esp32-node/` is Arduino on PlatformIO.
- **Unknowns.** No published sleep current or time to rejoin after deep sleep, and known power-save bugs
  on some MM6108 boards ([Morse community](https://community.morsemicro.com/t/seeed-xiao-esp32s3-halow-module-mm-iot-esp32-for-mqtt-communication/712)).
  The cameras power down between wakes, so the join time is what matters.

### B. DIY FSK radio

A plain sub-GHz FSK transceiver on each camera and at the hub, with our own transfer protocol. The
cheapest hardware that could carry whole photos through the canopy.

- **Chip.** Silicon Labs Si4463: up to 1 Mbps with 4GFSK. The Semtech SX1262 in FSK mode tops out at
  300 kbps ([RadioLib](https://jgromes.github.io/RadioLib/class_s_x126x.html)), and in LoRa mode at
  17.4 kbps (SF7, 500 kHz), about 92 s on air for one photo
  ([NiceRF comparison](https://www.nicerf.com/news/selection-comparison-of-lora-module-and-fsk-module.html)).
  NiceRF's −126 dBm for the Si4463 is its lowest-speed sensitivity; at fast settings expect about
  −95 to −100 dBm\*, so range shrinks as speed rises. Real throughput is well under the air rate:
  a RadioLib user measured 48 kbps at a 300 kbps setting on an SX1278
  ([issue #155](https://github.com/jgromes/RadioLib/issues/155)).
- **Driver.** RadioHead's `RH_RF24` supports the Si4460/4461/4463\*; the chip is configured with Silicon
  Labs' WDS tool. The SX1262 is easier (RadioLib) but slower.
- **What we'd write.** Split each JPEG into packets, acknowledge and resend lost ones, reassemble on the
  hub and hand the photo to `gateway.py`; agree on wake windows (the hub already sets each camera's
  wake times); firmware updates over the same link.
- **FCC.** Under 15.247 a wide enough signal (6 dB bandwidth of 500 kHz or more) needs no hopping;
  narrower ones must hop channels with a 400 ms dwell limit\*. Check the chosen settings.
- **Evidence.** None for images through canopy. LoRa image projects that do the same chunking take
  1–30 min per HD image ([LoRa_Camera_Trap](https://github.com/Atrop1n/LoRa_Camera_Trap)) and need
  retransmission to recover losses ([LoRa image bridge](https://github.com/Nonnanaw/Long-Range-Wireless-Image-Transmission-System-using-LoRa),
  [MDPI review](https://www.mdpi.com/2313-433X/12/9/442)).

## Sending less helps both

The liner changes little between photos. Sending a full photo now and then and only the tiles with
something new in between could cut an upload by roughly 5–20×\*, which makes the slow end of either
option much more comfortable. A published LoRa system does this with patch-level change detection
([ScienceDirect](https://www.sciencedirect.com/science/article/pii/S254266052500215X)). The server
would rebuild each photo before detection.

## What we ruled out

| Option | Why not |
|---|---|
| LoRa / LoRaWAN | 17.4 kbps at best; minutes per photo, US 400 ms dwell limit. Fine for counts or thumbnails only |
| nRF24L01+ PA+LNA, XBee 3 (XB3-24DMPT-J) | 2.4 GHz, so no better through leaves than Wi-Fi, and slower; the XB3's PCB antenna can't be upgraded |
| XBee-PRO 900HP / XR 900 | Works (about 105 kbps measured by Digi, 32.5 kbps over 3 mesh hops), but $50–90 per trap ([datasheet](https://cdn.sparkfun.com/datasheets/Wireless/Zigbee/90002173_N.pdf)) |
| Mesh between traps | Traps near the hub carry everyone's photos and drain first; a big firmware job on Wi-Fi. Fixed solar relays where needed are simpler |
| Cellular in every trap | No hub, but ~$30–45 per board\* and ~$2 a month per trap ([Hologram](https://www.hologram.io/pricing/)); LTE-M coverage under canopy unproven |

How commercial traps do it: Trapview puts a cellular modem in each trap; Semios runs its own radio
network with repeater antennas in the orchard ([Good Fruit Grower](https://goodfruit.com/a-new-image-of-pest-control/)).

## Next step: a range walk

With leaves on, walk out from the hub spot along a row and across rows, and at each stop log signal
strength and whether a real photo uploads, for each radio side by side:

1. Today's Freenove on the hub's Wi-Fi (baseline; `device.rssi` is already in each photo's metadata).
2. A HaLowLink 2 and a Freenove with the Wio-WM6180 (~$150).
3. Two Si4463 modules sending a stored photo in chunks (~$15).

Pick the cheapest one that reaches the farthest trap position.
