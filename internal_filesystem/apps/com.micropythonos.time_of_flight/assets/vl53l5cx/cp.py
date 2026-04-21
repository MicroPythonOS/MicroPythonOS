# Copyright (c) 2021 Mark Grosen <mark@grosen.org>
#
# SPDX-License-Identifier: MIT

from time import sleep

from adafruit_bus_device.i2c_device import I2CDevice

from . import VL53L5CX


class VL53L5CXCP(VL53L5CX):
    def __init__(self, i2c, addr=0x29, lpn=None):
        super().__init__(i2c, addr=addr, lpn=lpn)
        self.dev = I2CDevice(i2c, addr)
        self._buf = bytearray(3)

    def _rd_byte(self, reg16):
        self._buf[0] = reg16 >> 8
        self._buf[1] = reg16 & 0xFF
        with self.dev:
            self.dev.write_then_readinto(self._buf, self._b1,
                                         out_start=0, out_end=2)

        return self._b1[0]

    def _rd_multi(self, reg16, size):
        self._buf[0] = reg16 >> 8
        self._buf[1] = reg16 & 0xFF
        data = bytearray(size)
        with self.dev:
            self.dev.write_then_readinto(self._buf, data,
                                         out_start=0, out_end=2)

        return data

    def _wr_byte(self, reg16, val):
        self._buf[0] = reg16 >> 8
        self._buf[1] = reg16 & 0xFF
        self._buf[2] = val
        with self.dev:
            self.dev.write(self._buf)

    def _wr_multi(self, reg16, data):
        buf = bytearray(2 + len(data))
        buf[0] = reg16 >> 8
        buf[1] = reg16 & 0xFF
        buf[2:] = data
        with self.dev:
            self.dev.write(buf)

    def reset(self):
        if not self._lpn:
            raise ValueError("no LPN pin provided")

        self._lpn.value = False
        sleep(0.1)
        self._lpn.value = True
        sleep(0.1)
