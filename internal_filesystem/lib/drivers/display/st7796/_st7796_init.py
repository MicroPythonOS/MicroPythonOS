# Copyright (c) 2024 - 2025 Kevin G. Schlosser

import time
from micropython import const  # NOQA

import lvgl as lv  # NOQA

_SWRESET = const(0x01)
_SLPOUT = const(0x11)
_CSCON = const(0xF0)
_MADCTL = const(0x36)
_COLMOD = const(0x3A)
_DIC = const(0xB4)
_DFC = const(0xB6)
_DOCA = const(0xE8)
_PWR2 = const(0xC1)
_PWR3 = const(0xC2)
_VCMPCTL = const(0xC5)
_PGC = const(0xE0)
_NGC = const(0xE1)
_DISPON = const(0x29)

_EM = const(0xB7)


def init(self):
    param_buf = bytearray(14)
    param_mv = memoryview(param_buf)

    self.set_params(_SWRESET)

    time.sleep_ms(120)  # NOQA

    self.set_params(_SLPOUT)

    time.sleep_ms(120)  # NOQA

    param_buf[0] = 0xC3
    self.set_params(_CSCON, param_mv[:1])

    param_buf[0] = 0x96
    self.set_params(_CSCON, param_mv[:1])

    param_buf[0] = (
        self._madctl(
            self._color_byte_order,
            self._ORIENTATION_TABLE  # NOQA
        )
    )
    self.set_params(_MADCTL, param_mv[:1])

    color_size = lv.color_format_get_size(self._color_space)
    if color_size == 2:  # NOQA
        pixel_format = 0x05
    elif color_size == 3:
        pixel_format = 0x07
    else:
        raise RuntimeError(
            'ST7796 IC only supports '
            'lv.COLOR_FORMAT.RGB565 or lv.COLOR_FORMAT.RGB888'
        )

    param_buf[0] = pixel_format
    self.set_params(_COLMOD, param_mv[:1])

    param_buf[0] = 0xC6
    self.set_params(_EM, param_mv[:1])

    param_buf[0] = 0x01
    self.set_params(_DIC, param_mv[:1])

    param_buf[0] = 0x80
    param_buf[1] = 0x02
    param_buf[2] = 0x3B
    self.set_params(_DFC, param_mv[:3])

    param_buf[:8] = bytearray(
        [
            0x40, 0x8A, 0x00, 0x00, 0x29, 0x19, 0xA5, 0x33
        ]
    )
    self._data_bus.tx_param(_DOCA, param_mv[:8])

    param_buf[0] = 0x06
    self.set_params(_PWR2, param_mv[:1])

    param_buf[0] = 0xA7
    self.set_params(_PWR3, param_mv[:1])

    param_buf[0] = 0x18
    self.set_params(_VCMPCTL, param_mv[:1])

    time.sleep_ms(120)  # NOQA

    param_buf[:14] = bytearray(
        [
            0xF0, 0x09, 0x0b, 0x06, 0x04, 0x15, 0x2F,
            0x54, 0x42, 0x3C, 0x17, 0x14, 0x18, 0x1B
        ]
    )
    self.set_params(_PGC, param_mv[:14])

    param_buf[:14] = bytearray(
        [
            0xF0, 0x09, 0x0B, 0x06, 0x04, 0x03, 0x2D,
            0x43, 0x42, 0x3B, 0x16, 0x14, 0x17, 0x1B
        ]
    )
    self.set_params(_NGC, param_mv[:14])

    time.sleep_ms(120)  # NOQA

    param_buf[0] = 0x3C
    self.set_params(_CSCON, param_mv[:1])

    param_buf[0] = 0x69
    self.set_params(_CSCON, param_mv[:1])

    time.sleep_ms(120)  # NOQA

    self.set_params(_DISPON)

    time.sleep_ms(120)  # NOQA
