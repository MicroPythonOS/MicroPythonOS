# tcl.py Encoder for TCL smart TV IR remote control
# TCL uses a 24-bit NEC-style pulse-distance protocol with a non-standard header:
#   Header:  ~4ms mark + ~4ms space  (NEC uses 9ms/4.5ms)
#   Bit '0': ~500us mark + ~500us space
#   Bit '1': ~500us mark + ~1950us space
#   Frame:   addr_lo(8) + addr_hi(8) + cmd(8)  -- LSB first, no complement bytes
#
# Author: derived from Peter Hinch's NEC encoder

from micropython import const
from . import IR

_TBURST = const(500)
_T_ONE = const(1950)
_T_HDR_MARK = const(4000)
_T_HDR_SPACE = const(4000)


class TCL(IR):
    valid = (0xFFFF, 0xFF, 0)  # Max addr (16-bit), data (8-bit), toggle unused

    def __init__(self, pin, freq=38000, verbose=False):
        # 24-bit frame: 2 (header) + 24*2 (bits) + 1 (stop) + 1 (spare) = 52
        super().__init__(pin, freq, 52, 33, verbose)

    def _bit(self, b):
        self.append(_TBURST, _T_ONE if b else _TBURST)

    def tx(self, addr, data, _):  # toggle unused
        self.append(_T_HDR_MARK, _T_HDR_SPACE)
        for _ in range(16):  # 16-bit address, LSB first
            self._bit(addr & 1)
            addr >>= 1
        for _ in range(8):  # 8-bit command, LSB first
            self._bit(data & 1)
            data >>= 1
        self.append(_TBURST)  # stop mark
