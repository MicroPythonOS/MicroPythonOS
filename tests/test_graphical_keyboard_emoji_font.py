"""
Graphical tests for emoji input on MposKeyboard.

Checks that:
- Emoji keys exist on the specials keyboard layout
- Typing an emoji inserts it into the textarea
- Textarea font is switched to an emoji-capable composed font

Usage:
"""

import unittest
import lvgl as lv

from mpos import FontManager
from mpos.ui.testing import KeyboardTestCase


class TestGraphicalKeyboardEmojiFont(KeyboardTestCase):
    def test_typing_emoji_switches_textarea_font(self):
        keyboard, textarea = self.create_keyboard_scene(initial_text="")

        base_font = FontManager.getFont(size=16, family="Montserrat", emoji=False)
        textarea.set_style_text_font(base_font, lv.PART.MAIN)
        self.wait_for_render()

        before_font = textarea.get_style_text_font(lv.PART.MAIN)
        self.assertEqual(before_font.get_line_height(), base_font.get_line_height())

        keyboard.set_mode(keyboard.MODE_SPECIALS)
        self.wait_for_render()

        emoji_key = "🙂"
        emoji_found = False
        emoji_button_idx = None
        for i in range(100):
            text = keyboard.get_button_text(i)
            if text is None:
                break
            if text == emoji_key:
                emoji_found = True
                emoji_button_idx = i
                break
        self.assertTrue(emoji_found, "Expected emoji key not present in specials layout")

        clicked = self.click_keyboard_button(emoji_key)
        self.assertTrue(clicked, "Could not click emoji button")
        self.wait_for_render(20)

        self.assertTextareaText(emoji_key)
        self.assertTrue(keyboard._textarea_emoji_font_applied)

        after_font = textarea.get_style_text_font(lv.PART.MAIN)
        self.assertTrue(after_font.get_line_height() >= base_font.get_line_height())

        fallback_font = None
        try:
            fallback_font = after_font.fallback
        except Exception:
            fallback_font = None

        self.assertIsNotNone(fallback_font)
