# sony.py Decoder for IR remote control using synchronous code
# Sony SIRC protocol.

# Author: Peter Hinch
# Copyright Peter Hinch 2020 Released under the MIT license

from utime import ticks_us, ticks_diff
from ir_rx import IR_RX

class SONY_ABC(IR_RX):  # Abstract base class
    def __init__(self, pin, bits, callback, *args):
        # 20 bit block has 42 edges and lasts <= 39ms nominal. Add 4ms to time
        # for tolerances except in 20 bit case where timing is tight with a
        # repeat period of 45ms.
        t = int(3 + bits * 1.8) + (1 if bits == 20 else 4)
        super().__init__(pin, 2 + bits * 2, t, callback, *args)
        self._addr = 0
        self._bits = 20

    def decode(self, _):
        try:
            nedges = self.edge  # No. of edges detected
            self.verbose and print('nedges', nedges)
            if nedges > 42:
                raise RuntimeError(self.OVERRUN)
            bits = (nedges - 2) // 2
            if nedges not in (26, 32, 42) or bits > self._bits:
                raise RuntimeError(self.BADBLOCK)
            self.verbose and print('SIRC {}bit'.format(bits))
            width = ticks_diff(self._times[1], self._times[0])
            if not 1800 < width < 3000:  # 2.4ms leading mark for all valid data
                raise RuntimeError(self.BADSTART)
            width = ticks_diff(self._times[2], self._times[1])
            if not 350 < width < 1000:  # 600μs space
                raise RuntimeError(self.BADSTART)

            val = 0  # Data received, LSB 1st
            x = 2
            bit = 1
            while x <= nedges - 2:
                if ticks_diff(self._times[x + 1], self._times[x]) > 900:
                    val |= bit
                bit <<= 1
                x += 2
            cmd = val & 0x7f  # 7 bit command
            val >>= 7
            if nedges < 42:
                addr = val & 0xff  # 5 or 8 bit addr
                val = 0
            else:
                addr = val & 0x1f  # 5 bit addr
                val >>= 5  # 8 bit extended
        except RuntimeError as e:
            cmd = e.args[0]
            addr = 0
            val = 0
        self.do_callback(cmd, addr, val)

class SONY_12(SONY_ABC):
    def __init__(self, pin, callback, *args):
        super().__init__(pin, 12, callback, *args)

class SONY_15(SONY_ABC):
    def __init__(self, pin, callback, *args):
        super().__init__(pin, 15, callback, *args)

class SONY_20(SONY_ABC):
    def __init__(self, pin, callback, *args):
        super().__init__(pin, 20, callback, *args)

