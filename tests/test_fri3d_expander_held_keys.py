"""The fri3d 2026 expander's held-key table.

A keypad press reaches an app as one event and LVGL never sends the release,
so a game used to keep the key down on a timer. The expander already reads the
physical state on every input read, and ``held_keys()`` exposes it without any
extra bus traffic.
"""

import unittest

import lvgl as lv

from drivers.indev.fri3d_2026_expander import (
    held_keys_from_digital, Fri3d2026Expander)


def digital(right=False, left=False, down=False, up=False, menu=False,
            b=False, a=False, y=False, x=False):
    # usb_plugged, joy_right, joy_left, joy_down, joy_up, button_menu,
    # button_b, button_a, button_y, button_x, charger_standby, charger_charging
    return (False, right, left, down, up, menu, b, a, y, x, False, False)


class TestHeldKeys(unittest.TestCase):

    def test_nothing_pressed(self):
        self.assertEqual(held_keys_from_digital(digital()), ())

    def test_an_unread_expander_reports_nothing(self):
        self.assertEqual(held_keys_from_digital(None), ())

    def test_joystick_directions(self):
        self.assertEqual(
            held_keys_from_digital(digital(left=True)), (lv.KEY.LEFT,))
        self.assertEqual(
            held_keys_from_digital(digital(right=True)), (lv.KEY.RIGHT,))
        self.assertEqual(
            held_keys_from_digital(digital(up=True)), (lv.KEY.UP,))
        self.assertEqual(
            held_keys_from_digital(digital(down=True)), (lv.KEY.DOWN,))

    def test_buttons_use_the_codes_the_app_receives(self):
        # B and Y are dual-delivered as letters next to NEXT/PREV, and a game
        # maps the letter.
        self.assertEqual(held_keys_from_digital(digital(b=True)), (ord("B"),))
        self.assertEqual(held_keys_from_digital(digital(y=True)), (ord("Y"),))
        self.assertEqual(held_keys_from_digital(digital(x=True)), (lv.KEY.ESC,))
        self.assertEqual(
            held_keys_from_digital(digital(menu=True)), (lv.KEY.HOME,))

    def test_the_a_button_is_enter_and_the_letter(self):
        self.assertEqual(
            held_keys_from_digital(digital(a=True)),
            (lv.KEY.ENTER, ord("A")))

    def test_a_diagonal_reports_both_directions(self):
        self.assertEqual(
            held_keys_from_digital(digital(right=True, up=True)),
            (lv.KEY.RIGHT, lv.KEY.UP))


class TestRepeatSwitch(unittest.TestCase):

    def test_disabling_repeats_forgets_a_repeat_in_progress(self):
        driver = object.__new__(Fri3d2026Expander)
        driver._repeat_enabled = True
        driver._repeat_idx = 4
        driver._repeat_start_ms = 1
        driver._repeat_last_emit_ms = 2
        driver.set_repeat_enabled(False)
        self.assertFalse(driver._repeat_enabled)
        self.assertIsNone(driver._repeat_idx)
        driver.set_repeat_enabled(True)
        self.assertTrue(driver._repeat_enabled)
