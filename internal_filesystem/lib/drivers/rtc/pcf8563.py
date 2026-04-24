from machine import I2C
from micropython import const

I2C_ADDR = const(0x51)
REG_CTRL1 = const(0x00)  # not used much here
REG_CTRL2 = const(0x01)
REG_SEC   = const(0x02)
REG_MIN   = const(0x03)
REG_HR    = const(0x04)
REG_DAY   = const(0x05)
REG_WDAY  = const(0x06)
REG_MON   = const(0x07)
REG_YR    = const(0x08)

class PCF8563:
    def __init__(self, i2c):
        self.i2c = i2c
        self.i2c.writeto(I2C_ADDR, b'\x01\x00')  # clear some flags if needed

    def _bcd2dec(self, bcd):
        return ((bcd >> 4) * 10) + (bcd & 0x0F)

    def _dec2bcd(self, dec):
        return ((dec // 10) << 4) + (dec % 10)

    def datetime(self, dt=None):
        """Get or set datetime as tuple: (year, month, day, weekday, hour, minute, second)
           Year is full (e.g. 2026), weekday 0-6 (0=Sunday usually, but PCF8563 is flexible)"""
        if dt is None:
            # Read 7 bytes starting from seconds register
            self.i2c.writeto(I2C_ADDR, b'\x02')
            data = self.i2c.readfrom(I2C_ADDR, 7)
            sec = self._bcd2dec(data[0] & 0x7F)
            mins = self._bcd2dec(data[1] & 0x7F)
            hr = self._bcd2dec(data[2] & 0x3F)
            day = self._bcd2dec(data[3] & 0x3F)
            wday = self._bcd2dec(data[4] & 0x07)
            mon = self._bcd2dec(data[5] & 0x1F)
            yr = self._bcd2dec(data[6]) + 2000
            return (yr, mon, day, wday, hr, mins, sec)
        else:
            # Set time (stop clock briefly for clean write)
            self.i2c.writeto(I2C_ADDR, b'\x00\x80')  # stop clock (bit 7 of ctrl1)
            buf = bytearray([
                0x02,
                self._dec2bcd(dt[6] % 60),           # sec
                self._dec2bcd(dt[5] % 60),           # min
                self._dec2bcd(dt[4] % 24),           # hour
                self._dec2bcd(dt[2] % 32),           # day
                self._dec2bcd(dt[3] % 8),            # weekday
                self._dec2bcd(dt[1] % 13),           # month
                self._dec2bcd(dt[0] % 100)           # year (00-99 -> 2000+)
            ])
            self.i2c.writeto(I2C_ADDR, buf)
            self.i2c.writeto(I2C_ADDR, b'\x00\x00')  # start clock again

    def unix_time(self):
        """Return seconds since Unix epoch (1970-01-01). Note: MicroPython's time.mktime uses 2000-01-01 epoch on many ports."""
        import time
        dt = self.datetime()
        # time.mktime expects (year, month, mday, hour, minute, second, weekday, yearday)
        # yearday can be 0 or computed
        try:
            return time.mktime((dt[0], dt[1], dt[2], dt[4], dt[5], dt[6], dt[3], 0))
        except:
            # Fallback if mktime not available or epoch issue
            print("time.mktime not supported or epoch mismatch")
            return None

    def set_unix_time(self, unix_ts):
        """Set RTC from Unix timestamp (seconds since 1970)."""
        import time
        try:
            dt = time.localtime(unix_ts)  # (year, month, mday, hour, min, sec, wday, yday)
            # localtime returns wday with Monday=0; PCF8563 doesn't care much, but we pass it
            self.datetime((dt[0], dt[1], dt[2], dt[6], dt[3], dt[4], dt[5]))
        except:
            print("time.localtime not supported on this port")
