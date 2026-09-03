def create_expander_i2c(i2c_class, pin_class, sda, scl):
    # Camera SCCB can reconfigure I2C(0); restore the XL9535 after camera use.
    # P0.0/P0.1 are outputs, while P0.2/P1.4 return to BTN_B/BTN_A inputs.
    i2c = i2c_class(0, sda=pin_class(sda), scl=pin_class(scl), freq=400_000)
    cfg0 = i2c.readfrom_mem(0x20, 0x06, 1)[0]
    cfg0 = (cfg0 & ~0x03) | 0x04
    i2c.writeto_mem(0x20, 0x06, bytes([cfg0]))
    cfg1 = i2c.readfrom_mem(0x20, 0x07, 1)[0] | 0x10
    i2c.writeto_mem(0x20, 0x07, bytes([cfg1]))
    out0 = i2c.readfrom_mem(0x20, 0x02, 1)[0] | 0x03
    i2c.writeto_mem(0x20, 0x02, bytes([out0]))
    return i2c


def is_direct_navigation_target(focused, keyboard_type, buttonmatrix_type, dropdown_type):
    # A closed dropdown is one focus target; its open list needs direct navigation.
    if isinstance(focused, dropdown_type):
        try:
            return focused.is_open()
        except Exception:
            return False
    return isinstance(focused, keyboard_type) or isinstance(focused, buttonmatrix_type)


def initialize_camera_with_recovery(init_camera, on_failure, restore_expander_i2c, attempts=3):
    for attempt in range(attempts):
        try:
            return init_camera()
        except Exception as error:
            on_failure(attempt, error)
    restore_expander_i2c()
    return None


class K10ButtonInput:
    def __init__(self, long_press_ms=700, ticks_diff=None):
        self._long_press_ms = long_press_ms
        self._ticks_diff = ticks_diff or (lambda current, previous: current - previous)
        self._a_pressed = False
        self._a_down_at = None
        self._a_back_fired = False
        self._active_b_key = None
        self._b_dropdown_pressed = False
        self._b_down_at = None
        self._b_previous_fired = False
        self._events = []

    def update(self, a_pressed, b_pressed, now_ms, direct_navigation_focused, dropdown_open=False):
        if a_pressed and not self._a_pressed:
            self._a_down_at = now_ms
            self._a_back_fired = False
            self._cancel_b()

        if a_pressed and self._a_down_at is not None and not self._a_back_fired:
            if self._ticks_diff(now_ms, self._a_down_at) >= self._long_press_ms:
                self._a_back_fired = True
                if dropdown_open:
                    # ESC preserves LVGL's unconfirmed dropdown selection and stays in the app.
                    self._events.append(("esc", True, False))
                    self._events.append(("esc", False, False))
                else:
                    self._events.append((None, False, True))

        if not a_pressed and self._a_pressed:
            if not self._a_back_fired:
                self._events.append(("enter", True, False))
                self._events.append(("enter", False, False))
            self._a_down_at = None
            self._a_back_fired = False

        if a_pressed:
            self._cancel_b()
        elif dropdown_open:
            self._update_dropdown_b(b_pressed, now_ms)
        else:
            self._cancel_dropdown_b()
            self._update_navigation_b(b_pressed, direct_navigation_focused)

        self._a_pressed = a_pressed

        if self._events:
            return self._events.pop(0)
        if self._active_b_key is not None:
            return self._active_b_key, True, False
        return None, False, False

    def cancel(self):
        active_key = self._active_b_key
        self._a_pressed = False
        self._a_down_at = None
        self._a_back_fired = False
        self._active_b_key = None
        self._b_dropdown_pressed = False
        self._b_down_at = None
        self._b_previous_fired = False
        self._events = []
        return active_key

    def _update_dropdown_b(self, b_pressed, now_ms):
        # Delay B's action until release so a long press can use the same key for previous.
        if b_pressed and not self._b_dropdown_pressed:
            self._b_dropdown_pressed = True
            self._b_down_at = now_ms
            self._b_previous_fired = False
        elif b_pressed and not self._b_previous_fired:
            if self._ticks_diff(now_ms, self._b_down_at) >= self._long_press_ms:
                self._b_previous_fired = True
                self._events.append(("left", True, False))
                self._events.append(("left", False, False))
        elif not b_pressed and self._b_dropdown_pressed:
            if not self._b_previous_fired:
                self._events.append(("right", True, False))
                self._events.append(("right", False, False))
            self._cancel_dropdown_b()

    def _update_navigation_b(self, b_pressed, direct_navigation_focused):
        if b_pressed:
            desired_key = "right" if direct_navigation_focused else "next"
            if self._active_b_key != desired_key:
                self._release_b()
                self._active_b_key = desired_key
                self._events.append((desired_key, True, False))
        else:
            self._release_b()

    def _cancel_b(self):
        self._release_b()
        self._cancel_dropdown_b()

    def _cancel_dropdown_b(self):
        self._b_dropdown_pressed = False
        self._b_down_at = None
        self._b_previous_fired = False

    def _release_b(self):
        if self._active_b_key is not None:
            self._events.append((self._active_b_key, False, False))
            self._active_b_key = None
