# nec.py Encoder for IR remote control using synchronous code
# NEC protocol.

# Author: Peter Hinch
# Copyright Peter Hinch 2020-2022 Released under the MIT license

# With thanks to J.E. Tannenbaum for information re Samsung protocol
from micropython import const
from . import IR, STOP

_TBURST = const(563)
_T_ONE = const(1687)

class NEC(IR):
    valid = (0xffff, 0xff, 0)  # Max addr, data, toggle
    samsung = False

    def __init__(self, pin, freq=38000, verbose=False):  # NEC specifies 38KHz also Samsung
        super().__init__(pin, freq, 68, 33, verbose)  # Measured duty ratio 33%

    def _bit(self, b):
        self.append(_TBURST, _T_ONE if b else _TBURST)

    def tx(self, addr, data, _):  # Ignore toggle
        if self.samsung:
            self.append(4500, 4500)
        else:
            self.append(9000, 4500)
        if addr < 256:  # Short address: append complement
            if self.samsung:
              addr |= addr << 8
            else:
              addr |= ((addr ^ 0xff) << 8)
        for _ in range(16):
            self._bit(addr & 1)
            addr >>= 1
        data |= ((data ^ 0xff) << 8)
        for _ in range(16):
            self._bit(data & 1)
            data >>= 1
        self.append(_TBURST)

    def repeat(self):
        self.aptr = 0
        self.append(9000, 2250, _TBURST)
        self.trigger()  # Initiate physical transmission.
