class K10ButtonInput:
    def __init__(self, long_press_ms=700, ticks_diff=None):
        self._long_press_ms = long_press_ms
        self._ticks_diff = ticks_diff or (lambda current, previous: current - previous)
        self._a_pressed = False
        self._a_down_at = None
        self._a_back_fired = False
        self._active_b_key = None
        self._events = []

    def update(self, a_pressed, b_pressed, now_ms, keyboard_focused):
        if a_pressed and not self._a_pressed:
            self._a_down_at = now_ms
            self._a_back_fired = False
            self._release_b()

        if a_pressed and self._a_down_at is not None and not self._a_back_fired:
            if self._ticks_diff(now_ms, self._a_down_at) >= self._long_press_ms:
                self._a_back_fired = True
                self._events.append((None, False, True))

        if not a_pressed and self._a_pressed:
            if not self._a_back_fired:
                self._events.append(("enter", True, False))
                self._events.append(("enter", False, False))
            self._a_down_at = None
            self._a_back_fired = False

        if a_pressed:
            self._release_b()
        elif b_pressed:
            desired_key = "right" if keyboard_focused else "next"
            if self._active_b_key != desired_key:
                self._release_b()
                self._active_b_key = desired_key
                self._events.append((desired_key, True, False))
        else:
            self._release_b()

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
        self._events = []
        return active_key

    def _release_b(self):
        if self._active_b_key is not None:
            self._events.append((self._active_b_key, False, False))
            self._active_b_key = None
