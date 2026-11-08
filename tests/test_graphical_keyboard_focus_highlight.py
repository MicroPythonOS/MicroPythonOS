"""
test_graphical_keyboard_focus_highlight.py - The selected keyboard key must be
highlighted for keypad/joystick users.

Issue #274: with physical buttons there was no visible highlight on the
keyboard, so the user could not see which key was selected. LVGL only draws
the highlight for LV_STATE_FOCUS_KEY, which is set when focus arrives from a
keypad/encoder indev. MposKeyboard focuses itself programmatically when it is
shown, so the state was never set.

Usage:
    python3 scripts/test_runner.py tests/test_graphical_keyboard_focus_highlight.py
"""

import unittest

import lvgl as lv

import mpos.ui.focus as focus_module
from mpos.ui.testing import KeyboardTestCase


class TestKeyboardFocusHighlight(KeyboardTestCase):
    def setUp(self):
        super().setUp()
        self._saved_nav_active = focus_module._focus_nav_active
        focus_module._focus_nav_active = False

    def tearDown(self):
        focus_module._focus_nav_active = self._saved_nav_active
        super().tearDown()

    def _keyboard_has_focus_highlight(self):
        return bool(self.keyboard._keyboard.get_state() & lv.STATE.FOCUS_KEY)

    def test_show_keyboard_highlights_selection_for_button_users(self):
        keyboard, _ = self.create_keyboard_scene()

        # The user has navigated with direction keys before opening the field.
        focus_module.enable_focus_borders()
        keyboard.show_keyboard()
        self.wait_for_render(20)

        self.assertTrue(
            self._keyboard_has_focus_highlight(),
            "keypad users must see which keyboard key is selected",
        )

    def test_show_keyboard_has_no_highlight_in_touch_only_use(self):
        keyboard, _ = self.create_keyboard_scene()

        keyboard.show_keyboard()
        self.wait_for_render(20)

        self.assertFalse(
            self._keyboard_has_focus_highlight(),
            "touch users must not get a permanent key highlight",
        )

    def test_direction_navigation_reveals_keyboard_highlight(self):
        keyboard, _ = self.create_keyboard_scene()

        # Keyboard shown by touch: no highlight yet.
        keyboard.show_keyboard()
        self.wait_for_render(20)
        self.assertFalse(self._keyboard_has_focus_highlight())

        # The first direction press goes to the keyboard's own navigation.
        lv.group_focus_obj(keyboard._keyboard)
        from mpos.ui.focus_direction import move_focus_direction
        move_focus_direction(90)
        self.wait_for_render(10)

        self.assertTrue(
            self._keyboard_has_focus_highlight(),
            "navigating with direction keys must reveal the selected key",
        )


if __name__ == "__main__":
    unittest.main()
