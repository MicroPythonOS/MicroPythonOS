# Copyright (c) 2024 - 2025 Kevin G. Schlosser

from micropython import const  # NOQA
import display_driver_framework


STATE_HIGH = display_driver_framework.STATE_HIGH
STATE_LOW = display_driver_framework.STATE_LOW
STATE_PWM = display_driver_framework.STATE_PWM

BYTE_ORDER_RGB = display_driver_framework.BYTE_ORDER_RGB
BYTE_ORDER_BGR = display_driver_framework.BYTE_ORDER_BGR

_MADCTL_MV = const(0x20)
_MADCTL_MX = const(0x40)
_MADCTL_MY = const(0x80)


class ST7796(display_driver_framework.DisplayDriver):

    _ORIENTATION_TABLE = (
        _MADCTL_MX,
        _MADCTL_MV | _MADCTL_MY | _MADCTL_MX,
        _MADCTL_MY,
        _MADCTL_MV
    )
