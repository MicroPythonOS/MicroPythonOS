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

    def _find_button(self, keyboard, text):
        """Return the keyboard key button whose label text equals `text`."""
        for btn in keyboard._keys:
            if self._button_text(btn) == text:
                return btn
        return None

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

    def _check_ok_hides_keyboard(self, one_line, should_hide):
        """Pressing OK on a single-line textarea hides the keyboard."""
        textarea = lv.textarea(self.screen)
        textarea.set_size(280, 40)
        textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        textarea.set_one_line(one_line)
        self.wait_for_render(5)

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        keyboard.show_keyboard()
        self.wait_for_render(10)

        ok_btn = self._find_button(keyboard, lv.SYMBOL.OK)
        self.assertTrue(ok_btn is not None)
        ok_btn.send_event(lv.EVENT.CLICKED, None)

        is_hidden = False
        for _ in range(80):
            self.wait_for_render(5)
            if keyboard.has_flag(lv.obj.FLAG.HIDDEN):
                is_hidden = True
                break
        if should_hide:
            self.assertTrue(is_hidden, "OK should hide the keyboard for single-line textarea")
        else:
            self.assertFalse(is_hidden, "OK should not hide the keyboard for multi-line textarea")

    def test_ok_hides_keyboard_for_single_line(self):
        """Pressing the OK key closes the keyboard for a single-line textarea."""
        self._check_ok_hides_keyboard(one_line=True, should_hide=True)

    def test_ok_does_not_hide_keyboard_for_multiline(self):
        """Pressing the OK key leaves the keyboard open for a multi-line textarea."""
        self._check_ok_hides_keyboard(one_line=False, should_hide=False)


if __name__ == "__main__":
    unittest.main()
