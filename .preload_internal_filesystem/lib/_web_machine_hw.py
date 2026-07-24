# Fake machine peripherals for the WebAssembly/Emscripten build.
#
# The browser has no GPIO/buses, but apps and board drivers do
# `from machine import PWM, ADC, I2C, SPI, UART, RTC, ...`. These stubs
# store state in memory and no-op all hardware interaction so such code
# can at least import and run without crashing.

import time


def unique_id():
    return b"webbuild"


def freq(hz=None):
    if hz is None:
        return 240_000_000


def reset():
    raise SystemExit("machine.reset() on web build")


def soft_reset():
    raise SystemExit("machine.soft_reset() on web build")


def reset_cause():
    return 0


def wake_reason():
    return 0


def deepsleep(time_ms=None):
    raise SystemExit("machine.deepsleep() on web build")


def lightsleep(time_ms=None):
    if time_ms:
        time.sleep_ms(time_ms)


def idle():
    pass


class PWM:
    def __init__(self, pin, freq=5000, duty_u16=0, **kwargs):
        self._pin = pin
        self._freq = freq
        self._duty = duty_u16

    def freq(self, value=None):
        if value is None:
            return self._freq
        self._freq = value

    def duty(self, value=None):
        if value is None:
            return self._duty >> 6
        self._duty = value << 6

    def duty_u16(self, value=None):
        if value is None:
            return self._duty
        self._duty = value

    def duty_ns(self, value=None):
        if value is None:
            return 0

    def deinit(self):
        pass


class ADC:
    ATTN_0DB = 0
    ATTN_2_5DB = 1
    ATTN_6DB = 2
    ATTN_11DB = 3
    WIDTH_9BIT = 9
    WIDTH_10BIT = 10
    WIDTH_11BIT = 11
    WIDTH_12BIT = 12

    def __init__(self, pin, **kwargs):
        self._pin = pin

    def atten(self, value):
        pass

    def width(self, value):
        pass

    def read(self):
        return 2048

    def read_u16(self):
        return 32768

    def read_uv(self):
        return 1650000


class _Bus:
    def __init__(self, *args, **kwargs):
        pass

    def deinit(self):
        pass


class I2C(_Bus):
    def scan(self):
        return []

    def readfrom(self, addr, nbytes, stop=True):
        raise OSError("no I2C on web build")

    def readfrom_into(self, addr, buf, stop=True):
        raise OSError("no I2C on web build")

    def writeto(self, addr, buf, stop=True):
        raise OSError("no I2C on web build")

    def readfrom_mem(self, addr, memaddr, nbytes, addrsize=8):
        raise OSError("no I2C on web build")

    def readfrom_mem_into(self, addr, memaddr, buf, addrsize=8):
        raise OSError("no I2C on web build")

    def writeto_mem(self, addr, memaddr, buf, addrsize=8):
        raise OSError("no I2C on web build")


class SoftI2C(I2C):
    pass


class SPI(_Bus):
    MSB = 0
    LSB = 1

    def init(self, *args, **kwargs):
        pass

    def read(self, nbytes, write=0x00):
        return bytes(nbytes)

    def readinto(self, buf, write=0x00):
        pass

    def write(self, buf):
        pass

    def write_readinto(self, write_buf, read_buf):
        pass


class SoftSPI(SPI):
    pass


class UART:
    def __init__(self, id, baudrate=9600, **kwargs):
        self._id = id
        self._baudrate = baudrate

    def init(self, baudrate=9600, **kwargs):
        self._baudrate = baudrate

    def deinit(self):
        pass

    def any(self):
        return 0

    def read(self, nbytes=None):
        return None

    def readinto(self, buf, nbytes=None):
        return None

    def readline(self):
        return None

    def write(self, buf):
        return len(buf)

    def sendbreak(self):
        pass

    def flush(self):
        pass

    def txdone(self):
        return True


class RTC:
    def __init__(self, id=0):
        pass

    def datetime(self, datetimetuple=None):
        if datetimetuple is None:
            t = time.localtime()
            # (year, month, day, weekday, hours, minutes, seconds, subseconds)
            return (t[0], t[1], t[2], t[6], t[3], t[4], t[5], 0)
        # Setting the clock is not supported in the browser; ignore.

    def init(self, datetimetuple):
        pass

    def memory(self, data=None):
        if data is None:
            return b""


class WDT:
    def __init__(self, id=0, timeout=5000):
        pass

    def feed(self):
        pass


class SDCard:
    def __init__(self, *args, **kwargs):
        raise OSError("no SDCard on web build")

