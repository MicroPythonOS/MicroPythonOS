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

    def _widget_text(self, widget):
        """Return the text of a button's label child, or the label itself."""
        if isinstance(widget, lv.label):
            return widget.get_text()
        for i in range(widget.get_child_count()):
            child = widget.get_child(i)
            if isinstance(child, lv.label):
                return child.get_text()
        return None

    def _find_button(self, buttons, text):
        """Return the first widget whose text matches, or None."""
        for btn in buttons:
            if self._widget_text(btn) == text:
                return btn
        return None

    def _emulate_tap(self, btn):
        """Simulate a tap on a real button."""
        btn.send_event(lv.EVENT.CLICKED, None)
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
            emoji_found = any(
                any(isinstance(btn.get_child(i), lv.image) for i in range(btn.get_child_count()))
                for btn in keyboard._keys
            )
            self.assertTrue(emoji_found, "emoji key missing in %s mode" % name)

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

        # Open the emoji pane directly.
        keyboard._show_emoji_pane()
        self.wait_for_render(5)

        # The overlay should be visible and contain an Abc key and emoji buttons.
        abcd_btn = self._find_button(keyboard._emoji_buttons, "Abc")
        self.assertTrue(abcd_btn is not None, "Abc key not found in emoji pane")

        # Find the first real emoji button after Abc.
        emoji_btn = None
        for btn in keyboard._emoji_buttons:
            if btn is abcd_btn:
                continue
            text = self._widget_text(btn)
            if text and text != "Abc":
                emoji_btn = btn
                break
        self.assertTrue(emoji_btn is not None, "no emoji button found")
        emoji_text = self._widget_text(emoji_btn)

        self._emulate_tap(emoji_btn)
        self.assertTrue(emoji_text in textarea.get_text(), "emoji not inserted")

        # Close the pane via Abc.
        self._emulate_tap(abcd_btn)
        self.wait_for_render(5)
        self.assertTrue(keyboard._emoji_pane.has_flag(lv.obj.FLAG.HIDDEN), "emoji pane still visible")

    def test_emoji_pane_ok_key_closes(self):
        """The last OK key on the emoji pane closes it and returns to the keyboard."""
        textarea = lv.textarea(self.screen)
        textarea.set_size(280, 40)
        textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        # Use a multi-line textarea so the keyboard itself stays open.
        textarea.set_one_line(False)
        self.wait_for_render(5)

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self.wait_for_render(5)

        keyboard._show_emoji_pane()
        self.wait_for_render(5)

        ok_btn = self._find_button(keyboard._emoji_buttons, lv.SYMBOL.OK)
        self.assertTrue(ok_btn is not None, "OK key not found in emoji pane")

        self._emulate_tap(ok_btn)
        self.wait_for_render(5)

        self.assertTrue(keyboard._emoji_pane.has_flag(lv.obj.FLAG.HIDDEN), "emoji pane still visible after OK")

        group = lv.group_get_default()
        if not group:
            group = lv.group_create()
            group.set_default()
        self.wait_for_render(5)
        self.assertTrue(group.get_focused() in keyboard._keys, "focus not restored to keyboard after OK")

    def test_emoji_pane_redirects_focus(self):
        """Joystick/encoder focus moves to the emoji pane while it is visible."""
        textarea = lv.textarea(self.screen)
        textarea.set_size(280, 40)
        textarea.align(lv.ALIGN.TOP_MID, 0, 10)
        textarea.set_one_line(True)
        self.wait_for_render(5)

        keyboard = MposKeyboard(self.screen)
        keyboard.set_textarea(textarea)
        keyboard.align(lv.ALIGN.BOTTOM_MID, 0, 0)
        self.wait_for_render(5)

        group = lv.group_get_default()
        if not group:
            group = lv.group_create()
            group.set_default()

        keyboard.show_keyboard()
        self.wait_for_render(5)

        # With the emoji pane visible, focus should be on an emoji button.
        keyboard._show_emoji_pane()
        self.wait_for_render(5)
        focused = group.get_focused()
        self.assertTrue(
            focused in keyboard._emoji_buttons,
            "focus not on emoji pane: %s" % focused,
        )

        # Navigating the focus group must not land back on the keyboard keys.
        for _ in range(10):
            group.focus_next()
            self.assertTrue(
                group.get_focused() not in keyboard._keys,
                "focus leaked to keyboard keys while emoji pane is open",
            )

        # Exiting emoji mode should restore focus to a keyboard key.
        keyboard._hide_emoji_pane()
        self.wait_for_render(5)
        self.assertTrue(group.get_focused() in keyboard._keys, "focus not restored to keyboard")


if __name__ == "__main__":
    unittest.main()
