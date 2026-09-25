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

    Rotation: the ST7701 has no row/column exchange for the video
    interface, so a rotated (e.g. landscape) UI is produced by the ESP32-P4's
    PPA instead: create the bus with the matching `rotation` (degrees) and
    pass the same rotation here; LVGL then renders the rotated picture and
    the bus rotates every finished update into the panel's back buffer. The
    rotation is fixed at construction (set_rotation() later is refused).
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
        rotation=lv.DISPLAY_ROTATION._0,
    ):
        self.panel_id = None
        self._fixed_rotation = rotation

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

        if rotation != lv.DISPLAY_ROTATION._0:
            # LVGL works in the rotated (logical) resolution from now on; the
            # bus does the pixel rotation (DSIBus rotation=...).
            self._disp_drv.set_rotation(rotation)

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

    def set_rotation(self, value):
        if value != self._fixed_rotation:
            raise NotImplementedError(
                'ST7701_DSI: rotation is fixed at construction (DSIBus rotation=... and rotation=...)'
            )

    def _set_memory_location(self, x1, y1, x2, y2):  # NOQA
        # video-mode panel: no CASET/RASET/RAMWR
        return -1

    def _on_size_change(self, _):
        # Track LVGL's idea of the size only; MADCTL cannot rotate this panel.
        self._rotation = self._disp_drv.get_rotation()
        self._width = self._disp_drv.get_horizontal_resolution()
        self._height = self._disp_drv.get_vertical_resolution()
