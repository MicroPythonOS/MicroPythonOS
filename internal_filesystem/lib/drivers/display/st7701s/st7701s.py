import lvgl as lv
import rgb_display_framework


class ST7701S(rgb_display_framework.RGBDisplayDriver):
    def __init__(
        self,
        data_bus,
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
        color_space=lv.COLOR_FORMAT.RGB888,
        set_params_func=None,
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
            rgb565_byte_swap=False,
        )
        self.set_params_func = set_params_func

        mod_name = f'_st7701s_init'
        mod = __import__(mod_name)
        mod.init(self)

    def set_params(self, cmd, params=None):
        if self.set_params_func:
            self.set_params_func(cmd, params)
        else:
            super().set_params(cmd, params)
