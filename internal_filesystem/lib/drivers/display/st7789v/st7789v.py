# Copyright (c) 2024 - 2025 Kevin G. Schlosser

from micropython import const  # NOQA
import display_driver_framework
import lcd_bus
import lvgl as lv


STATE_HIGH = display_driver_framework.STATE_HIGH
STATE_LOW = display_driver_framework.STATE_LOW
STATE_PWM = display_driver_framework.STATE_PWM

BYTE_ORDER_RGB = display_driver_framework.BYTE_ORDER_RGB
BYTE_ORDER_BGR = display_driver_framework.BYTE_ORDER_BGR

_MADCTL_MV = const(0x20)  # 0=Normal, 1=Row/column exchange
_MADCTL_MX = const(0x40)  # 0=Left to Right, 1=Right to Left
_MADCTL_MY = const(0x80)  # 0=Top to Bottom, 1=Bottom to Top

_INVCTR = const(0xB4)  # Display Inversion Control (ST7789V)


class ST7789V(display_driver_framework.DisplayDriver):
    _ORIENTATION_TABLE = (
        0x0,
        _MADCTL_MV | _MADCTL_MX,
        _MADCTL_MY | _MADCTL_MX,
        _MADCTL_MV | _MADCTL_MY
    )

    # ST7789V uses 0xB4 for inversion control, not 0x20/0x21.
    _INVON = 0x01
    _INVOFF = 0x00

    def __init__(
        self,
        data_bus,
        display_width,
        display_height,
        frame_buffer1=None,
        frame_buffer2=None,
        reset_pin=None,
        reset_state=STATE_HIGH,
        power_pin=None,
        power_on_state=STATE_HIGH,
        backlight_pin=None,
        backlight_on_state=STATE_HIGH,
        offset_x=0,
        offset_y=0,
        color_byte_order=BYTE_ORDER_RGB,
        color_space=lv.COLOR_FORMAT.RGB888,  # NOQA
        rgb565_byte_swap=False,
    ):

        if color_space != lv.COLOR_FORMAT.RGB565:  # NOQA
            rgb565_byte_swap = False

        self._rgb565_byte_swap = rgb565_byte_swap

        if (
            isinstance(data_bus, lcd_bus.I80Bus) and
            data_bus.get_lane_count() == 8
        ):
            rgb565_byte_swap = False

        super().__init__(
            data_bus=data_bus,
            display_width=display_width,
            display_height=display_height,
            frame_buffer1=frame_buffer1,
            frame_buffer2=frame_buffer2,
            reset_pin=reset_pin,
            reset_state=reset_state,
            power_pin=power_pin,
            power_on_state=power_on_state,
            backlight_pin=backlight_pin,
            backlight_on_state=backlight_on_state,
            offset_x=offset_x,
            offset_y=offset_y,
            color_byte_order=color_byte_order,
            color_space=color_space,  # NOQA
            rgb565_byte_swap=rgb565_byte_swap,
            _cmd_bits=8,
            _param_bits=8,
            _init_bus=True
        )

    def set_color_inversion(self, value):
        # ST7789V uses 0xB4 with parameter:
        #   bit 0: 0 = normal, 1 = inverted
        self._param_buf[0] = self._INVON if value else self._INVOFF
        self.set_params(_INVCTR, self._param_mv[:1])
