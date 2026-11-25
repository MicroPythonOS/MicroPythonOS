"""The fri3d 2024 badge can hold several keys at once.

Its face buttons, START/MENU and the joystick are separate inputs, so a player
fires with B while walking with the stick. The board used to report only the
first key it found, which made the joystick dead while any button was down.
"""

import time
import unittest

import lvgl as lv

import mpos.ui.focus_direction as focus_direction
from mpos import InputManager
from drivers.indev.fri3d_2024_keypad import (
    LONG_PRESS_REPEAT_TIME,
    LONG_PRESS_TIME,
    Fri3d2024Keypad,
)


class TestFri3d2024Keypad(unittest.TestCase):

    def setUp(self):
        self.keys = []
        self.moves = []
        self._real_move = focus_direction.move_focus_direction
        focus_direction.move_focus_direction = self.moves.append
        self.keypad = Fri3d2024Keypad(lambda: list(self.keys))

    def tearDown(self):
        focus_direction.move_focus_direction = self._real_move

    def _press(self, *keys):
        self.keys = list(keys)

    def _next(self):
        return self.keypad._get_key()

    def _age_repeat(self):
        """Move the long-press deadline far enough back to be due."""
        now = time.ticks_ms()
        self.keypad._repeat_start_ms = time.ticks_add(now, -LONG_PRESS_TIME - 1)
        self.keypad._repeat_last_ms = time.ticks_add(
            now, -LONG_PRESS_REPEAT_TIME - 1)

    def test_a_button_does_not_hide_the_joystick(self):
        # The report that started this: B held, then the stick pushed.
        self._press(ord("B"))
        self.assertEqual(self._next(), (lv.INDEV_STATE.PRESSED, ord("B")))
        self.assertEqual(self.keypad.held_keys(), (ord("B"),))

        self._press(ord("B"), lv.KEY.RIGHT)
        self.assertEqual(self._next(), (lv.INDEV_STATE.PRESSED, lv.KEY.RIGHT))
        self.assertEqual(self.keypad.held_keys(), (ord("B"), lv.KEY.RIGHT))
        self.assertEqual(self.moves, [90], "the stick did not turn")

        # Lifting the stick leaves fire down.
        self._press(ord("B"))
        self.assertEqual(self._next(), (lv.INDEV_STATE.RELEASED, lv.KEY.RIGHT))
        self.assertEqual(self.keypad.held_keys(), (ord("B"),))

    def test_a_held_key_is_not_pressed_again(self):
        self._press(ord("B"))
        self.assertEqual(self._next(), (lv.INDEV_STATE.PRESSED, ord("B")))
        # The same state on the next read is not an event.
        self.assertIsNone(self._next())

    def test_the_first_key_repeats_until_it_is_let_go(self):
        self._press(lv.KEY.DOWN)
        self._next()
        del self.moves[:]
        self._age_repeat()
        self.assertEqual(self._next(), (lv.INDEV_STATE.PRESSED, lv.KEY.DOWN))
        self.assertEqual(self._next(), (lv.INDEV_STATE.RELEASED, lv.KEY.DOWN))
        self.assertEqual(self.moves, [180])

    def test_the_framework_sees_every_held_key(self):
        # This is what a game with key_state polls once a frame: the source of
        # KeyHolds' held state. Both keys have to be in it.
        InputManager.register_indev(self.keypad)
        try:
            self._press(ord("B"), lv.KEY.RIGHT)
            self.keypad._get_key()
            held = InputManager.held_keys()
            self.assertTrue(held is not None)
            self.assertIn(ord("B"), held)
            self.assertIn(lv.KEY.RIGHT, held)
        finally:
            InputManager.unregister_indev(self.keypad)

    def test_a_game_turns_the_repeats_off(self):
        # Doom and Duke hold a key for as long as it is physically down; the
        # typing repeat would press it again behind their back.
        self.keypad.set_repeat_enabled(False)
        self._press(lv.KEY.DOWN)
        self._next()
        self._age_repeat()
        self.assertIsNone(self._next())
        # The state is still reported, so the game keeps the key down.
        self.assertEqual(self.keypad.held_keys(), (lv.KEY.DOWN,))


if __name__ == "__main__":
    unittest.main()
