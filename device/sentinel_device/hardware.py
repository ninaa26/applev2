"""LED switch and I2C sensors. Every function degrades to a no-op/None off the Pi."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)


@contextmanager
def led(enabled: bool, gpio: int):
    """Turn the liner LEDs on for the duration of the block."""
    device = None
    if enabled:
        try:
            from gpiozero import OutputDevice  # type: ignore

            device = OutputDevice(gpio, active_high=True, initial_value=False)
            device.on()
        except Exception as e:  # not on a Pi, or GPIO busy
            log.warning("LED control unavailable: %s", e)
            device = None
    try:
        yield
    finally:
        if device is not None:
            device.off()
            device.close()


def _crc8_sht(data: bytes) -> int:
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x31) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def sht4x_decode(raw: bytes) -> tuple[float, float]:
    """Decode a 6-byte SHT4x high-precision reading into (°C, %RH). Raises on CRC failure."""
    if len(raw) != 6 or _crc8_sht(raw[0:2]) != raw[2] or _crc8_sht(raw[3:5]) != raw[5]:
        raise ValueError("SHT4x CRC mismatch")
    t_ticks = raw[0] << 8 | raw[1]
    rh_ticks = raw[3] << 8 | raw[4]
    temp_c = -45 + 175 * t_ticks / 65535
    rh = min(100.0, max(0.0, -6 + 125 * rh_ticks / 65535))
    return round(temp_c, 2), round(rh, 1)


def read_sht4x(bus_no: int = 1, address: int = 0x44) -> dict | None:
    try:
        from smbus2 import SMBus, i2c_msg

        with SMBus(bus_no) as bus:
            bus.i2c_rdwr(i2c_msg.write(address, [0xFD]))  # measure, high precision
            time.sleep(0.01)
            msg = i2c_msg.read(address, 6)
            bus.i2c_rdwr(msg)
            temp_c, rh = sht4x_decode(bytes(list(msg)))
        return {"temp_c": temp_c, "rh": rh}
    except Exception as e:
        log.warning("SHT4x read failed: %s", e)
        return None


def read_ina219(shunt_ohms: float, bus_no: int = 1, address: int = 0x40) -> dict | None:
    """Battery-side bus voltage and current from an INA219 (no calibration register needed)."""
    try:
        from smbus2 import SMBus

        with SMBus(bus_no) as bus:
            def reg(r: int) -> int:
                hi, lo = bus.read_i2c_block_data(address, r, 2)
                return hi << 8 | lo

            bus_v = (reg(0x02) >> 3) * 0.004
            shunt = reg(0x01)
            if shunt & 0x8000:
                shunt -= 1 << 16
            current_ma = shunt * 0.01 / shunt_ohms  # 10 µV per LSB -> mV / Ω = mA
        return {"battery_v": round(bus_v, 3), "current_ma": round(current_ma, 1)}
    except Exception as e:
        log.warning("INA219 read failed: %s", e)
        return None


def cpu_temp_c() -> float | None:
    p = Path("/sys/class/thermal/thermal_zone0/temp")
    try:
        return round(int(p.read_text()) / 1000, 1)
    except Exception:
        return None


def uptime_s() -> float | None:
    try:
        return float(Path("/proc/uptime").read_text().split()[0])
    except Exception:
        return None


RTC_WAKEALARM = Path("/sys/class/rtc/rtc0/wakealarm")


def set_rtc_wake(epoch_s: int) -> bool:
    """Program the Pi 5 RTC to power the board back on at epoch_s (UTC seconds)."""
    try:
        RTC_WAKEALARM.write_text("0")  # clear any pending alarm first
        RTC_WAKEALARM.write_text(str(int(epoch_s)))
        return True
    except Exception as e:
        log.error("could not set RTC wake alarm: %s", e)
        return False
