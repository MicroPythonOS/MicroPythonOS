# Web (Emscripten) fake Fri3d 2026 expander for MicroPythonOS.
#
# Presents the same `digital` / `analog` surface as
# drivers.fri3d.expander.Expander, but reads button/joystick state from the
# browser page via the `_webio` native bridge (Module.__webio.buttons bitmask
# + joy_x/joy_y axes, driven by the on-page D-pad/buttons in shell.html).
#
# This lets the REAL Fri3d2026Expander LVGL indev driver
# (drivers.indev.fri3d_2026_expander) run unchanged on the web build, so key
# mapping, long-press repeat and navigation hooks behave exactly like on the
# physical badge.

import _webio

_webio.init()

# Bit positions in the buttons bitmask == indices in the digital tuple:
# (usb_plugged, joy_right, joy_left, joy_down, joy_up,
#  button_menu, button_b, button_a, button_y, button_x,
#  charger_standby, charger_charging)
_DIGITAL_LEN = 12


class WebExpander:
    @property
    def digital(self):
        bits = _webio.buttons()
        return tuple(bool(bits & (1 << i)) for i in range(_DIGITAL_LEN))

    @property
    def analog(self):
        # (ain0, battery_monitor, usb_monitor, joystick_y, joystick_x)
        x, y = _webio.joystick()
        return (0, 2048, 0, y, x)
