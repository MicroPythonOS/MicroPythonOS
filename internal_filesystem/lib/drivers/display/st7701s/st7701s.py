import lvgl as lv
import rgb_display_framework


class ST7701S(rgb_display_framework.RGBDisplayDriver):
    # Re-exported so the board can pass ST7701S.BYTE_ORDER_RGB as color_byte_order.
    BYTE_ORDER_RGB = rgb_display_framework.BYTE_ORDER_RGB

    _INVOFF = 0x20  # Color Inversion Off
    _INVON = 0x21   # Color Inversion On

    def __init__(
        self,
        data_bus,
        spi_3wire,
        display_width,
        display_height,
        frame_buffer1=None,
        frame_buffer2=None,
        reset_pin=None,
        reset_state=rgb_display_framework.STATE_HIGH,
        power_pin=None,
        power_on_state=rgb_display_framework.STATE_HIGH,
        backlight_pin=None,
        backlight_on_state=rgb_display_framework.STATE_HIGH,
        offset_x=0,
        offset_y=0,
        color_byte_order=rgb_display_framework.BYTE_ORDER_RGB,
        color_space=lv.COLOR_FORMAT.RGB565,
        rgb565_byte_swap=False,
        bus_shared_pins=False,
    ):
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
            color_space=color_space,
            rgb565_byte_swap=rgb565_byte_swap,
            spi_3wire=spi_3wire,
            spi_3wire_shared_pins=bus_shared_pins,
            _cmd_bits=8,
            _param_bits=8,
            _init_bus=False,  # run _spi_3wire_init (register config) BEFORE the RGB bus
        )

    def _spi_3wire_init(self, type=None):
        # The framework already ran spi_3wire.init(). Send the panel sequence
        # via self.set_params, which routes to spi_3wire.tx_param.
        mod = __import__('_st7701s_init')
        mod.init(self)
