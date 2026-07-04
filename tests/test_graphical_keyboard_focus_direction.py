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
        # Clean up stale buttonmatrix instances left in the default group by
        # earlier runs so directional navigation targets only this keyboard.
        # Stale keyboard matrices from previous tests can confuse focus
        # direction; remove them and wait until this keyboard is the focused
        # object in the default group before navigating.
        stale = [group.get_obj_by_index(i) for i in range(group.get_obj_count())
                 if isinstance(group.get_obj_by_index(i), lv.buttonmatrix)]
        for obj in stale:
            lv.group_remove_obj(obj)
        group.add_obj(keyboard._keyboard)
        lv.group_focus_obj(keyboard._keyboard)
        keyboard._keyboard.set_selected_button(0)

        for _ in range(30):
            if (group.get_focused() is keyboard._keyboard
                    and self._selected_text(keyboard) == "q"):
                break
            self.wait_for_render(5)
        else:
            actual_focus = group.get_focused()
            actual_text = self._selected_text(keyboard)
            self.fail("keyboard not focused/selected: focus=%s text=%r" % (actual_focus, actual_text))
        return keyboard

    def _selected_text(self, keyboard):
        idx = keyboard._keyboard.get_selected_button()
        if idx is None:
            return None
        try:
            return keyboard._keyboard.get_button_text(idx)
        except Exception:
            return None

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
        self.assertFalse(
            keyboard._keyboard_indicator.has_flag(lv.obj.FLAG.HIDDEN),
            "keyboard focus indicator should be visible",
        )

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


if __name__ == "__main__":
    unittest.main()
