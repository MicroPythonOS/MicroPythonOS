import gc
import logging
import time

import lvgl as lv

logger = logging.getLogger(__name__)


class USBManager:
    _usb_dev = None
    _usb_display = None
    _panel_display = None
    _panel_backlight = None
    _active = "panel"
    _switching = False
    _poll_timer = None
    _pump_suspended = False
    # USB touch exceptions: ONLY boards whose drag test disagrees with the
    # default (same orientation: scale; portrait panel to landscape USB: rotate
    # clockwise, no mirrors) get an entry. Empty by design; the panel's own
    # proven mapping is reused, so mounting knowledge is never needed here.
    _USB_TOUCH_EXC = {
        # "board_id": {"ccw": True, "mx": True, "my": True},
    }
    _wrapped_indevs = []
    _usb_mouse = None
    _usb_keyboard = None
    _hid_hub = None
    _hid_idle_prev = None
    # Future Settings-toggle seam: when False, hotplugged displays enumerate
    # but the UI never auto-switches (manual switch_to_usb still works).
    _auto_switch = True
    _sw_idle_polls = 0
    _sw_retries = 0
    _SW_RETRY_EVERY = 5
    _SW_MAX_RETRIES = 6
    # Host-mode preference lives in the Settings app's preferences (same
    # key the Settings UI persists), so UI, REPL and boot all share one
    # source of truth. Stored as strings ("on"/"once"/"off"); only "on"
    # boots into host mode.
    _HOST_PREFS = "com.micropythonos.settings"
    _HOST_MODE_KEY = "usb_host_mode"

    @classmethod
    def is_available(cls):
        try:
            import usb  # NOQA
            return True
        except ImportError:
            return False

    @classmethod
    def _get_host_pref(cls):
        try:
            from mpos import SharedPreferences
            return SharedPreferences(cls._HOST_PREFS).get_string(cls._HOST_MODE_KEY) == "on"
        except Exception:
            return False

    @classmethod
    def _set_host_pref(cls, on):
        try:
            from mpos import SharedPreferences
            SharedPreferences(cls._HOST_PREFS).edit().put_string(
                cls._HOST_MODE_KEY, "on" if on else "off").commit()
        except Exception as e:
            logger.error("usb host pref save fail: %s" % (e))

    @classmethod
    def _bootsel_held(cls):
        # Physical escape hatch: BOOT held at boot forces CDC device mode
        # regardless of the persisted flag (no-UART boards would otherwise
        # strand headless in host mode). Best effort: GPIO0 with pull-up
        # on most S3 boards; silent no-op anywhere else.
        try:
            from machine import Pin
            import time as _time
            boot = Pin(0, Pin.IN, Pin.PULL_UP)
            _time.sleep_ms(5)
            return boot.value() == 0
        except Exception:
            return False

    @classmethod
    def host_boot_requested(cls):
        if cls._bootsel_held():
            logger.warning("usb BOOTSEL held: staying in CDC device mode")
            return False
        return cls._get_host_pref()

    @classmethod
    def host_mode_active(cls):
        try:
            import usb
        except ImportError:
            return False
        if not hasattr(usb, "host_active"):
            return False
        try:
            return bool(usb.host_active())
        except Exception:
            return False

    @classmethod
    def activate(cls, persist=True):
        # Runtime switch from CDC device mode to USB host mode. Tears down
        # TinyUSB, starts the host stack, arms display + HID. CDC dies here
        # by design (announce it in the UI before calling).
        try:
            import usb
        except ImportError:
            return False
        if not hasattr(usb, "activate_host"):
            return False
        try:
            usb.activate_host()
        except Exception as e:
            logger.error("usb host activate fail: %s" % (e))
            return False
        cls.arm_display()
        cls.arm_hid()
        if persist:
            cls._set_host_pref(True)
        return True

    @classmethod
    def deactivate(cls, persist=True):
        # Runtime switch back to CDC device mode. The UI must be on panel
        # first (can't tear down the active display); indevs are
        # unregistered + deleted so no stale pointers survive.
        try:
            import usb
        except ImportError:
            return False
        if not hasattr(usb, "deactivate_host"):
            return False
        if cls._active == "usb":
            try:
                cls.switch_to_panel()
            except Exception as e:
                logger.error("usb host deactivate switch-back fail: %s" % (e))
                return False
        try:
            from mpos import InputManager
            for dev in (cls._usb_mouse, cls._usb_keyboard):
                if dev is None:
                    continue
                try:
                    InputManager.unregister_indev(dev)
                except Exception:
                    pass
                try:
                    dev.delete()
                except Exception as e:
                    logger.error("usb hid delete fail: %s" % (e))
        except Exception as e:
            logger.error("usb hid teardown fail: %s" % (e))
        cls._usb_mouse = None
        cls._usb_keyboard = None
        cls._hid_hub = None
        cls._usb_dev = None
        cls._usb_display = None
        cls._update_hid_watchdog_exclusion()
        try:
            usb.deactivate_host()
        except Exception as e:
            logger.error("usb host deactivate fail (reboot recommended): %s" % (e))
            if persist:
                cls._set_host_pref(False)
            return False
        if persist:
            cls._set_host_pref(False)
        return True

    @classmethod
    def arm_display(cls, width=640, height=480):
        if not cls.is_available():
            return None
        if cls._usb_dev is None:
            import usb
            cls._usb_dev = usb.Display(width=width, height=height)
        cls._usb_dev.start()
        cls._ensure_poll_timer()
        return cls._usb_dev

    @classmethod
    def arm_hid(cls):
        if cls._usb_mouse is not None and cls._usb_keyboard is not None:
            return cls._usb_mouse
        try:
            import usb
        except ImportError:
            return None
        if not hasattr(usb, "hid_start"):
            return None
        try:
            import drivers.indev.usb_hid as usb_hid_mod
        except ImportError as e:
            logger.error("usb hid driver import fail: %s" % (e))
            return None
        try:
            if not usb.hid_start():
                return None
        except Exception as e:
            logger.error("usb hid start fail: %s" % (e))
            return None
        from mpos import InputManager
        if cls._hid_hub is None:
            cls._hid_hub = usb_hid_mod.HIDHub()
        if cls._usb_mouse is None:
            try:
                cls._usb_mouse = usb_hid_mod.USBMouse(source=cls._hid_hub)
                InputManager.register_indev(cls._usb_mouse)
                cls._usb_mouse.attach_cursor()
                cls._usb_mouse.hide_cursor()
                cls._usb_mouse.enable(False)
            except Exception as e:
                logger.error("usb hid mouse init fail: %s" % (e))
                cls._usb_mouse = None
        if cls._usb_keyboard is None:
            try:
                cls._usb_keyboard = usb_hid_mod.USBHIDKeyboard(cls._hid_hub)
                try:
                    group = lv.group_get_default()
                except Exception:
                    group = None
                if group is not None:
                    cls._usb_keyboard.set_group(group)
                InputManager.register_indev(cls._usb_keyboard)
                cls._usb_keyboard.enable(False)
            except Exception as e:
                logger.error("usb hid keyboard init fail: %s" % (e))
                cls._usb_keyboard = None
        cls._ensure_poll_timer()
        return cls._usb_mouse

    @classmethod
    def _hid_claimed(cls):
        try:
            import usb
        except ImportError:
            return []
        if not hasattr(usb, "hid_claimed_addrs"):
            return []
        try:
            return list(usb.hid_claimed_addrs())
        except Exception as e:
            logger.error("usb hid claimed fail: %s" % (e))
            return []

    @classmethod
    def _hid_parked_entries(cls):
        try:
            import usb
        except ImportError:
            return []
        if not hasattr(usb, "hid_parked"):
            return []
        try:
            return list(usb.hid_parked())
        except Exception as e:
            logger.error("usb hid parked fail: %s" % (e))
            return []

    @classmethod
    def _update_hid_watchdog_exclusion(cls):
        # Global idle-reset suppression, parked-only: a parked device is
        # enumerated but silent, which reads exactly like a wedged adapter,
        # and with no open handle its port is unresolvable. Claimed devices
        # need no global suppression: the C watchdog skips exactly the
        # HID-owned ports (usb_hid_owns_idle_port) while other ports keep
        # healing. Restores the prior value afterwards, so a manual user
        # setting is never forced back on.
        try:
            import usb
        except ImportError:
            return
        if not hasattr(usb, "auto_reset_idle"):
            return
        parked = cls._hid_parked_entries()
        if parked and cls._hid_idle_prev is None:
            try:
                cls._hid_idle_prev = bool(usb.auto_reset_idle())
                usb.auto_reset_idle(False)
            except Exception as e:
                logger.error("hid idle suppress fail: %s" % (e))
                cls._hid_idle_prev = None
        elif not parked and cls._hid_idle_prev is not None:
            try:
                usb.auto_reset_idle(cls._hid_idle_prev)
            except Exception as e:
                logger.error("hid idle restore fail: %s" % (e))
            cls._hid_idle_prev = None

    @classmethod
    def _hid_kinds(cls, claimed):
        try:
            import usb
        except ImportError:
            return (False, False)
        if not hasattr(usb, "hid_state"):
            return (bool(claimed), bool(claimed))
        try:
            kinds = [entry[1] for entry in usb.hid_state()]
        except Exception as e:
            logger.error("usb hid kinds fail: %s" % (e))
            return (bool(claimed), bool(claimed))
        return ("mouse" in kinds, "keyboard" in kinds)

    @classmethod
    def _sync_usb_hid(cls, claimed):
        if claimed and (cls._usb_mouse is None or cls._usb_keyboard is None):
            cls.arm_hid()
        has_mouse, has_keyboard = cls._hid_kinds(claimed)
        try:
            if cls._usb_mouse is not None:
                cls._usb_mouse.enable(bool(has_mouse))
                if has_mouse:
                    cls._usb_mouse.show_cursor()
                else:
                    cls._usb_mouse.hide_cursor()
            if cls._usb_keyboard is not None:
                cls._usb_keyboard.enable(bool(has_keyboard))
        except Exception as e:
            logger.error("usb hid sync fail: %s" % (e))

    @classmethod
    def _poll_hid(cls):
        try:
            import usb
        except ImportError:
            return
        if not hasattr(usb, "hid_poll"):
            return
        try:
            usb.hid_poll()
        except Exception as e:
            logger.error("usb hid poll fail: %s" % (e))
            return
        claimed = cls._hid_claimed()
        cls._update_hid_watchdog_exclusion()
        cls._sync_usb_hid(claimed)

    # width/height default to 640x480: smallest standard DMT mode, proven to sync.
    # Never request below that: smaller modes need a sub-25MHz pixel clock that
    # real monitors cannot sync to (verified). 0,0 = EDID auto.
    @classmethod
    def try_init_usb_display(cls, width=640, height=480, timeout_s=10, buf_lines=16):
        import drivers.display.usb_display as usb_display_driver
        dev = cls.arm_display(width=width, height=height)
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
        display = usb_display_driver.USBDisplayDriver(
            usb_dev=dev,
            display_width=disp_width,
            display_height=disp_height,
            frame_buffer1=bytearray(buf_size),
            frame_buffer2=bytearray(buf_size),
            color_space=lv.COLOR_FORMAT.RGB565,
        )
        display.init()
        cls._load_blank(display)
        cls._usb_display = display
        return display

    @classmethod
    def _load_blank(cls, display):
        prev = lv.display_get_default()
        display.set_default()
        try:
            lv.screen_load(lv.obj())
        finally:
            if prev is not None:
                prev.set_default()
        logger.warning("sw blank ok")

    @classmethod
    def switch_to_usb(cls, width=640, height=480, timeout_s=0):
        import mpos.ui
        if cls._active == "usb":
            return mpos.ui.main_display
        cls._panel_display = mpos.ui.main_display
        cls._switching = True
        logger.warning("sw usb begin")
        try:
            display = cls.try_init_usb_display(width=width, height=height, timeout_s=timeout_s)
            cls._swap_to(display, "usb")
            return display
        finally:
            cls._pump_resume()
            cls._switching = False

    @classmethod
    def switch_to_panel(cls):
        import mpos.ui
        if cls._active == "panel":
            return mpos.ui.main_display
        if cls._panel_display is None:
            raise RuntimeError("no panel (USB boot)")
        cls._switching = True
        logger.warning("sw panel begin")
        try:
            cls._swap_to(cls._panel_display, "panel")
            if cls._usb_display is not None:
                cls._delete_display(cls._usb_display)
                cls._usb_display = None
            return mpos.ui.main_display
        finally:
            cls._pump_resume()
            cls._switching = False

    @classmethod
    def _swap_to(cls, display, name):
        import mpos.ui
        from mpos import AppManager, DisplayMetrics, InputManager
        from mpos.ui.view import remove_and_stop_all_activities
        old = mpos.ui.main_display
        logger.warning("sw teardown old=%s new=%s" % (type(old).__name__, type(display).__name__))
        indevs = InputManager.list_indevs()
        logger.warning("sw indevs=%d stack=%d" % (len(indevs), len(mpos.ui.view.screen_stack)))
        cls._pump_suspend()
        for indev in indevs:
            indev.enable(False)
        remove_and_stop_all_activities()
        logger.warning("sw torn down stack=%d" % (len(mpos.ui.view.screen_stack)))
        cls._load_blank(old)
        logger.warning("sw inval off")
        old.enable_invalidation(False)
        logger.warning("sw inval off old ok")
        display.enable_invalidation(False)
        logger.warning("sw inval off new ok")
        if name == "usb":
            try:
                cls._panel_backlight = old.get_backlight()
                logger.warning("sw panel bl=%s" % (cls._panel_backlight))
            except Exception as e:
                logger.error("sw panel bl read fail: %s" % (e))
                cls._panel_backlight = None
            try:
                old.set_backlight(0)
                logger.warning("sw panel blanked")
            except Exception as e:
                logger.error("panel blank fail: %s" % (e))
        try:
            logger.warning("sw default")
            display.set_default()
            mpos.ui.main_display = display
            if name == "panel":
                level = cls._panel_backlight
                if level is None or level < 0:
                    level = cls._brightness_pref()
                try:
                    display.set_backlight(level)
                except Exception as e:
                    logger.error("panel bl restore fail: %s" % (e))
            logger.warning("sw indevs")
            cls._repoint_indevs(display, old)
            if name == "usb":
                cls._wrap_all_touch(display, old)
            else:
                cls._unwrap_touch()
            logger.warning("sw metrics")
            DisplayMetrics.set_resolution(display.get_horizontal_resolution(), display.get_vertical_resolution())
            DisplayMetrics.set_dpi(display.get_dpi())
            logger.warning("sw topmenu")
            mpos.ui.topmenu.move_to_display()
            logger.warning("sw gestures")
            # Gesture zones are recreated (one leaked set per switch, harmless).
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
            cls._pump_resume()
        cls._active = name
        logger.warning("switched to %s" % (name))

    @classmethod
    def _pump_suspend(cls):
        if cls._pump_suspended:
            return
        try:
            import mpos.ui
            th = getattr(mpos.ui, "task_handler", None)
            if th is not None:
                th.disable()
                cls._pump_suspended = True
                logger.warning("sw pump off")
        except Exception as e:
            logger.error("sw pump off fail: %s" % (e))

    @classmethod
    def _pump_resume(cls):
        if not cls._pump_suspended:
            return
        cls._pump_suspended = False
        try:
            import mpos.ui
            th = getattr(mpos.ui, "task_handler", None)
            if th is not None:
                th.enable()
                logger.warning("sw pump on")
        except Exception as e:
            logger.error("sw pump on fail: %s" % (e))

    @classmethod
    def _brightness_pref(cls):
        try:
            from mpos import SharedPreferences
            return SharedPreferences("com.micropythonos.settings").get_int("display_brightness", 100)
        except Exception:
            return 100

    @classmethod
    def _repoint_indevs(cls, display, old):
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
            drv = getattr(indev, "_indev_drv", indev)
            drv.set_display(new_lv_disp)
            if hasattr(indev, "_disp_drv"):
                indev._disp_drv = new_lv_disp
                indev._width = new_lv_disp.get_horizontal_resolution()
                indev._height = new_lv_disp.get_vertical_resolution()
                indev._py_disp_drv = py_disp
            on_display_changed = getattr(indev, "_on_display_changed", None)
            if on_display_changed is not None:
                try:
                    on_display_changed(new_lv_disp)
                except Exception as e:
                    logger.error("sw indev display hook fail: %s" % (e))
            if hasattr(indev, "_on_size_change"):
                new_lv_disp.add_event_cb(indev._on_size_change, lv.EVENT.RESOLUTION_CHANGED, None)
            indev.enable(True)
        logger.warning("sw indevs done")

    @classmethod
    def _wrap_all_touch(cls, display, old):
        pw = getattr(old, "display_width", None)
        ph = getattr(old, "display_height", None)
        uw = getattr(display, "display_width", None)
        uh = getattr(display, "display_height", None)
        if None in (pw, ph, uw, uh) or 0 in (pw, ph):
            logger.error("sw touch wrap skipped (dims unknown)")
            return
        from mpos import DeviceInfo, InputManager
        try:
            exc = cls._USB_TOUCH_EXC.get(DeviceInfo.get_hardware_id(), {})
        except Exception:
            exc = {}
        for indev in InputManager.list_indevs():
            if getattr(indev, "__usb_absolute__", False):
                continue
            if not hasattr(indev, "_calc_coords") or indev in cls._wrapped_indevs:
                continue
            cls._wrapped_indevs.append(indev)
            orig = indev._calc_coords
            if (pw >= ph) == (uw >= uh):
                sx = uw / pw
                sy = uh / ph
                mx = exc.get("mx", False)
                my = exc.get("my", False)

                def usb_calc(x, y, _o=orig):
                    px, py = _o(x, y)
                    if mx:
                        px = pw - 1 - px
                    if my:
                        py = ph - 1 - py
                    return (int(px * sx), int(py * sy))
            elif exc.get("ccw", False):
                def usb_calc(x, y, _o=orig):
                    px, py = _o(x, y)
                    return (int((ph - 1 - py) * uw / ph), int(px * uh / pw))
            else:
                def usb_calc(x, y, _o=orig):
                    px, py = _o(x, y)
                    return (int(py * uw / ph), int((pw - 1 - px) * uh / pw))
            indev._calc_coords = usb_calc
        logger.warning("sw touch wrapped=%d" % (len(cls._wrapped_indevs)))

    @classmethod
    def _unwrap_touch(cls):
        for indev in cls._wrapped_indevs:
            try:
                del indev._calc_coords
            except Exception as e:
                logger.error("sw touch unwrap fail: %s" % (e))
        del cls._wrapped_indevs[:]
        logger.warning("sw touch unwrapped")

    @classmethod
    def _delete_display(cls, display):
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

    @classmethod
    def _ensure_poll_timer(cls):
        if cls._poll_timer is None:
            cls._poll_timer = lv.timer_create(cls._poll_cb, 1000, None)

    @classmethod
    def _poll_cb(cls, t):
        if not cls._switching:
            cls._poll_hid()
        dev = cls._usb_dev
        if dev is None or cls._switching:
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
        if event and ready and cls._active == "panel" and cls._auto_switch:
            logger.warning("usb ready, auto-switch")
            try:
                cls.switch_to_usb(timeout_s=5)
            except Exception as e:
                logger.error("auto-switch fail: %s" % (e))
            cls._sw_idle_polls = 0
            cls._sw_retries = 0
        elif cls._active == "usb" and event and not ready:
            logger.warning("usb gone, back to panel")
            try:
                cls.switch_to_panel()
            except Exception as e:
                logger.error("auto-revert fail: %s" % (e))
            cls._sw_idle_polls = 0
            cls._sw_retries = 0
        elif event:
            logger.warning("usb ev ready=%s %sx%s" % (ready, dev.width(), dev.height()))
            cls._sw_idle_polls = 0
            cls._sw_retries = 0
        elif ready and cls._active == "panel" and cls._auto_switch:
            cls._sw_idle_polls += 1
            if cls._sw_idle_polls >= cls._SW_RETRY_EVERY and cls._sw_retries < cls._SW_MAX_RETRIES:
                cls._sw_idle_polls = 0
                cls._sw_retries += 1
                logger.warning("usb ready but still on panel, retry %d/%d" % (cls._sw_retries, cls._SW_MAX_RETRIES))
                try:
                    cls.switch_to_usb(timeout_s=5)
                except Exception as e:
                    logger.error("auto-switch retry fail: %s" % (e))
        else:
            cls._sw_idle_polls = 0
            if not ready:
                cls._sw_retries = 0
