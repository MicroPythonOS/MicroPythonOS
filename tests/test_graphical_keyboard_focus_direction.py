"""
Test MposKeyboard integration with focus_direction.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_keyboard_focus_direction.py
"""

import unittest
import lvgl as lv

from mpos import MposKeyboard
from mpos.ui import focus_direction
from mpos.ui.testing import GraphicalTestCase


class TestKeyboardFocusDirection(GraphicalTestCase):
    """Verify keyboard keys are navigated as individual focus candidates."""

    def _button_text(self, btn):
        """Return the text of a key button's label child."""
        for i in range(btn.get_child_count()):
            child = btn.get_child(i)
            if isinstance(child, lv.label):
                return child.get_text()
        return None

    def _find_button(self, keyboard, text):
        """Return the keyboard key button whose label text equals `text`."""
        for btn in keyboard._keys:
            if self._button_text(btn) == text:
                return btn
        return None

    def _prepare_keyboard(self):
        """Create and focus a lowercase MposKeyboard, return it."""
        textarea = lv.textarea(self.screen)
        textarea.set_size(280, 40)
        textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        textarea.set_one_line(True)
        self.wait_for_render(10)

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self.wait_for_render(10)

        group = lv.group_get_default()
        if not group:
            group = lv.group_create()
            group.set_default()
        # Remove stale objects so directional navigation targets only this keyboard.
        group.remove_all_objs()
        for btn in keyboard._keys:
            group.add_obj(btn)
        lv.group_focus_obj(keyboard._keys[0])

        for _ in range(30):
            if (group.get_focused() is keyboard._keys[0]
                    and self._selected_text(keyboard) == "q"):
                break
            self.wait_for_render(5)
        else:
            actual_focus = group.get_focused()
            actual_text = self._selected_text(keyboard)
            self.fail("keyboard not focused/selected: focus=%s text=%r" % (actual_focus, actual_text))
        return keyboard

    def _selected_text(self, keyboard):
        group = lv.group_get_default()
        if not group:
            return None
        btn = group.get_focused()
        if btn not in keyboard._keys and btn not in keyboard._emoji_buttons:
            return None
        return self._button_text(btn)

    def _wait_for_selected(self, keyboard, text, max_attempts=30):
        for _ in range(max_attempts):
            if self._selected_text(keyboard) == text:
                return
            self.wait_for_render(5)
        actual = self._selected_text(keyboard)
        self.fail("expected selected key %r, got %r" % (text, actual))

    def _move_and_expect(self, keyboard, direction, expected_text):
        focus_direction.move_focus_direction(direction)
        self._wait_for_selected(keyboard, expected_text)

    def test_horizontal_navigation_does_not_skip(self):
        """Moving right/left visits every key on the top row in order."""
        keyboard = self._prepare_keyboard()

        expected = ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"]
        for expected_text in expected[1:]:
            self._move_and_expect(keyboard, 90, expected_text)

        for expected_text in reversed(expected[:-1]):
            self._move_and_expect(keyboard, 270, expected_text)

    def test_vertical_navigation_does_not_skip(self):
        """Moving down/up lands on the key directly below/above."""
        keyboard = self._prepare_keyboard()

        # From q, right once to w, then down to s.
        self._move_and_expect(keyboard, 90, "w")
        self._move_and_expect(keyboard, 180, "s")

        # From s, right to d, then up back to e.
        self._move_and_expect(keyboard, 90, "d")
        self._move_and_expect(keyboard, 0, "e")

        # From e, down to d.
        self._move_and_expect(keyboard, 180, "d")

    def test_diagonal_bias_does_not_skip_rows(self):
        """A mixed sequence keeps one-key-at-a-time movement."""
        keyboard = self._prepare_keyboard()

        for key in ("w", "e"):
            self._move_and_expect(keyboard, 90, key)

        self._move_and_expect(keyboard, 180, "d")
        self._move_and_expect(keyboard, 270, "s")
        self._move_and_expect(keyboard, 270, "a")

    def test_mode_switch_keeps_focus_nearby(self):
        """Switching modes preserves focus near the same on-screen position."""
        keyboard = self._prepare_keyboard()

        # Direct set_mode() should focus the corresponding key at the same spot.
        g_btn = self._find_button(keyboard, "g")
        self.assertTrue(g_btn is not None)
        lv.group_focus_obj(g_btn)
        self._wait_for_selected(keyboard, "g")
        keyboard.set_mode(keyboard.MODE_UPPERCASE)
        self._wait_for_selected(keyboard, "G")

        # Switching back via the mode-switch key lands on the matching key.
        down_btn = self._find_button(keyboard, lv.SYMBOL.DOWN)
        self.assertTrue(down_btn is not None)
        lv.group_focus_obj(down_btn)
        self._wait_for_selected(keyboard, lv.SYMBOL.DOWN)
        down_btn.send_event(lv.EVENT.CLICKED, None)
        self._wait_for_selected(keyboard, lv.SYMBOL.UP)


if __name__ == "__main__":
    unittest.main()
