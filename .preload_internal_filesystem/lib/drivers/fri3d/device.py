import struct

from micropython import const
from machine import I2C

# common registers
_REG_VERSION = const(0x00)


class Device:
    """Fri3d I2C device."""

    def __init__(self, i2c_bus: I2C, address: int):
        """Read from a sensor on the given I2C bus, at the given address."""
        self.i2c = i2c_bus
        self.address = address

    def _read(self, format, reg, amount):
        return struct.unpack(format, self.i2c.readfrom_mem(self.address, reg, amount))

    def _write(self, reg, value):
        self.i2c.writeto_mem(self.address, reg, value, addrsize=8)

    @property
    def version(self) -> tuple[int, int, int]:
        return self._read("BBB", _REG_VERSION, 3)
