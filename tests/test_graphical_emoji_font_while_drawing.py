"""
An emoji font's image callback can run while LVGL is drawing: a textarea placeholder is never
measured beforehand, so its glyphs are first looked up mid-draw. Scaling an emoji image there
with a snapshot would wait for the draw that is running it, which never finishes.

Usage:
"""

import unittest
import lvgl as lv
from mpos import FontManager
from mpos.ui.testing import GraphicalTestCase


def _reset_emoji_caches():
    FontManager._composed_font_cache.clear()
    FontManager._emoji_src_lookup_cache.clear()
    FontManager._emoji_sequence_lookup_cache.clear()
    FontManager._imgfont_scaled_src_cache.clear()
    FontManager._imgfont_source_size_cache.clear()
    FontManager._imgfont_empty_src_cache.clear()


class TestEmojiFirstSeenWhileDrawing(GraphicalTestCase):

    def setUp(self):
        super().setUp()
        _reset_emoji_caches()

    def test_placeholder_with_an_unseen_emoji_renders(self):
        font = FontManager.getFont(size=16, emoji=True)
        ta = lv.textarea(self.screen)
        ta.set_size(300, 60)
        ta.set_style_text_font(font, lv.PART.MAIN)
        ta.set_placeholder_text("Message to Alex\U0001F4AA")
        self.wait_for_render(5)
        self.wait_for_render(5)
        sizes = [key[1] for key in FontManager._imgfont_scaled_src_cache]
        self.assertTrue(sizes, "the emoji was never scaled")

    def test_placeholder_with_several_unseen_emoji_renders(self):
        font = FontManager.getFont(size=16, emoji=True)
        ta = lv.textarea(self.screen)
        ta.set_size(300, 60)
        ta.set_style_text_font(font, lv.PART.MAIN)
        ta.set_placeholder_text("Hello \U0001F4AA\U0001F680")
        self.wait_for_render(5)
        self.wait_for_render(5)
        self.assertTrue(len(FontManager._imgfont_scaled_src_cache) >= 2,
                        "not all placeholder emoji were scaled")

    def test_label_with_an_unseen_emoji_renders(self):
        font = FontManager.getFont(size=16, emoji=True)
        label = lv.label(self.screen)
        label.set_style_text_font(font, lv.PART.MAIN)
        label.set_text("Hi \U0001F4AA")
        self.wait_for_render(5)
        self.assertTrue(FontManager._imgfont_scaled_src_cache,
                        "the label emoji was never scaled")


if __name__ == "__main__":
    unittest.main()
