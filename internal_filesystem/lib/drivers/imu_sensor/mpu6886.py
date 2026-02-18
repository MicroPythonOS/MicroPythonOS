"""
MicroPython driver for MPU6886 3-Axis Accelerometer + 3-Axis Gyroscope.
Tested with M5Stack FIRE
https://docs.m5stack.com/en/unit/imu
https://github.com/m5stack/M5Stack/blob/master/src/utility/MPU6886.h
"""

import time

from machine import I2C
from micropython import const

_I2CADDR_DEFAULT = const(0x68)


# register addresses
_REG_PWR_MGMT_1 = const(0x6B)
_REG_ACCEL_XOUT_H = const(0x3B)
_REG_GYRO_XOUT_H = const(0x43)
_REG_ACCEL_CONFIG = const(0x1C)
_REG_GYRO_CONFIG = const(0x1B)
_REG_TEMPERATURE_OUT_H = const(0x41)

# Scale factors for converting raw sensor data to physical units:
_ACCEL_SCALE_8G = 8.0 / 32768.0  # LSB/g for +-8g range
_GYRO_SCALE_2000DPS = 2000.0 / 32768.0  # LSB/°/s for +-2000dps range
_TEMPERATURE_SCALE = 326.8  # LSB/°C
_TEMPERATURE_OFFSET = const(25)  # Offset (25°C at 0 LSB)


def twos_complement(val, bits):
    if val & (1 << (bits - 1)):
        val -= 1 << bits
    return val


class MPU6886:
    def __init__(
        self,
        i2c_bus: I2C,
        address: int = _I2CADDR_DEFAULT,
    ):
        self.i2c = i2c_bus
        self.address = address

        for data in (b"\x00", b"\x80", b"\x01"):  # Reset, then wake up
            self._write(_REG_PWR_MGMT_1, data)
            time.sleep(0.01)

        self._write(_REG_ACCEL_CONFIG, b"\x10")  # +-8g
        time.sleep(0.001)

        self._write(_REG_GYRO_CONFIG, b"\x18")  # +-2000dps
        time.sleep(0.001)

    # Helper functions for register operations
    def _write(self, reg: int, data: bytes):
        self.i2c.writeto_mem(self.address, reg, data)

    def _read_xyz(self, reg: int, scale: float) -> tuple[int, int, int]:
        data = self.i2c.readfrom_mem(self.address, reg, 6)
        x = twos_complement(data[0] << 8 | data[1], 16)
        y = twos_complement(data[2] << 8 | data[3], 16)
        z = twos_complement(data[4] << 8 | data[5], 16)
        return (x * scale, y * scale, z * scale)

    @property
    def temperature(self) -> float:
        buf = self.i2c.readfrom_mem(self.address, _REG_TEMPERATURE_OUT_H, 14)
        temp_raw = (buf[6] << 8) | buf[7]
        if temp_raw & 0x8000:  # If MSB is 1, it's negative
            temp_raw -= 0x10000  # Subtract 2^16 to get negative value
        return temp_raw / _TEMPERATURE_SCALE + _TEMPERATURE_OFFSET

    @property
    def acceleration(self) -> tuple[int, int, int]:
        """Get current acceleration reading."""
        return self._read_xyz(_REG_ACCEL_XOUT_H, scale=_ACCEL_SCALE_8G)

    @property
    def gyro(self) -> tuple[int, int, int]:
        """Get current gyroscope reading."""
        return self._read_xyz(_REG_GYRO_XOUT_H, scale=_GYRO_SCALE_2000DPS)
