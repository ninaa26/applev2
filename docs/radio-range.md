# Reaching traps further from the hub

How photos get from ESP32 traps to the hub through apple canopy when the traps are out of reach of the
hub's own Wi-Fi. Researched Oct 27–29 2026; prices are from that week's listings and change. Nothing
here has been tried in the orchard yet. Numbers marked \* are our estimates, not measurements or quotes.

**The plan (Oct 29 2026): a 900 MHz Semtech SX1262 radio in FSK mode on each camera and at the hub,
with our own photo-transfer protocol.** About $10–15 a trap and $15–30 a hub. The Semtech LR2021 is the
upgrade if it needs more range or speed, and Wi-Fi HaLow is the fallback if a home-made link doesn't
work out.

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

Free improvements whichever radio is used: put the hub's antenna high (3.5 m or more) at the end of the
rows, looking down the aisles; hang traps as high in the canopy as monitoring allows; lower
`CAM_JPEG_QUALITY` or the frame size so an upload spends less time on air.

## The plan: SX1262 in FSK mode

900 MHz goes through leaves much better than 2.4 GHz, and the SX1262 is the best documented cheap
900 MHz radio: [RadioLib](https://jgromes.github.io/RadioLib/class_s_x126x.html) drives it from Arduino
and ESP-IDF, and Meshtastic and most LoRa boards use it, so help is easy to find. In FSK mode it runs
0.6–300 kbps (in LoRa mode at most 17.4 kbps, too slow for photos).

**Settings to start from:** 915 MHz, 250 kbps, 125 kHz deviation, 500 kHz receive bandwidth, +22 dBm.
The datasheet gives −104 dBm sensitivity there
([SX1261/2 datasheet](https://www.scribd.com/document/448963424/DS-SX1261-2-V1-2)), a link budget of
126 dB against about 118 dB for the ESP32's Wi-Fi at 1 Mbps\*, before 900 MHz's advantage in leaves
(about 8 dB in open air from the frequency alone).

**Photo time:** 200 kB is 6.4 s on air at 250 kbps; with packet overhead and acknowledgements expect
about 10–20 s\*. Six photos a day is under 2 minutes of radio time per trap. A RadioLib user got only
48 kbps from a 300 kbps setting because of per-packet handling
([issue #155](https://github.com/jgromes/RadioLib/issues/155)): use the largest packets (255 bytes) and
interrupt-driven sending.

**FCC (US):** under [47 CFR 15.247](https://www.law.cornell.edu/cfr/text/47/15.247) a digitally
modulated signal with a 6 dB bandwidth of at least 500 kHz may run without frequency hopping, up to
1 W. The settings above should be about that wide\*: measure the signal's bandwidth before relying on
it. If it is narrower, the link must hop channels with a 400 ms dwell limit.

### Parts and cost

| Where | Part | Cost |
|---|---|---|
| Each trap | **Ebyte E22-900M22S** (SX1262, +22 dBm, SPI) | $4.63 (10+), $6.60 for one ([LCSC](https://www.lcsc.com/product-image/C411293.html)) |
| | or Ebyte E22-900M30S (+30 dBm, 1 W; much more current while sending) | $6.99–8.25 (10+), $12.49 for one ([LCSC](https://www.lcsc.com/product-detail/LoRa-Modules_Chengdu-Ebyte-Elec-Tech-E22-900M30S_C411294.html), [X-On](https://www.xonelec.com/mpn/ebyte/e22900m30s)) |
| | or Waveshare Core1262-HF (850–930 MHz, easier to prototype with) | $7.99 ([Waveshare](https://www.waveshare.com/core1262-868m.htm?sku=20855)) |
| | 915 MHz antenna, and a u.FL-to-SMA cable if needed | ~$4–9\* |
| Hub | **Heltec WiFi LoRa 32 V3, US915** (ESP32-S3 + SX1262), on USB to the Pi | $26.97–29.97 ([Rokland](https://store.rokland.com/products/heltec-wifi-lora-32v3)) |
| | or an E22 module on a spare ESP32 | ~$5–12 |
| | optional outdoor 915 MHz antenna on a pole | ~$20–50\* |

Buy the **M** Ebyte parts (E22-900**M**22S, **M**30S): they expose the chip over SPI. The **T** parts
(E22-900**T**22S) are LoRa-only serial modems and can't do FSK. Check the datasheet names the SX1262.

| | Cost |
|---|---|
| Test kit: 1 Heltec V3, 2 E22-900M22S, antennas | ~$45–55 |
| One trap | ~$10–15 |
| One hub (radio only) | ~$15–30, or ~$45–80 with a pole antenna |
| Hub + 20 traps | ~$215–380 |

The base hub is the same whichever radio is used: the Pi, a cellular modem or router (~$40–150\*), a data
plan (~$5–20 a month\*), a box, and solar (~$100–200\*) if it can't be on mains power.

### What we build

- **Camera firmware** (`device/esp32-node/`): drive the SX1262 with RadioLib; split each queued JPEG into
  255-byte packets with a photo id and sequence number; resend what the hub didn't acknowledge; keep the
  photo in flash until the hub has all of it (the queue already works this way). The wake schedule,
  clock sync and **Take a photo now** need small messages both ways over the same link.
- **Hub bridge:** an ESP32 + SX1262 on the Pi's USB that receives packets, acknowledges them and passes
  each finished photo to `gateway.py`, which then handles it exactly as a Wi-Fi upload.
- **Firmware updates over the radio:** about 1–1.5 MB, a couple of minutes at the link's real speed\*.
  To design; until then cameras are updated near the hub over Wi-Fi.
- Wi-Fi stays for pairing, the live preview and the bench.

### Open questions

- **Free pins on the Freenove board:** the SX1262 needs 7 (SCK, MOSI, MISO, NSS, BUSY, DIO1, RESET) next
  to the camera's. Check before ordering in quantity.
- Real throughput and range through leaves, measured on the range walk below.
- Current while receiving and sending, and how long a camera stays awake per photo.
- The signal's measured bandwidth (for the FCC point above).

### Upgrade: Semtech LR2021

The 2025 "LoRa Plus" chip adds FLRC mode, 260 kbps to 2.6 Mbps on 915 MHz, with −111 dBm at 260 kbps
(7 dB better than the SX1262 at a similar speed) and +22 dBm
([Semtech](https://www.semtech.com/products/wireless-rf/lora-plus/lr2021),
[CNX](https://www.cnx-software.com/2026/02/16/lr2021-lora-plus-board-combines-semtech-lr2021-and-nordic-nrf54l15-for-high-speed-flrc-and-lora-connectivity/)).
Semtech demonstrates it sending camera images
([blog](https://blog.semtech.com/fast-long-range-communication-semtech-lr2021-enables-high-speed-image-transfer-without-compromise)).
RadioLib supports it, FLRC included ([`LR2021::beginFLRC`](https://jgromes.github.io/RadioLib/class_l_r2021.html)),
so firmware written for the SX1262 moves over with little change. A US915 kit (two Wio-LR2021 with XIAO
nRF54L15) is about $99–105
([RobotShop](https://www.robotshop.com/products/seeedstudio-semtech-lr2021-lora-evaluation-kit-us915-xiao-nrf54l15));
no price yet for the module alone, and little field history.

## Fallback: Wi-Fi HaLow

If the home-made link is too slow or too much work, HaLow is Wi-Fi at 900 MHz: the cameras keep
joining a network and POSTing photos over HTTP, so scheduling, firmware updates and the live preview
carry over, at about twice the cost.

- **Evidence.** LUMA Lab's ESP32-S3 HaLow camera (Heltec HT-HC33) to a Heltec HT-HD01 access point in
  an apple orchard: 1.16 Mbps upload at 301 m, 0.40 Mbps at 534 m (−90 dBm), 0.05 Mbps at 640 m. Their
  earlier 4G version "could not maintain a consistently stable connection" there
  ([Heltec/LUMA](https://wiki.heltec.org/news/into-the-orchard-real-world-long-range-wi%E2%80%91fi%E2%80%91halow-testing/into-the-orchard-real-world-long-range-wi%E2%80%91fi%E2%80%91halow-testing)).
  A 14-acre farm trial kept 1.3 Mbps at its most obstructed points
  ([Wi-Fi Alliance](https://www.wi-fi.org/beacon/neil-weste/the-future-of-farming-testing-the-rural-range-of-wi-fi-certified-halow)).
  Both are vendor or trade-group results.
- **Hub:** [GL.iNet HaLowLink 2](https://www.cnx-software.com/2026/01/13/halowlink-2-wi-fi-halow-access-point-and-extender-offers-up-to-1-km-range-supports-up-to-1000-iot-end-devices/),
  $129, Ethernet to the Pi, 5 V 2 A, 0–40 °C (needs a shaded box). Avoid Pi HATs: the Alfa AHPI7292S
  image is 2022 Bullseye and kernel upgrades break its driver
  ([BeyondLogic](https://www.beyondlogic.org/building-an-updated-802-11ah-driver-for-the-alfa-network-ahpi7292s/)).
- **Trap:** [Seeed Wio-WM6180 for XIAO](https://www.seeedstudio.com/Wio-WM6180-Wi-Fi-HaLow-Module-for-XIAO-p-6395.html),
  $14.90 + antenna, on the Freenove (keeps the OV5640); or the
  [Heltec HT-HC33](https://heltec.org/project/ht-hc33/) ($24–27, its camera sensor not stated).
- **Firmware:** Morse Micro's driver is an ESP-IDF component
  ([registry](https://components.espressif.com/components/morsemicro/halow/versions/2.11.2-esp32-2/readme));
  no published sleep current or rejoin time, and known power-save bugs on some MM6108 boards
  ([Morse community](https://community.morsemicro.com/t/seeed-xiao-esp32s3-halow-module-mm-iot-esp32-for-mqtt-communication/712)).
- **Cost:** hub $129, trap ~$19, hub + 20 traps ~$510.

## Comparison

| | Today: hub's Wi-Fi | **Plan: SX1262 FSK** | Upgrade: LR2021 FLRC | Fallback: HaLow |
|---|---|---|---|---|
| Band | 2.4 GHz | 915 MHz | 915 MHz | 915 MHz |
| Speed used | ~1 Mbps | 250 kbps | 260 kbps–1.3 Mbps | ~0.4–1 Mbps |
| Sensitivity at that speed | ~−98 dBm\* | −104 dBm | −111 dBm at 260 kbps | about −90 dBm at 534 m in the orchard test |
| One 200 kB photo | ~1 s | ~10–20 s\* | ~2–15 s\* | ~1–4 s |
| Range in canopy | ~40–100 m\* | not measured; well beyond Wi-Fi\* | further than the SX1262\* | 300–530 m measured |
| Hub radio cost | $0 | ~$15–30 | ~$50 (half a kit) | $129 |
| Per-trap cost | $0 | ~$10–15 | not yet sold alone | ~$19 |
| Networking | HTTP | our own protocol | the same protocol | HTTP |
| Live preview, firmware updates | yes, yes | no, to design | no, to design | yes, yes |

## Sending less helps any radio

The liner changes little between photos. Sending a full photo now and then and only the tiles with
something new in between could cut an upload by roughly 5–20×\*. A published LoRa system does this with
patch-level change detection ([ScienceDirect](https://www.sciencedirect.com/science/article/pii/S254266052500215X)).
The server would rebuild each photo before detection.

## Ruled out

| Option | Why not |
|---|---|
| Si4463 (Silicon Labs, 4GFSK to 1 Mbps) | Faster, but no published sensitivity at speed (about −97 dBm at 1 Mbps\*), and thin libraries: Zak Kemble's Si446x is AVR-focused ([GitHub](https://github.com/ZakKemble/Si446x)), RadioHead's `RH_RF24` needs Silicon Labs' WDS tool for its settings |
| RFM69HCW (SX1231) | Well documented (LowPowerLab, Moteino), but 61-byte messages and weaker sensitivity at speed; the SX1262 replaces it |
| CC1101 | Only about +10 dBm on common modules ([Ebyte E07](https://www.rcscomponents.kiev.ua/datasheets/e07-915ms10_usermanual_en_v1_20.pdf)) |
| TI CC1312R / CC1352 | Up to 4 Mbps, but a second microcontroller with TI's own SDK |
| SiK / RFD900x telemetry radios | Built-in FCC hopping and a serial link, but point to point, $59–199 each ([Holybro](https://holybro.com/products/sik-telemetry-radio-v3), [IRLock](https://irlock.com/products/rfd-900x-modem)) |
| LoRa / LoRaWAN | 17.4 kbps at best; minutes per photo |
| nRF24L01+ PA+LNA, XBee 3 (XB3-24DMPT-J) | 2.4 GHz, so no better through leaves than Wi-Fi, and slower |
| XBee-PRO 900HP / XR 900 | Works (about 105 kbps measured by Digi), but $50–90 per trap ([datasheet](https://cdn.sparkfun.com/datasheets/Wireless/Zigbee/90002173_N.pdf)) |
| Mesh between traps | Traps near the hub carry everyone's photos and drain first. Fixed solar relays where needed are simpler |
| Cellular in every trap | No hub, but ~$30–45 per board\* and ~$2 a month per trap ([Hologram](https://www.hologram.io/pricing/)); LTE-M under canopy unproven |

How commercial traps do it: Trapview puts a cellular modem in each trap; Semios runs its own radio
network with repeater antennas in the orchard ([Good Fruit Grower](https://goodfruit.com/a-new-image-of-pest-control/)).

## Steps

1. **Order the test kit** (~$45–55): a Heltec WiFi LoRa 32 V3 (US915) and two E22-900M22S with antennas.
   Check the Freenove's free pins against the module's 7.
2. **Bench sketch:** send a stored 200 kB photo in 255-byte packets with acknowledgements at the
   settings above; log time per photo, packets resent and current drawn.
3. **Range walk, leaves on:** walk out from the hub spot along a row and across rows, and at each stop
   log RSSI and whether a whole photo arrives, next to today's Freenove on the hub's Wi-Fi
   (`device.rssi` is already in each photo's metadata).
4. **If it reaches the farthest trap position:** build the camera side and the hub bridge as above. If not,
   try the E22-900M30S, a higher hub antenna, or an LR2021 kit; if a home-made link still falls short,
   go to HaLow.
