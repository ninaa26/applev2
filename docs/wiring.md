# Wiring: one trap unit

```
              Power (Option A, B or the 12 V build below)
                          │  battery +
                 INA219 (Vin+ → Vin−)  ── I2C ──┐
                          │                      │
                  5 V converter                  │
                          │ USB-C pigtail        │
                  ┌───────▼────────┐             │
                  │ Raspberry Pi 5  │◄────────────┘
                  │  CAM1 ── 500 mm ribbon ── Arducam UC-572, IMX219 wide-angle (in the apex mount)
                  │  J5 BAT ── RTC battery
                  │  GPIO17 ── MOSFET gate ── LED strip (−)
                  │  I2C ── SHT45 (in a small shield outside the box)
                  └─────────────────┘
```

## Power

Plan: **Option A** (DIY single-cell pack with solar). Backup: **Option B** (same pack, no panel, swapped at
each liner change), used if the charger side gives trouble or a trap hangs where the panel gets no sun.
The 12 V build is the off-the-shelf alternative.

Energy budget (estimates, Oct 2026, **not measured**; the full cycle has not run on a Pi yet): each photo
cycle is about 75 s at about 4.5 W, so ~0.15 Wh, or ~0.9 Wh a day at six photos. What sets battery life is
what draws power while the Pi is off (Pi off ~0.01 W, plus the converter and charger idling). With a
converter that idles under 1 mA, a trap needs **about 1.5–2 Wh a day**. Replace these numbers with the
INA219 log from a two-day bench run (see [bring-up.md](bring-up.md), "Before a trap goes out").

### Option A: DIY 1S pack with solar (plan)

```
 6 V 10 W panel ──► CN3791 solar charger board ──► 1S pack ── protection board
                    (TEMP pin ── 10 k NTC on the pack)          │
                                                           3 A inline fuse
                                                                │
                                                     INA219 ── 5 V ≥3 A boost ── Pi 5
```

| Part | Approx. cost (Oct 2026) | Notes |
|---|---|---|
| 6 V 10 W panel | $15–20 | On a post above the canopy, facing south, not in the tree beside the trap |
| CN3791 solar charger board | $3–6 | Sold in a 4.2 V (Li-ion) and a 3.6 V (LiFePO4) version: match the cells |
| 1S pack, ~40 Wh | $16–25 | 4 × 18650 in parallel, or 2 × 32700 LiFePO4. Salvaged laptop cells are fine after a capacity test; all cells in a pack the same type and charge |
| 1S protection board and cell holder | $3–5 | Low-voltage cut-off protects the cells when the panel can't keep up |
| 5 V boost converter, ≥3 A out | $5–10 | Measure its no-load current before using it: under ~1 mA. Not an MT3608 board (too small for a Pi 5) |
| 10 k NTC, fuse, wire | $3–5 | NTC to the CN3791 TEMP pin so it won't charge below 0 °C (April and October frosts) |
| INA219 | $5 | Already in the unit |
| **Total** | **~$50–75** | |

- About three weeks with no sun from a 40 Wh pack at ~2 Wh a day; a 10 W panel refills that in a day of sun.
- `battery_v` on the dashboard reads ~3.3–4.1 V (Li-ion) or ~3.0–3.5 V (LiFePO4) instead of ~13 V. The code
  has no voltage thresholds, so nothing else changes.
- On a 3.x V pack the boost draws up to ~3.5 A when the Pi is busiest. With the stock 0.1 Ω shunt the INA219
  reads at most 3.2 A, so peaks read low (the voltage is unaffected). To log the full current, fit a 0.05 Ω
  shunt and set `ina219_shunt_ohms = 0.05`.
- The Pi 5 should need only 1–2 A here (nothing on its USB ports), so a 3 A boost is enough;
  `PSU_MAX_CURRENT=5000` can stay.
- Keep the box shaded: 18650 cells should not sit above ~60 °C.

### Option B: battery swap, no solar (backup)

The Option A pack, boost, fuse and INA219 with the panel and charger board left out. The pack is sized for one
liner period (`SENTINEL_LINER_MAX_DAYS=28`): 28 days × ~2 Wh plus margin is ~65 Wh, so **6 × 18650 in parallel**.
Charge packs indoors with a 1S charger and swap one at every liner change. About **$30–40 per trap**, plus a
spare pack to rotate.

- A swap between two scheduled wakes looks like a power-button press. The server checks the photo before
  starting a new liner ([bring-up.md](bring-up.md), "Field mode"), so swap the battery and the liner together.
- **No off-the-shelf USB power bank.** Most turn themselves off once the Pi powers down and draws almost
  nothing, and then don't turn back on when the RTC alarm fires. The trap goes dead without any warning.
- Going from six photos a day to two (22:00 and 07:00) would stretch a pack by about a third.

### Off-the-shelf 12 V build

```
 20 W panel ──► ┌──────────────────────┐ ◄── LiFePO4 12.8 V 6 Ah
                │ Solar charge ctrl     │
                │ (LiFePO4 profile)     │
                └────── LOAD out ───────┘
                          │
                     3 A inline fuse
                          │
                 INA219 ── 12 → 5 V 5 A step-down ── Pi 5
```

About $200–280 per trap. The parts left on all day decide the battery life: a Genasun GV-5-Li (14.2 V
version, ~0.13 mA idle, $90–190) rather than a Victron SmartSolar 75/10 (~10 mA, $60–75) or a cheap PWM
controller, and a step-down that idles under ~1–2 mA. With typical parts the idle draw is 6–9 Wh a day, about
90% of the total. Buy a battery whose management board stops charging below 0 °C.

## Pi header

| Part | Pi 5 header pin | Notes |
|---|---|---|
| SHT45 VIN / GND | 1 (3V3) / 6 (GND) | STEMMA QT cable to a breakout; address 0x44 |
| SHT45 SDA / SCL | 3 (GPIO2) / 5 (GPIO3) | Shares the bus with the INA219 |
| INA219 VCC / GND / SDA / SCL | 17 (3V3) / 9 / 3 / 5 | Address 0x40; shunt 0.1 Ω (`ina219_shunt_ohms`) |
| LED MOSFET signal | 11 (GPIO17) | Logic-level MOSFET, low-side switch; common ground with the LED supply |
| LED supply | 5 V from the boost or step-down (or a 12 V strip from the controller load in the 12 V build) | Never power LEDs from the 3V3 pin |
| Camera | CAM/DISP 1 connector | Pi 5 uses the 22-pin *mini* connector: standard-to-mini cable. The Pi does not detect this board by itself: `camera_auto_detect=0` and `dtoverlay=imx219` in `/boot/firmware/config.txt` ([hardware/CAMERAS.md](../hardware/CAMERAS.md)) |
| RTC battery | J5 "BAT" | Keeps the clock through power loss; the wake alarm needs the RTC |

## Pi 5 EEPROM settings for the field

`sudo rpi-eeprom-config --edit` and add:

```
POWER_OFF_ON_HALT=1   # ~0.01 W when off, instead of ~1 W
WAKE_ON_GPIO=0        # needed so the RTC alarm is the wake source
PSU_MAX_CURRENT=5000  # stops the low-power warning; fine with a 3 A boost when nothing is on the USB ports
```

## Checks before closing the box

1. `i2cdetect -y 1` shows `40` (INA219) and `44` (SHT45).
2. `rpicam-still -o test.jpg` takes a photo. "No cameras available" means the `imx219` overlay above is missing.
3. Bench cycle (see bring-up.md) uploads a photo and the dashboard shows battery voltage.
4. RTC wake: `echo +120 | sudo tee /sys/class/rtc/rtc0/wakealarm && sudo halt`. The Pi should power back on about two minutes later.
