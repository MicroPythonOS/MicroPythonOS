# Copyright (c) 2024 - 2025 Kevin G. Schlosser

# FT6236/FT6336/FT6436/FT6436L

from micropython import const  # NOQA
import focaltech_touch
import pointer_framework


I2C_ADDR = const(0x38)
BITS = 8

_FT6x36_CHIPID_1 = const(0x36)
_FT6x36_CHIPID_2 = const(0x64)
_FT6x36_CHIPID_3 = const(0xCD)


class FT6x36(focaltech_touch.FocalTechTouch):

    def __init__(
        self,
        device,
        touch_cal=None,
        startup_rotation=pointer_framework.lv.DISPLAY_ROTATION._0,  # NOQA
        debug=False
    ):  # NOQA

        super().__init__(
            device,
            touch_cal,
            startup_rotation,
            debug,
            None,
            _FT6x36_CHIPID_1,
            _FT6x36_CHIPID_2,
            _FT6x36_CHIPID_3
        )
