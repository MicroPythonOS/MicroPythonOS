# philips.py Encoder for IR remote control using synchronous code
# RC-5 and RC-6 mode 0 protocols.

# Author: Peter Hinch
# Copyright Peter Hinch 2020 Released under the MIT license

from micropython import const
from ir_tx import IR

# Philips RC5 protocol
_T_RC5 = const(889)  # Time for pulse of carrier


class RC5(IR):
    valid = (0x1f, 0x7f, 1)  # Max addr, data, toggle

    def __init__(self, pin, freq=36000, verbose=False):
        super().__init__(pin, freq, 28, 30, verbose)

    def tx(self, addr, data, toggle):  # Fix RC5X S2 bit polarity
        d = (data & 0x3f) | ((addr & 0x1f) << 6) | (((data & 0x40) ^ 0x40) << 6) | ((toggle & 1) << 11)
        self.verbose and print(bin(d))
        mask = 0x2000
        while mask:
            if mask == 0x2000:
                self.append(_T_RC5)
            else:
                bit = bool(d & mask)
                if bit ^ self.carrier:
                    self.add(_T_RC5)
                    self.append(_T_RC5)
                else:
                    self.append(_T_RC5, _T_RC5)
            mask >>= 1

# Philips RC6 mode 0 protocol
_T_RC6 = const(444)
_T2_RC6 = const(889)

class RC6_M0(IR):
    valid = (0xff, 0xff, 1)  # Max addr, data, toggle

    def __init__(self, pin, freq=36000, verbose=False):
        super().__init__(pin, freq, 44, 30, verbose)

    def tx(self, addr, data, toggle):
        # leader, 1, 0, 0, 0
        self.append(2666, _T2_RC6, _T_RC6, _T2_RC6, _T_RC6, _T_RC6, _T_RC6, _T_RC6, _T_RC6)
        # Append a single bit of twice duration
        if toggle:
            self.add(_T2_RC6)
            self.append(_T2_RC6)
        else:
            self.append(_T2_RC6, _T2_RC6)
        d = (data & 0xff) | ((addr & 0xff) << 8)
        mask = 0x8000
        self.verbose and print('toggle', toggle, self.carrier, bool(d & mask))
        while mask:
            bit = bool(d & mask)
            if bit ^ self.carrier:
                self.append(_T_RC6, _T_RC6)
            else:
                self.add(_T_RC6)
                self.append(_T_RC6)
            mask >>= 1
