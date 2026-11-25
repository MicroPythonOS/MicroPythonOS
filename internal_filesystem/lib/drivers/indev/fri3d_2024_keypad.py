"""Keypad driver for the Fri3d Camp 2024 badge's own buttons and joystick.

The face buttons, START/MENU and the two joystick ADC channels are separate
inputs, so several keys can be down at once - firing while walking is the
normal way to play. LVGL's keypad indev carries one key per read, so the board
used to report only the first one it found: holding B (fire) hid the joystick
completely. This driver queues the press and release of every change instead,
and reports the whole physically-held set through ``held_keys()``, so a game
with ``key_state`` keeps its direction and its fire down together.
"""

import lvgl as lv
import keypad_framework
import time
from micropython import const

import mpos.ui
import mpos.ui.focus_direction

LONG_PRESS_TIME = const(400)
LONG_PRESS_REPEAT_TIME = const(100)


class Fri3d2024Keypad(keypad_framework.KeypadDriver):
    """An LVGL keypad indev over a badge that can hold several keys.

    ``read_state()`` returns the keys that are down right now, in any order;
    the first one is the key that repeats while it stays held.
    """

    def __init__(self, read_state, group=None):
        super().__init__()
        self._read_state = read_state
        self._held = ()
        self._queue = []
        self._repeat_key = None
        self._repeat_start_ms = 0
        self._repeat_last_ms = 0
        self._repeat_enabled = True
        if group is not None:
            self.set_group(group)

    def held_keys(self):
        """Every key the badge reports as down (at most one read period old)."""
        return self._held

    def set_long_press_time(self, ms):
        """LVGL's own long press (a widget's LONG_PRESSED, e.g. the file
        explorer's pick) has to fire before the driver's first repeat: a repeat
        releases the key, which would cancel a long press still waiting."""
        self._indev_drv.set_long_press_time(ms)  # NOQA

    def set_repeat_enabled(self, enabled):
        """Stop synthesizing repeats while a game is in the foreground.

        A repeat is a typing affordance: a game wants one press and one
        release. It is re-enabled when the game pauses.
        """
        self._repeat_enabled = bool(enabled)
        if not self._repeat_enabled:
            self._reset_repeat()

    def _poll_state(self):
        state = tuple(self._read_state())
        previous = self._held
        self._held = state

        for key in state:
            if key not in previous:
                self._queue.append((self.PRESSED, key))
        for key in previous:
            if key not in state:
                self._queue.append((self.RELEASED, key))

        # The first held key is the one that repeats, as the badge did before:
        # holding right turns continuously while a walk continues.
        if state:
            first = state[0]
            if first != self._repeat_key:
                now = time.ticks_ms()
                self._repeat_key = first
                self._repeat_start_ms = now
                self._repeat_last_ms = now
        else:
            self._reset_repeat()

    def _reset_repeat(self):
        self._repeat_key = None
        self._repeat_start_ms = 0
        self._repeat_last_ms = 0

    def _maybe_enqueue_repeat(self):
        if not self._repeat_enabled or self._repeat_key is None:
            return
        if self._repeat_key not in self._held:
            self._reset_repeat()
            return
        now = time.ticks_ms()
        if time.ticks_diff(now, self._repeat_start_ms) < LONG_PRESS_TIME:
            return
        if time.ticks_diff(now, self._repeat_last_ms) < LONG_PRESS_REPEAT_TIME:
            return
        self._repeat_last_ms = now
        self._queue.append((self.PRESSED, self._repeat_key))
        self._queue.append((self.RELEASED, self._repeat_key))

    def _fire_nav_hook(self, state, key):
        if state != self.PRESSED:
            return
        if key == lv.KEY.ESC:
            mpos.ui.back_screen()
        elif key == lv.KEY.HOME:
            from mpos.ui import topmenu as topmenu
            topmenu.toggle_drawer()
        elif key == lv.KEY.RIGHT:
            mpos.ui.focus_direction.move_focus_direction(90)
        elif key == lv.KEY.LEFT:
            mpos.ui.focus_direction.move_focus_direction(270)
        elif key == lv.KEY.UP:
            mpos.ui.focus_direction.move_focus_direction(0)
        elif key == lv.KEY.DOWN:
            mpos.ui.focus_direction.move_focus_direction(180)

    def _get_key(self):
        self._poll_state()
        self._maybe_enqueue_repeat()
        if self._queue:
            state, key = self._queue.pop(0)
            self._fire_nav_hook(state, key)
            return state, key
        return None

    def _read(self, drv, data):  # NOQA
        key = self._get_key()

        if key is None:
            state = self.RELEASED
            key = self._last_key
        else:
            state, key = key

        data.key = self._last_key = key
        data.state = self._current_state = state
        data.continue_reading = bool(self._queue)
