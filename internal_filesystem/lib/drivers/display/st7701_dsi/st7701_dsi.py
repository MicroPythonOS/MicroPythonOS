import time

from micropython import const  # NOQA
import lvgl as lv
import display_driver_framework

STATE_HIGH = display_driver_framework.STATE_HIGH
STATE_LOW = display_driver_framework.STATE_LOW
STATE_PWM = display_driver_framework.STATE_PWM

BYTE_ORDER_RGB = display_driver_framework.BYTE_ORDER_RGB
BYTE_ORDER_BGR = display_driver_framework.BYTE_ORDER_BGR

_RDDID = const(0x04)  # Read Display ID


class ST7701_DSI(display_driver_framework.DisplayDriver):
    """ST7701 over MIPI-DSI in video mode (lcd_bus.DSIBus).

    The DSI bus owns two screen-sized frame buffers that LVGL renders into
    directly and the SoC's DPI DMA scans out continuously, so unlike the
    SPI/I80 panels there is no window addressing (CASET/RASET/RAMWR) and no
    per-flush pixel transfer here. What this driver does is bring the panel
    up: hardware reset, then the DCS register setup (bank selects, gamma,
    power, timing, SLPOUT, DISPON) over the same DSI link. The bus starts
    the video stream on the first flush, i.e. after that setup, the order
    Espressif's own esp_lcd_st7701 MIPI driver uses.

    Rotation is not supported: the ST7701 has no row/column exchange for
    the video interface, so the display runs in the panel's native
    orientation.
    """

    STATE_HIGH = STATE_HIGH
    STATE_LOW = STATE_LOW
    STATE_PWM = STATE_PWM
    BYTE_ORDER_RGB = BYTE_ORDER_RGB
    BYTE_ORDER_BGR = BYTE_ORDER_BGR

    _INVOFF = 0x20  # Color Inversion Off
    _INVON = 0x21   # Color Inversion On

    def __init__(
        self,
        data_bus,
        display_width,
        display_height,
        frame_buffer1,
        frame_buffer2=None,
        reset_pin=None,
        reset_state=STATE_LOW,
        power_pin=None,
        power_on_state=STATE_HIGH,
        backlight_pin=None,
        backlight_on_state=STATE_HIGH,
        color_byte_order=BYTE_ORDER_RGB,
        color_space=lv.COLOR_FORMAT.RGB565,
    ):
        self.panel_id = None

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
            offset_x=0,
            offset_y=0,
            color_byte_order=color_byte_order,
            color_space=color_space,
            rgb565_byte_swap=False,
            _cmd_bits=8,
            _param_bits=8,
            _init_bus=True,  # creates the DSI bus, the DBI command IO and the DPI panel (frame buffers)
        )

    def init(self, type=None):  # NOQA
        # Hardware reset: reset_state is the active level (the framework
        # holds it for 120 ms), then give the controller time to come up.
        self.reset()
        time.sleep_ms(120)  # NOQA

        # The ID read is the first traffic over the link, a cheap check that
        # the panel answers before the long register setup.
        try:
            buf = bytearray(3)
            self.get_params(_RDDID, buf)
            self.panel_id = bytes(buf)
        except Exception as e:  # NOQA
            print('ST7701_DSI: panel ID read failed: %s' % e)

        from . import _st7701_dsi_init
        _st7701_dsi_init.init(self)

        # No window to set: the whole frame buffer is what the panel shows.
        self._initilized = True

    def set_params(self, cmd, params=None):
        self._data_bus.tx_param(cmd, params)

    def get_params(self, cmd, params):
        self._data_bus.rx_param(cmd, params)

    def _set_memory_location(self, x1, y1, x2, y2):  # NOQA
        # video-mode panel: no CASET/RASET/RAMWR
        return -1

    def _on_size_change(self, _):
        # Track LVGL's idea of the size only; MADCTL cannot rotate this panel.
        self._rotation = self._disp_drv.get_rotation()
        self._width = self._disp_drv.get_horizontal_resolution()
        self._height = self._disp_drv.get_vertical_resolution()
