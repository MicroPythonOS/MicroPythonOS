"""
Test that MposKeyboard only shows the NEW_LINE key for multi-line textareas.

Usage:
"""

import unittest
import lvgl as lv

from mpos import MposKeyboard
from mpos.ui.testing import GraphicalTestCase


class TestKeyboardNewlineKey(GraphicalTestCase):
    """Verify NEW_LINE key visibility based on textarea one_line state."""

    def _has_newline_key(self, keyboard):
        """Return True if the keyboard currently has a NEW_LINE key."""
        for i in range(100):
            try:
                text = keyboard.get_button_text(i)
                if text == lv.SYMBOL.NEW_LINE:
                    return True
            except Exception:
                pass
        return False

    def _assert_newline_state(self, keyboard, should_have_newline):
        """Helper to assert newline key state across all modes."""
        modes = [
            MposKeyboard.MODE_LOWERCASE,
            MposKeyboard.MODE_UPPERCASE,
            MposKeyboard.MODE_NUMBERS,
            MposKeyboard.MODE_SPECIALS,
        ]
        for mode in modes:
            keyboard.set_mode(mode)
            self.wait_for_render(5)
            found = self._has_newline_key(keyboard)
            if should_have_newline:
                self.assertTrue(found, "NEW_LINE key missing in mode %s" % mode)
            else:
                self.assertFalse(found, "NEW_LINE key should not appear in mode %s" % mode)

    def test_multiline_textarea_has_newline_key(self):
        """A multi-line textarea keeps the NEW_LINE key."""
        textarea = lv.textarea(self.screen)
        textarea.set_size(280, 80)
        textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        # textarea is multi-line by default
        self.wait_for_render(5)

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self.wait_for_render(5)

        self._assert_newline_state(keyboard, should_have_newline=True)

    def test_single_line_textarea_hides_newline_key(self):
        """A single-line textarea hides the NEW_LINE key."""
        textarea = lv.textarea(self.screen)
        textarea.set_size(280, 40)
        textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        textarea.set_one_line(True)
        self.wait_for_render(5)

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self.wait_for_render(5)

        self._assert_newline_state(keyboard, should_have_newline=False)


if __name__ == "__main__":
    unittest.main()
