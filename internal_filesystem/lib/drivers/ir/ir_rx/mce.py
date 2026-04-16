# mce.py Decoder for IR remote control using synchronous code
# Supports Microsoft MCE edition remote protocol.

# Author: Peter Hinch
# Copyright Peter Hinch 2020 Released under the MIT license

# WARNING: This is experimental and subject to change.

from utime import ticks_us, ticks_diff
from ir_rx import IR_RX

class MCE(IR_RX):
    init_cs = 4  # http://www.hifi-remote.com/johnsfine/DecodeIR.html#OrtekMCE says 3
    def __init__(self, pin, callback, *args):
        # Block lasts ~19ms and has <= 34 edges
        super().__init__(pin, 34, 25, callback, *args)

    def decode(self, _):
        def check(v):
            if self.init_cs == -1:
                return True
            csum = v >> 12
            cs = self.init_cs
            for _ in range(12):
                if v & 1:
                    cs += 1
                v >>= 1
            return cs == csum

        try:
            t0 = ticks_diff(self._times[1], self._times[0])  # 2000μs mark
            t1 = ticks_diff(self._times[2], self._times[1])  # 1000μs space
            if not ((1800 < t0 < 2200) and (800 < t1 < 1200)):
                raise RuntimeError(self.BADSTART)
            nedges = self.edge  # No. of edges detected
            if not 14 <= nedges <= 34:
                raise RuntimeError(self.OVERRUN if nedges > 28 else self.BADSTART)
            # Manchester decode
            mask = 1
            bit = 1
            v = 0
            x = 2
            for _ in range(16):
                # -1 convert count to index, -1 because we look ahead
                if x > nedges - 2:
                    raise RuntimeError(self.BADBLOCK)
                # width is 500/1000 nominal
                width = ticks_diff(self._times[x + 1], self._times[x])
                if not 250 < width < 1350:
                    self.verbose and print('Bad block 3 Width', width, 'x', x)
                    raise RuntimeError(self.BADBLOCK)
                short = int(width < 750)
                bit ^= short ^ 1
                v |= mask if bit else 0
                mask <<= 1
                x += 1 + short

            self.verbose and print(bin(v))
            if not check(v):
                raise RuntimeError(self.BADDATA)
            val = (v >> 6) & 0x3f
            addr = v & 0xf  # Constant for all buttons on my remote
            ctrl = (v >> 4) & 3

        except RuntimeError as e:
            val, addr, ctrl = e.args[0], 0, 0
        # Set up for new data burst and run user callback/error function
        self.do_callback(val, addr, ctrl)
