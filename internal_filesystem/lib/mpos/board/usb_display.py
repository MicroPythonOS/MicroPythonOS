import gc
import logging
import time

import lvgl as lv

logger = logging.getLogger(__name__)

_usb_dev = None
_usb_display = None
_panel_display = None
_panel_backlight = None
_active = "panel"
_switching = False
_poll_timer = None
_pump_suspended = False
# Future Settings-toggle seam: when False, hotplugged displays enumerate
# but the UI never auto-switches (manual switch_to_usb still works).
_auto_switch = True


def is_available():
    try:
        import usb_disp  # NOQA
        return True
    except ImportError:
        return False


def arm_usb_display(width=640, height=480):
    global _usb_dev
    if not is_available():
        return None
    if _usb_dev is None:
        import usb_disp
        _usb_dev = usb_disp.USBDisp(width=width, height=height)
    _usb_dev.start()
    _ensure_poll_timer()
    return _usb_dev


# width/height default to 640x480: smallest standard DMT mode, proven to sync.
# Never request below that: smaller modes need a sub-25MHz pixel clock that
# real monitors cannot sync to (verified). 0,0 = EDID auto.
def try_init_usb_display(width=640, height=480, timeout_s=10, buf_lines=16):
    global _usb_display
    import drivers.display.usb_disp as usb_disp_driver
    dev = arm_usb_display(width=width, height=height)
    if dev is None:
        raise RuntimeError("USB display unavailable (stock build?)")
    if timeout_s:
        logger.warning("usb wait %ss" % (timeout_s))
        deadline = time.ticks_add(time.ticks_ms(), timeout_s * 1000)
    else:
        logger.warning("usb wait (Ctrl-C aborts)...")
        deadline = None
    _polls = 0
    while not dev.ready():
        dev.poll()
        _polls += 1
        if deadline is not None and time.ticks_diff(deadline, time.ticks_ms()) <= 0:
            raise RuntimeError("usb timeout %ss polls=%d" % (timeout_s, _polls))
        time.sleep_ms(100)
    disp_width = dev.width()
    disp_height = dev.height()
    logger.warning("usb ready %sx%s %s polls=%d" % (disp_width, disp_height, dev.chip_name(), _polls))
    buf_size = disp_width * buf_lines * 2
    logger.warning("usb bufs=%d" % (buf_size))
    display = usb_disp_driver.USB_DISP(
        usb_dev=dev,
        display_width=disp_width,
        display_height=disp_height,
        frame_buffer1=bytearray(buf_size),
        frame_buffer2=bytearray(buf_size),
        color_space=lv.COLOR_FORMAT.RGB565,
    )
    display.init()
    _load_blank(display)
    _usb_display = display
    return display


def _load_blank(display):
    prev = lv.display_get_default()
    display.set_default()
    try:
        lv.screen_load(lv.obj())
    finally:
        if prev is not None:
            prev.set_default()
    logger.warning("sw blank ok")


def switch_to_usb(width=640, height=480, timeout_s=0):
    import mpos.ui
    global _panel_display, _switching
    if _active == "usb":
        return mpos.ui.main_display
    _panel_display = mpos.ui.main_display
    _switching = True
    logger.warning("sw usb begin")
    try:
        display = try_init_usb_display(width=width, height=height, timeout_s=timeout_s)
        _swap_to(display, "usb")
        return display
    finally:
        _pump_resume()
        _switching = False


def switch_to_panel():
    import mpos.ui
    global _usb_display, _switching
    if _active == "panel":
        return mpos.ui.main_display
    if _panel_display is None:
        raise RuntimeError("no panel (USB boot)")
    _switching = True
    logger.warning("sw panel begin")
    try:
        _swap_to(_panel_display, "panel")
        if _usb_display is not None:
            _delete_display(_usb_display)
            _usb_display = None
        return mpos.ui.main_display
    finally:
        _pump_resume()
        _switching = False


def _swap_to(display, name):
    import mpos.ui
    from mpos import AppManager, DisplayMetrics, InputManager
    from mpos.ui.view import remove_and_stop_all_activities
    global _active, _panel_backlight
    old = mpos.ui.main_display
    logger.warning("sw teardown old=%s new=%s" % (type(old).__name__, type(display).__name__))
    indevs = InputManager.list_indevs()
    logger.warning("sw indevs=%d stack=%d" % (len(indevs), len(mpos.ui.view.screen_stack)))
    _pump_suspend()
    for indev in indevs:
        indev.enable(False)
    remove_and_stop_all_activities()
    logger.warning("sw torn down stack=%d" % (len(mpos.ui.view.screen_stack)))
    _load_blank(old)
    logger.warning("sw inval off")
    old.enable_invalidation(False)
    logger.warning("sw inval off old ok")
    display.enable_invalidation(False)
    logger.warning("sw inval off new ok")
    if name == "usb":
        try:
            _panel_backlight = old.get_backlight()
            logger.warning("sw panel bl=%s" % (_panel_backlight))
        except Exception as e:
            logger.error("sw panel bl read fail: %s" % (e))
            _panel_backlight = None
        try:
            old.set_backlight(0)
            logger.warning("sw panel blanked")
        except Exception as e:
            logger.error("panel blank fail: %s" % (e))
    try:
        logger.warning("sw default")
        display.set_default()
        mpos.ui.main_display = display
        if name == "panel" and _panel_backlight is not None and _panel_backlight >= 0:
            try:
                display.set_backlight(_panel_backlight)
            except Exception as e:
                logger.error("panel bl restore fail: %s" % (e))
        logger.warning("sw indevs")
        _repoint_indevs(display)
        logger.warning("sw metrics")
        DisplayMetrics.set_resolution(display.get_horizontal_resolution(), display.get_vertical_resolution())
        DisplayMetrics.set_dpi(display.get_dpi())
        logger.warning("sw gestures")
        # Topmenu bar/drawer stay on the panel: singletons with timers bound
        # to their labels, recreating them would crash. Gesture zones are
        # recreated (one leaked set per switch, harmless).
        mpos.ui.handle_back_swipe()
        mpos.ui.handle_top_swipe()
        logger.warning("sw launcher")
        launcher = AppManager.get_launcher()
        if launcher is None:
            raise RuntimeError("no launcher")
        logger.warning("sw starting %s" % (launcher.fullname))
        ok = AppManager.start_app(launcher.fullname)
        logger.warning("sw started=%s" % (ok))
    finally:
        logger.warning("sw inval on")
        try:
            display.enable_invalidation(True)
        except Exception as e:
            logger.error("inval on fail: %s" % (e))
        try:
            old.enable_invalidation(True)
        except Exception as e:
            logger.error("old inval on fail: %s" % (e))
        _pump_resume()
    _active = name
    logger.warning("switched to %s" % (name))


def _pump_suspend():
    global _pump_suspended
    if _pump_suspended:
        return
    try:
        import mpos.ui
        th = getattr(mpos.ui, "task_handler", None)
        if th is not None:
            th.disable()
            _pump_suspended = True
            logger.warning("sw pump off")
    except Exception as e:
        logger.error("sw pump off fail: %s" % (e))


def _pump_resume():
    global _pump_suspended
    if not _pump_suspended:
        return
    _pump_suspended = False
    try:
        import mpos.ui
        th = getattr(mpos.ui, "task_handler", None)
        if th is not None:
            th.enable()
            logger.warning("sw pump on")
    except Exception as e:
        logger.error("sw pump on fail: %s" % (e))


def _repoint_indevs(display):
    import display_driver_framework
    from mpos import InputManager
    new_lv_disp = display._disp_drv
    py_disp = None
    for d in display_driver_framework.DisplayDriver.get_displays():
        if d._disp_drv == new_lv_disp:
            py_disp = d
            break
    for indev in InputManager.list_indevs():
        logger.warning("sw indev %s" % (type(indev).__name__))
        indev._indev_drv.set_display(new_lv_disp)
        indev._disp_drv = new_lv_disp
        indev._width = new_lv_disp.get_horizontal_resolution()
        indev._height = new_lv_disp.get_vertical_resolution()
        indev._py_disp_drv = py_disp
        new_lv_disp.add_event_cb(indev._on_size_change, lv.EVENT.RESOLUTION_CHANGED, None)
        indev.enable(True)
    logger.warning("sw indevs done")


def _delete_display(display):
    import display_driver_framework
    try:
        displays = display_driver_framework.DisplayDriver.get_displays()
        if display in displays:
            displays.remove(display)
    except Exception as e:
        logger.error("untrack fail: %s" % (e))
    try:
        display._disp_drv.delete()
    except Exception as e:
        logger.error("delete fail: %s" % (e))
    gc.collect()


def _ensure_poll_timer():
    global _poll_timer
    if _poll_timer is None:
        _poll_timer = lv.timer_create(_poll_cb, 1000, None)


def _poll_cb(t):
    dev = _usb_dev
    if dev is None or _switching:
        return
    try:
        event = dev.poll()
    except Exception as e:
        logger.error("usb poll fail: %s" % (e))
        return
    try:
        ready = dev.ready()
    except Exception:
        return
    if event and ready and _active == "panel" and _auto_switch:
        logger.warning("usb ready, auto-switch")
        try:
            switch_to_usb(timeout_s=5)
        except Exception as e:
            logger.error("auto-switch fail: %s" % (e))
    elif _active == "usb" and event and not ready:
        logger.warning("usb gone, back to panel")
        try:
            switch_to_panel()
        except Exception as e:
            logger.error("auto-revert fail: %s" % (e))
    elif event:
        logger.warning("usb ev ready=%s %sx%s" % (ready, dev.width(), dev.height()))
