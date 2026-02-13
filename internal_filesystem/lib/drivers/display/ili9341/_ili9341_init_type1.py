# Copyright (c) 2024 - 2025 Kevin G. Schlosser

import time
from micropython import const  # NOQA
import lvgl as lv  # NOQA


_PWR1 = const(0xC0)
_PWR2 = const(0xC1)
_VCOMCTL1 = const(0xC5)
_VCOMCTL2 = const(0xC7)
_MADCTL = const(0x36)
_COLMOD = const(0x3A)
_FRMCTR1 = const(0xB1)
_DFUNCTRL = const(0xB6)
_GAMSET = const(0x26)
_PGC = const(0xE0)
_NGC = const(0xE1)
_SLPOUT = const(0x11)
_DISPON = const(0x29)
_RASET = const(0x2B)
_CASET = const(0x2A)
_PWRCTRLB = const(0xCF)
_PWRONSQCTRL = const(0xED)
_DRVTIMCTRLA1 = const(0xE8)
_PWRCTRLA = const(0xCB)
_PUMPRATIOCTRL = const(0xF7)
_DRVTIMCTRLB = const(0xEA)
_ENA3GAMMA = const(0xF2)


def init(self):
    param_buf = bytearray(15)
    param_mv = memoryview(param_buf)

    param_buf[:3] = bytearray([0x03, 0x80, 0x02])
    self.set_params(0xEF, param_mv[:3])

    param_buf[:3] = bytearray([0x00, 0XC1, 0X30])
    self.set_params(_PWRCTRLB, param_mv[:3])

    param_buf[:4] = bytearray([0x64, 0x03, 0X12, 0X81])
    self.set_params(_PWRONSQCTRL, param_mv[:4])

    param_buf[:3] = bytearray([0x85, 0x00, 0x78])
    self.set_params(_DRVTIMCTRLA1, param_mv[:3])

    param_buf[:5] = bytearray([0x39, 0x2C, 0x00, 0x34, 0x02])
    self.set_params(_PWRCTRLA, param_mv[:5])

    param_buf[0] = 0x20
    self.set_params(_PUMPRATIOCTRL, param_mv[:1])

    param_buf[:2] = bytearray([0x00, 0x00])
    self.set_params(_DRVTIMCTRLB, param_mv[:2])

    param_buf[0] = 0x23
    self.set_params(_PWR1, param_mv[:1])

    param_buf[0] = 0x10
    self.set_params(_PWR2, param_mv[:1])

    param_buf[:2] = bytearray([0x3e, 0x28])
    self.set_params(_VCOMCTL1, param_mv[:2])

    param_buf[0] = 0x86
    self.set_params(_VCOMCTL2, param_mv[:1])

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

    param_buf[:2] = bytearray([0x00, 0x13])  # 0x18 ??
    self.set_params(_FRMCTR1, param_mv[:2])

    param_buf[:3] = bytearray([0x08, 0x82, 0x27])
    self.set_params(_DFUNCTRL, param_mv[:3])

    param_buf[0] = 0x00
    self.set_params(_ENA3GAMMA, param_mv[:1])

    param_buf[0] = 0x01
    self.set_params(_GAMSET, param_mv[:1])

    param_buf[:15] = bytearray([
        0x0F, 0x31, 0x2B, 0x0C, 0x0E, 0x08, 0x4E, 0xF1,
        0x37, 0x07, 0x10, 0x03, 0x0E, 0x09, 0x00])
    self.set_params(_PGC, param_mv[:15])

    param_buf[:15] = bytearray([
        0x00, 0x0E, 0x14, 0x03, 0x11, 0x07, 0x31, 0xC1,
        0x48, 0x08, 0x0F, 0x0C, 0x31, 0x36, 0x0F])
    self.set_params(_NGC, param_mv[:15])

    self.set_params(_SLPOUT)
    time.sleep_ms(120)  # NOQA
    self.set_params(_DISPON)
    time.sleep_ms(20)  # NOQA
