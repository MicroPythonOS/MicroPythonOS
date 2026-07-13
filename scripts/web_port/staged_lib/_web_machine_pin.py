# Fake machine.Pin for the WebAssembly/Emscripten build.
#
# The browser has no GPIO, but drivers like mpos.lights do
# `from machine import Pin` and pass Pin objects to the (emulated)
# neopixel module. This stub stores the pin state in memory and
# no-ops all hardware interaction.


class Pin:
    IN = 0
    OUT = 1
    OPEN_DRAIN = 2
    PULL_UP = 3
    PULL_DOWN = 4
    IRQ_RISING = 1
    IRQ_FALLING = 2

    def __init__(self, id, mode=-1, pull=-1, value=None, **kwargs):
        self._id = id
        self._mode = mode
        self._pull = pull
        self._value = 1 if pull == Pin.PULL_UP else 0
        if value is not None:
            self._value = 1 if value else 0

    def init(self, mode=-1, pull=-1, value=None, **kwargs):
        if mode != -1:
            self._mode = mode
        if pull != -1:
            self._pull = pull
        if value is not None:
            self._value = 1 if value else 0

    def value(self, x=None):
        if x is None:
            return self._value
        self._value = 1 if x else 0

    def on(self):
        self._value = 1

    def off(self):
        self._value = 0

    def irq(self, handler=None, trigger=IRQ_RISING | IRQ_FALLING, **kwargs):
        return None

    def __repr__(self):
        return "Pin({})".format(self._id)
