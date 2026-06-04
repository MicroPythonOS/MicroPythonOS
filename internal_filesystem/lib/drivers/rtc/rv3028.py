# RV-3028-C7 low-power RTC (I2C 0x52).
#
# `i2c` is any machine.I2C-style object exposing readfrom_mem/writeto_mem.
# datetime() uses the tuple (year, month, day, weekday, hour, minute, second),
# weekday 0..6, full 4-digit year. This is the shape MicroPythonOS expects of a
# TimeZone.rtc driver (see drivers/rtc/pcf8563.py).
from micropython import const

_ADDR = const(0x52)
_SECONDS = const(0x00)   # SEC,MIN,HOUR,WEEKDAY,DATE,MONTH,YEAR (BCD, 7 bytes)
_STATUS = const(0x0E)
_CTRL1 = const(0x0F)
_CTRL2 = const(0x10)
_ALARM_MIN = const(0x07)  # ALARM_MIN, ALARM_HOUR, ALARM_WD_DATE
_UNIX0 = const(0x1B)      # 32-bit LSB-first
_EE_BACKUP = const(0x37)


def _b2d(b):
    return ((b >> 4) * 10) + (b & 0x0F)


def _d2b(d):
    return ((d // 10) << 4) + (d % 10)


class RV3028:
    def __init__(self, i2c, addr=_ADDR):
        self._i2c = i2c
        self._addr = addr

    def datetime(self, dt=None):
        if dt is None:
            d = self._i2c.readfrom_mem(self._addr, _SECONDS, 7)
            sec = _b2d(d[0] & 0x7F)
            mins = _b2d(d[1] & 0x7F)
            hr = _b2d(d[2] & 0x3F)
            wday = d[3] & 0x07
            day = _b2d(d[4] & 0x3F)
            mon = _b2d(d[5] & 0x1F)
            yr = 2000 + _b2d(d[6])
            return (yr, mon, day, wday, hr, mins, sec)
        yr, mon, day, wday, hr, mins, sec = dt
        buf = bytes((_d2b(sec), _d2b(mins), _d2b(hr), wday & 0x07,
                     _d2b(day), _d2b(mon), _d2b(yr % 100)))
        self._i2c.writeto_mem(self._addr, _SECONDS, buf)

    def unix_time(self):
        a = self._i2c.readfrom_mem(self._addr, _UNIX0, 4)
        return a[0] | (a[1] << 8) | (a[2] << 16) | (a[3] << 24)

    def set_unix_time(self, ts):
        self._i2c.writeto_mem(self._addr, _UNIX0,
                              bytes((ts & 0xFF, (ts >> 8) & 0xFF, (ts >> 16) & 0xFF, (ts >> 24) & 0xFF)))

    def _ru8(self, reg):
        return self._i2c.readfrom_mem(self._addr, reg, 1)[0]

    def _wu8(self, reg, v):
        self._i2c.writeto_mem(self._addr, reg, bytes((v & 0xFF,)))

    def set_daily_alarm(self, hour, minute):
        # clear AF (STATUS b2) and AIE (CTRL2 b3), select WADA weekday mode, compare HH and MM
        self._wu8(_STATUS, self._ru8(_STATUS) & ~(1 << 2))
        self._wu8(_CTRL2, self._ru8(_CTRL2) & ~(1 << 3))
        self._wu8(_CTRL1, self._ru8(_CTRL1) & ~(1 << 5))  # WADA=0 weekday-mode
        # AE bit7=1 means that field is ignored, so this matches HH:MM and ignores weekday
        self._i2c.writeto_mem(self._addr, _ALARM_MIN,
                              bytes((_d2b(minute), _d2b(hour), 0x80)))

    def enable_alarm_interrupt(self, enable=True):
        c2 = self._ru8(_CTRL2)
        self._wu8(_CTRL2, (c2 | (1 << 3)) if enable else (c2 & ~(1 << 3)))

    def alarm_fired(self):
        return bool(self._ru8(_STATUS) & (1 << 2))

    def clear_alarm(self):
        self._wu8(_STATUS, self._ru8(_STATUS) & ~(1 << 2))

    def enable_backup(self):
        # 0x37: BSM=Level Switching (bits3:2=11), TCE trickle enable (b5), TCR=3k (bits1:0=00)
        try:
            v = self._ru8(_EE_BACKUP)
            v = (v & ~0x0C) | 0x0C        # BSM=LSM
            v |= 0x20                      # TCE
            self._wu8(_EE_BACKUP, v)       # RAM mirror write, effective immediately, EEPROM persistence optional
        except Exception as e:
            print("rv3028: enable_backup:", e)
