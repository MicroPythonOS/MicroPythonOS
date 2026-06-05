# MAX17048/MAX17049 LiPo fuel gauge (I2C 0x36), 16-bit big-endian registers.
#
# `i2c` is any machine.I2C-style object exposing readfrom_mem/writeto_mem.
# Scaling per the MAX17048 datasheet: VCELL 78.125 uV/LSB, SOC 1/256 %/LSB,
# CRATE 0.208 %/hr/LSB (signed). CONFIG.ATHD (low 5 bits) = 32 - empty-alert %.
from micropython import const

_ADDR = const(0x36)
_VCELL = const(0x02)
_SOC = const(0x04)
_MODE = const(0x06)
_VERSION = const(0x08)
_CONFIG = const(0x0C)   # [15:8]=RCOMP, b6 ALSC, b5 ALRT, [4:0] ATHD
_VALRT = const(0x14)
_CRATE = const(0x16)
_STATUS = const(0x1A)
_CMD = const(0xFE)


class MAX17048:
    def __init__(self, i2c, addr=_ADDR):
        self._i2c = i2c
        self._addr = addr

    def _r16(self, reg):
        return int.from_bytes(self._i2c.readfrom_mem(self._addr, reg, 2), "big")

    def _w16(self, reg, val):
        self._i2c.writeto_mem(self._addr, reg, (val & 0xFFFF).to_bytes(2, "big"))

    @property
    def cell_voltage(self):           # volts
        return self._r16(_VCELL) * 78.125e-6

    @property
    def state_of_charge(self):        # percent 0..100
        return self._r16(_SOC) / 256.0

    @property
    def charge_rate(self):            # %/hr, signed (+charging)
        raw = self._r16(_CRATE)
        if raw & 0x8000:
            raw -= 0x10000
        return raw * 0.208

    @property
    def version(self):
        return self._r16(_VERSION)

    def set_empty_alert_threshold(self, percent):   # 1..32
        percent = max(1, min(32, int(percent)))
        athd = 32 - percent                          # ATHD = 32 - threshold
        cfg = self._r16(_CONFIG)
        self._w16(_CONFIG, (cfg & 0xFFE0) | (athd & 0x1F))

    def enable_soc_change_alert(self, enable=True):
        cfg = self._r16(_CONFIG)
        self._w16(_CONFIG, (cfg | 0x0040) if enable else (cfg & ~0x0040))

    def alert_active(self):                           # CONFIG.ALRT (b5)
        return bool(self._r16(_CONFIG) & 0x0020)

    def clear_alert(self):                            # de-assert FG_INT
        cfg = self._r16(_CONFIG)
        self._w16(_CONFIG, cfg & ~0x0020)

    def status(self):                                 # 0x1A alert flags
        return self._r16(_STATUS)
