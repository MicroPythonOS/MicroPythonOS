# Copyright (c) 2024 - 2025 Kevin G. Schlosser

import time
from micropython import const  # NOQA

import lvgl as lv  # NOQA
import lcd_bus  # NOQA


_SWRESET = const(0x01)
_SLPOUT = const(0x11)
_DISPON = const(0x29)
_COLMOD = const(0x3A)
_MADCTL = const(0x36)
_TEON = const(0x35)
_TEARLINE = const(0x44)
_SETOSC = const(0xB0)
_SETPWR1 = const(0xB1)
_SETRGB = const(0xB3)
_SETCOM = const(0xB6)
_SETCYC = const(0xB4)
_SETC = const(0xB9)
_SETSTBA = const(0xC0)
_SETPANEL = const(0xCC)
_SETGAMMA = const(0xE0)


def init(self):
    param_buf = bytearray(34)
    param_mv = memoryview(param_buf)

    time.sleep_ms(300)  # NOQA
    param_buf[:3] = bytearray([0xFF, 0x83, 0x57])
    self.set_params(_SETC, param_mv[:3])

    param_buf[0] = 0x80
    self.set_params(_SETRGB, param_mv[:1])

    param_buf[:4] = bytearray([0x00, 0x06, 0x06, 0x25])
    self.set_params(_SETCOM, param_mv[:4])

    param_buf[0] = 0x68
    self.set_params(_SETOSC, param_mv[:1])

    param_buf[0] = 0x05
    self.set_params(_SETPANEL, param_mv[:1])

    param_buf[:6] = bytearray([0x00, 0x15, 0x1C, 0x1C, 0x83, 0xAA])
    self.set_params(_SETPWR1, param_mv[:6])

    param_buf[:6] = bytearray([0x50, 0x50, 0x01, 0x3C, 0x1E, 0x08])
    self.set_params(_SETSTBA, param_mv[:6])

    param_buf[:7] = bytearray([0x02, 0x40, 0x00, 0x2A, 0x2A, 0x0D, 0x78])
    self.set_params(_SETCYC, param_mv[:7])

    param_buf[:34] = bytearray([
        0x02, 0x0A, 0x11, 0x1d, 0x23, 0x35, 0x41, 0x4b, 0x4b, 0x42, 0x3A,
        0x27, 0x1B, 0x08, 0x09, 0x03, 0x02, 0x0A, 0x11, 0x1d, 0x23, 0x35,
        0x41, 0x4b, 0x4b, 0x42, 0x3A, 0x27, 0x1B, 0x08, 0x09, 0x03, 0x00, 0x01])
    self.set_params(_SETGAMMA, param_mv[:34])

    param_buf[0] = (
        self._madctl(
            self._color_byte_order,
            self._ORIENTATION_TABLE  # NOQA
        )
    )
    self.set_params(_MADCTL, param_mv[:1])

    color_size = lv.color_format_get_size(self._color_space)
    if color_size == 2:  # NOQA
        pixel_format = 0x55
    else:
        raise RuntimeError(
            f'{self.__class__.__name__} IC only supports '
            'lv.COLOR_FORMAT.RGB565'
        )

    param_buf[0] = pixel_format
    self.set_params(_COLMOD, param_mv[:1])

    param_buf[0] = 0x00
    self.set_params(_TEON, param_mv[:1])

    param_buf[:2] = bytearray([0x00, 0x02])
    self.set_params(_TEARLINE, param_mv[:2])

    time.sleep_ms(150)  # NOQA
    self.set_params(_SLPOUT)

    time.sleep_ms(50)  # NOQA
    self.set_params(_DISPON)
