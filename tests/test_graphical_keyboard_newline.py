"""
Test MposKeyboard newline key visibility for single and multi-line textareas.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_keyboard_newline.py
"""

import unittest
import lvgl as lv

from mpos import MposKeyboard
from mpos.ui.testing import GraphicalTestCase


class TestKeyboardNewlineKey(GraphicalTestCase):
    """Verify the newline key appears only for multi-line textareas."""

    def _button_text(self, btn):
        """Return the text of a key button's label child."""
        for i in range(btn.get_child_count()):
            child = btn.get_child(i)
            if isinstance(child, lv.label):
                return child.get_text()
        return None

    def _has_newline_key(self, keyboard):
        """Return True if the current keyboard layout contains a NEW_LINE key."""
        for btn in keyboard._keys:
            if self._button_text(btn) == lv.SYMBOL.NEW_LINE:
                return True
        return False

    def _check_newline_for_textarea(self, one_line, should_exist):
        """Create a keyboard for a textarea and check NEW_LINE presence across modes."""
        textarea = lv.textarea(self.screen)
        textarea.set_size(280, 40)
        textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        textarea.set_one_line(one_line)
        self.wait_for_render(5)

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self.wait_for_render(5)

        modes = [
            keyboard.MODE_LOWERCASE,
            keyboard.MODE_UPPERCASE,
            keyboard.MODE_NUMBERS,
            keyboard.MODE_SPECIALS,
        ]
        for mode in modes:
            keyboard.set_mode(mode)
            self.wait_for_render(5)
            if should_exist:
                self.assertTrue(
                    self._has_newline_key(keyboard),
                    "NEW_LINE key missing in mode %s" % mode,
                )
            else:
                self.assertFalse(
                    self._has_newline_key(keyboard),
                    "NEW_LINE key should be hidden in mode %s" % mode,
                )

    def test_multiline_textarea_has_newline_key(self):
        """A multi-line textarea should show the NEW_LINE key in every mode."""
        self._check_newline_for_textarea(one_line=False, should_exist=True)

    def test_single_line_textarea_hides_newline_key(self):
        """A single-line textarea should hide the NEW_LINE key in every mode."""
        self._check_newline_for_textarea(one_line=True, should_exist=False)


if __name__ == "__main__":
    unittest.main()
