import lvgl as lv
import micropython
import keypad_framework
from micropython import const

import mpos.ui
import mpos.ui.focus_direction

# Indices in expander.digital tuple:
# (usb_plugged, joy_right, joy_left, joy_down, joy_up,
#  button_menu, button_b, button_a, button_y, button_x,
#  charger_standby, charger_charging)
_IDX_JOY_RIGHT = const(1)
_IDX_JOY_LEFT  = const(2)
_IDX_JOY_DOWN  = const(3)
_IDX_JOY_UP    = const(4)
_IDX_BTN_MENU  = const(5)
_IDX_BTN_B     = const(6)
_IDX_BTN_A     = const(7)
_IDX_BTN_Y     = const(8)
_IDX_BTN_X     = const(9)

_BUTTON_INDICES = (
    _IDX_JOY_RIGHT,
    _IDX_JOY_LEFT,
    _IDX_JOY_DOWN,
    _IDX_JOY_UP,
    _IDX_BTN_MENU,
    _IDX_BTN_B,
    _IDX_BTN_A,
    _IDX_BTN_Y,
    _IDX_BTN_X,
)

# joy_up/down/left/right -> navigation
# button_a               -> ENTER
# button_b               -> NEXT  (tab forward)
# button_menu            -> HOME
# button_x               -> ESC
# button_y               -> PREV  (tab backward)
_KEY_MAP = {
    _IDX_JOY_RIGHT: lv.KEY.RIGHT,
    _IDX_JOY_LEFT:  lv.KEY.LEFT,
    _IDX_JOY_DOWN:  lv.KEY.DOWN,
    _IDX_JOY_UP:    lv.KEY.UP,
    _IDX_BTN_A:     lv.KEY.ENTER,
    _IDX_BTN_B:     lv.KEY.NEXT,
    _IDX_BTN_MENU:  lv.KEY.HOME,
    _IDX_BTN_X:     lv.KEY.ESC,
    _IDX_BTN_Y:     lv.KEY.PREV,
}


class Fri3d2026Expander(keypad_framework.KeypadDriver):
    """LVGL indev keypad driver for the Fri3d Camp 2026 badge expander.

    Pass an Expander instance that was created WITHOUT an int_pin. The driver
    itself optionally owns the interrupt pin so it can schedule LVGL reads on
    every state change rather than relying on the LVGL polling timer.

    Usage (polling)::

        from drivers.fri3d.expander import Expander
        from drivers.indev.fri3d_2026_expander import Fri3d2026Expander
        from machine import I2C, Pin

        i2c = I2C(0, sda=Pin(39), scl=Pin(42), freq=400_000)
        exp = Expander(i2c)
        kbd = Fri3d2026Expander(exp)

    Usage (interrupt-driven)::

        int_pin = Pin(X, Pin.IN, Pin.PULL_UP)
        exp = Expander(i2c)
        kbd = Fri3d2026Expander(exp, int_pin=int_pin)
    """

    def __init__(self, expander, int_pin=None):
        super().__init__()
        self._expander = expander
        self._int_pin = int_pin
        self._prev_digital = None
        self._queue = []

        if int_pin is not None:
            def _irq_cb(_):
                try:
                    micropython.schedule(Fri3d2026Expander._on_interrupt, self)
                except Exception:
                    pass

            int_pin.irq(trigger=int_pin.IRQ_RISING, handler=_irq_cb)

    def _on_interrupt(self):
        self._poll_state()
        self.read()

    def _poll_state(self):
        """Compare current digital state to previous; enqueue changed buttons."""
        digital = self._expander.digital

        if self._prev_digital is None:
            self._prev_digital = digital
            return

        for idx in _BUTTON_INDICES:
            prev = self._prev_digital[idx]
            curr = digital[idx]
            if curr != prev:
                state = self.PRESSED if curr else self.RELEASED
                self._queue.append((state, _KEY_MAP[idx]))

        self._prev_digital = digital

    def _get_key(self):
        if self._int_pin is None:
            # Polling mode: detect changes on every LVGL tick.
            self._poll_state()

        if self._queue:
            state, key = self._queue.pop(0)
            if state == self.PRESSED:
                if key == lv.KEY.ESC:
                    mpos.ui.back_screen()
                elif key == lv.KEY.RIGHT:
                    mpos.ui.focus_direction.move_focus_direction(90)
                elif key == lv.KEY.LEFT:
                    mpos.ui.focus_direction.move_focus_direction(270)
                elif key == lv.KEY.UP:
                    mpos.ui.focus_direction.move_focus_direction(0)
                elif key == lv.KEY.DOWN:
                    mpos.ui.focus_direction.move_focus_direction(180)
            return state, key

        return None
