# mce.py Encoder for IR remote control using synchronous code
# Supports Microsoft MCE edition remote protocol.

# Author: Peter Hinch
# Copyright Peter Hinch 2020 Released under the MIT license

# WARNING: This is experimental and subject to change.

from micropython import const
from ir_tx import IR

_TBIT = const(500)  # Time (μs) for pulse of carrier


class MCE(IR):
    valid = (0xf, 0x3f, 3)  # Max addr, data, toggle
    init_cs = 4  # http://www.hifi-remote.com/johnsfine/DecodeIR.html#OrtekMCE says 3

    def __init__(self, pin, freq=38000, verbose=False):
        super().__init__(pin, freq, 34, 30, verbose)

    def tx(self, addr, data, toggle):
        def checksum(v):
            cs = self.init_cs
            for _ in range(12):
                if v & 1:
                    cs += 1
                v >>= 1
            return cs

        self.append(2000, 1000, _TBIT)
        d = ((data & 0x3f) << 6) | (addr & 0xf)  | ((toggle & 3) << 4)
        d |= checksum(d) << 12
        self.verbose and print(bin(d))

        mask = 1
        while mask < 0x10000:
            bit = bool(d & mask)
            if bit ^ self.carrier:
                self.add(_TBIT)
                self.append(_TBIT)
            else:
                self.append(_TBIT, _TBIT)
            mask <<= 1
