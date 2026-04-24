# Copyright (c) 2021 Mark Grosen <mark@grosen.org>
#
# SPDX-License-Identifier: MIT

from time import sleep_ms

from . import VL53L5CX


class VL53L5CXMP(VL53L5CX):
    def _rd_byte(self, reg16):
        self.i2c.readfrom_mem_into(self.addr, reg16, self._b1, addrsize=16)
        return self._b1[0]

    def _rd_multi(self, reg16, size):
        return self.i2c.readfrom_mem(self.addr, reg16, size, addrsize=16)

    def _wr_byte(self, reg16, val):
        self._b1[0] = val
        self.i2c.writeto_mem(self.addr, reg16, self._b1, addrsize=16)

    def _wr_multi(self, reg16, buf):
        self.i2c.writeto_mem(self.addr, reg16, buf, addrsize=16)

    def reset(self):
        if not self._lpn:
            raise ValueError("no LPN pin provided")

        self._lpn.value(0)
        sleep_ms(100)
        self._lpn.value(1)
        sleep_ms(100)
