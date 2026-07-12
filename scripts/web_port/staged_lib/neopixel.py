# Web (Emscripten) `neopixel` shim for MicroPythonOS.
#
# The browser build has no NeoPixel hardware, but mpos.lights (LightsManager)
# does `from neopixel import NeoPixel` and drives RGB LEDs with item
# assignment + write(). This drop-in forwards the packed RGB buffer to the
# page via the `_webio` native bridge, where shell.html paints LED dots
# (Module.__webio.onLeds). Same __getitem__/__setitem__/write()/fill()
# surface as the MicroPython neopixel module; the pin argument is accepted
# and ignored.

import _webio

_webio.init()


class NeoPixel:
    def __init__(self, pin, n, bpp=3, timing=1):
        self.pin = pin
        self.n = n
        self.bpp = bpp
        self.buf = bytearray(n * bpp)

    def __len__(self):
        return self.n

    def __setitem__(self, i, v):
        o = i * self.bpp
        for j in range(self.bpp):
            self.buf[o + j] = v[j] & 0xFF

    def __getitem__(self, i):
        o = i * self.bpp
        return tuple(self.buf[o + j] for j in range(self.bpp))

    def fill(self, v):
        for i in range(self.n):
            self[i] = v

    def write(self):
        _webio.leds_write(bytes(self.buf))
