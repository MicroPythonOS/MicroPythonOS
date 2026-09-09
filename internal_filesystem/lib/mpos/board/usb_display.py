import logging
import time

import lvgl as lv

logger = logging.getLogger(__name__)


# width/height default to 640x480: smallest standard DMT mode, proven to sync.
# Never request below that: smaller modes need a sub-25MHz pixel clock that
# real monitors cannot sync to (verified). 0,0 = EDID auto.
def try_init_usb_display(width=640, height=480, timeout_s=10, buf_lines=16):
    import usb_disp
    import drivers.display.usb_disp as usb_disp_driver
    dev = usb_disp.USBDisp(width=width, height=height)
    dev.start()
    if timeout_s:
        logger.warning("waiting for USB display (timeout %ss)..." % (timeout_s))
        deadline = time.ticks_add(time.ticks_ms(), timeout_s * 1000)
    else:
        logger.warning("waiting for USB display (no timeout, Ctrl-C to abort)...")
        deadline = None
    while not dev.ready():
        dev.poll()
        if deadline is not None and time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            raise RuntimeError("USB display not ready within %ss" % (timeout_s))
        time.sleep_ms(100)
    disp_width = dev.width()
    disp_height = dev.height()
    logger.warning("USB display ready: %sx%s chip=%s" % (disp_width, disp_height, dev.chip_name()))
    buf_size = disp_width * buf_lines * 2
    display = usb_disp_driver.USB_DISP(
        usb_dev=dev,
        display_width=disp_width,
        display_height=disp_height,
        frame_buffer1=bytearray(buf_size),
        frame_buffer2=bytearray(buf_size),
        color_space=lv.COLOR_FORMAT.RGB565,
    )
    display.init()
    lv.timer_create(lambda t: _poll_cb(dev), 1000, None)
    return display


def _poll_cb(dev):
    if dev.poll():
        logger.warning("USB display event: ready=%s %sx%s" % (dev.ready(), dev.width(), dev.height()))
