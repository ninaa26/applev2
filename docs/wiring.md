# Wiring: one trap unit

```
 20 W panel ──► ┌──────────────────────┐ ◄── LiFePO4 12.8 V 6 Ah
                │ Solar charge ctrl     │
                │ (LiFePO4 profile)     │
                └────── LOAD out ───────┘
                          │
                     3 A inline fuse
                          │
                 INA219 (Vin+ → Vin−)  ── I2C ──┐
                          │                      │
               12 → 5 V 5 A step-down            │
                          │ USB-C pigtail        │
                  ┌───────▼────────┐             │
                  │ Raspberry Pi 5  │◄────────────┘
                  │  CAM0 ── 500 mm ribbon ── Camera Module 3 Wide (in the apex mount)
                  │  J5 BAT ── RTC battery
                  │  GPIO17 ── MOSFET gate ── LED strip (−)
                  │  I2C ── SHT45 (in a small shield outside the box)
                  └─────────────────┘
```

| Part | Pi 5 header pin | Notes |
|---|---|---|
| SHT45 VIN / GND | 1 (3V3) / 6 (GND) | STEMMA QT cable to a breakout; address 0x44 |
| SHT45 SDA / SCL | 3 (GPIO2) / 5 (GPIO3) | Shares the bus with the INA219 |
| INA219 VCC / GND / SDA / SCL | 17 (3V3) / 9 / 3 / 5 | Address 0x40; shunt 0.1 Ω (`ina219_shunt_ohms`) |
| LED MOSFET signal | 11 (GPIO17) | Logic-level MOSFET, low-side switch; common ground with the LED supply |
| LED supply | 5 V from the step-down (or 12 V strip from the controller load) | Never power LEDs from the 3V3 pin |
| Camera | CAM/DISP 0 connector | Pi 5 uses the 22-pin *mini* connector: standard-to-mini cable |
| RTC battery | J5 "BAT" | Keeps the clock through power loss; the wake alarm needs the RTC |

## Pi 5 EEPROM settings for the field

`sudo rpi-eeprom-config --edit` and add:

```
POWER_OFF_ON_HALT=1   # ~0.01 W when off, instead of ~1 W
WAKE_ON_GPIO=0        # needed so the RTC alarm is the wake source
PSU_MAX_CURRENT=5000  # the step-down can supply 5 A; stops the low-power warning
```

## Checks before closing the box

1. `i2cdetect -y 1` shows `40` (INA219) and `44` (SHT45).
2. `rpicam-still -o test.jpg` takes a photo.
3. Bench cycle (see bring-up.md) uploads a photo and the dashboard shows battery voltage.
4. RTC wake: `echo +120 | sudo tee /sys/class/rtc/rtc0/wakealarm && sudo halt`. The Pi should power back on about two minutes later.
