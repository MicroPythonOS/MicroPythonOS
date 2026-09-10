import display_driver_framework
import lvgl as lv


STATE_HIGH = display_driver_framework.STATE_HIGH
STATE_LOW = display_driver_framework.STATE_LOW
STATE_PWM = display_driver_framework.STATE_PWM

BYTE_ORDER_RGB = display_driver_framework.BYTE_ORDER_RGB
BYTE_ORDER_BGR = display_driver_framework.BYTE_ORDER_BGR


class _USBDispBus:
    def __init__(self, usb_dev):
        self._dev = usb_dev
        self._callback = None

    def allocate_framebuffer(self, size, flags):
        return bytearray(size)

    def free_framebuffer(self, fb):
        return None

    def init(self, *args, **kwargs):
        return None

    def tx_param(self, cmd, params=None):
        return None

    def rx_param(self, cmd, params):
        return 0

    def register_callback(self, callback):
        self._callback = callback

    def tx_color(self, cmd, data_view, x1, y1, x2, y2, rotation, last_update):
        w = x2 - x1 + 1
        h = y2 - y1 + 1
        self._dev.update_565(x1, y1, w, h, data_view)
        if last_update:
            self._dev.flush(100)
        if self._callback is not None:
            self._callback()


class USB_DISP(display_driver_framework.DisplayDriver):
    def __init__(
        self,
        usb_dev,
        display_width,
        display_height,
        frame_buffer1=None,
        frame_buffer2=None,
        offset_x=0,
        offset_y=0,
        color_space=lv.COLOR_FORMAT.RGB565,  # NOQA
    ):
        if color_space != lv.COLOR_FORMAT.RGB565:  # NOQA
            raise ValueError("USB_DISP PoC only supports RGB565")
        self._usb_dev = usb_dev
        super().__init__(
            data_bus=_USBDispBus(usb_dev),
            display_width=display_width,
            display_height=display_height,
            frame_buffer1=frame_buffer1,
            frame_buffer2=frame_buffer2,
            offset_x=offset_x,
            offset_y=offset_y,
            color_space=color_space,  # NOQA
            _init_bus=True
        )

    def init(self, type=None):  # NOQA
        self._initilized = True

    def set_rotation(self, value):
        if value != lv.DISPLAY_ROTATION._0:  # NOQA
            raise ValueError("USB_DISP only supports rotation _0")
        super().set_rotation(value)

    def poll(self):
        return self._usb_dev.poll()
