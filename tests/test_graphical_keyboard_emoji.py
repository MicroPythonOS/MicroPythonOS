"""
Test MposKeyboard emoji pane.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_keyboard_emoji.py
"""

import unittest
import lvgl as lv

from mpos import MposKeyboard
from mpos.ui.testing import GraphicalTestCase


class TestKeyboardEmoji(GraphicalTestCase):
    """Verify the emoji overlay pane behaves as expected."""

    def _button_index_by_text(self, widget, text):
        """Return the first button index whose text matches, or -1."""
        for i in range(100):
            try:
                if widget.get_button_text(i) == text:
                    return i
            except Exception:
                pass
        return -1

    def _emulate_tap(self, btnmatrix, button_index):
        """Tap a button by setting it selected and firing VALUE_CHANGED."""
        btnmatrix.set_selected_button(button_index)
        btnmatrix.send_event(lv.EVENT.VALUE_CHANGED, None)
        self.wait_for_render(5)

    def test_numbers_and_specials_show_emoji_key(self):
        """The emoji label appears in numbers and specials modes."""
        textarea = lv.textarea(self.screen)
        textarea.set_size(280, 40)
        textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        textarea.set_one_line(True)
        self.wait_for_render(5)

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self.wait_for_render(5)

        for mode, name in (
            (MposKeyboard.MODE_NUMBERS, "numbers"),
            (MposKeyboard.MODE_SPECIALS, "specials"),
        ):
            keyboard.set_mode(mode)
            self.wait_for_render(5)
            idx = self._button_index_by_text(keyboard, "emoji")
            self.assertTrue(idx >= 0, "emoji label missing in %s mode" % name)

    def test_emoji_pane_inserts_and_closes(self):
        """The emoji pane inserts emojis and closes via Abc."""
        textarea = lv.textarea(self.screen)
        textarea.set_size(280, 40)
        textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        textarea.set_one_line(True)
        self.wait_for_render(5)

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self.wait_for_render(5)

        # Open the emoji pane directly (overlay tap simulation).
        keyboard._show_emoji_pane()
        self.wait_for_render(5)

        # The overlay should be visible and contain an Abc key and emoji buttons.
        abcd_idx = self._button_index_by_text(keyboard._emoji_buttons, "Abc")
        self.assertTrue(abcd_idx >= 0, "Abc key not found in emoji pane")

        # Find the first real emoji button after Abc.
        emoji_button_idx = abcd_idx + 1
        self.assertTrue(emoji_button_idx >= 0, "no emoji button found")
        emoji_text = keyboard._emoji_buttons.get_button_text(emoji_button_idx)
        self.assertTrue(emoji_text and emoji_text != "Abc", "invalid emoji text")

        self._emulate_tap(keyboard._emoji_buttons, emoji_button_idx)
        self.assertTrue(emoji_text in textarea.get_text(), "emoji not inserted")

        # Close the pane via Abc.
        self._emulate_tap(keyboard._emoji_buttons, abcd_idx)
        self.wait_for_render(5)
        self.assertTrue(keyboard._emoji_pane.has_flag(lv.obj.FLAG.HIDDEN), "emoji pane still visible")


if __name__ == "__main__":
    unittest.main()
