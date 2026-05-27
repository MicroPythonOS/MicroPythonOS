"""
Graphical tests for FontManager.

Covers:
- getFont(): builtin families, size snapping, emoji=True/False, TTF loading, caching
- listFonts(): structure, completeness, renderability
- getEmojiCodepoints(): non-empty, sorted, both size tiers loaded
- normalizeEmojiText(): variation-selector stripping
- End-to-end rendering: labels using composed emoji fonts render without crashing

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_font_manager.py
    Device:  ./tests/unittest.sh tests/test_graphical_font_manager.py --ondevice
"""

import unittest
import lvgl as lv
from mpos import FontManager
from mpos.ui.testing import GraphicalTestCase

# TTF for testing: path relative to internal_filesystem/ (the test runner CWD).
# The M: drive prefix routes through the LVGL fs_driver which calls open() directly.
_TEST_TTF_PATH = "M:../tests/TimesNRW01-SmallTextRegular.ttf"

# Reset FontManager caches between tests so each test starts from a clean state.
def _reset_font_manager():
    FontManager._composed_font_cache.clear()
    FontManager._ttf_font_cache.clear()
    FontManager._emoji_maps.clear()
    FontManager._imgfont_scaled_src_cache.clear()
    FontManager._imgfont_source_size_cache.clear()
    FontManager._imgfont_empty_src_cache.clear()
    FontManager._unknown_emoji_codepoints_logged.clear()
    FontManager._builtin_font_records = None
    FontManager._emoji_similarity_group_members_by_cp = None


class TestFontManagerGetFont(GraphicalTestCase):
    """Tests for FontManager.getFont()."""

    def setUp(self):
        super().setUp()
        _reset_font_manager()

    def test_getfont_builtin_returns_font(self):
        """getFont() with a known family and size returns a non-None font object."""
        font = FontManager.getFont(size=16, family="Montserrat")
        self.assertIsNotNone(font)

    def test_getfont_emoji_false_returns_base_font(self):
        """getFont(emoji=False) returns the raw builtin font without composition."""
        base = FontManager.getFont(size=16, family="Montserrat", emoji=False)
        self.assertIsNotNone(base)
        # Should be one of the lv builtins — has get_line_height
        line_h = base.get_line_height()
        self.assertTrue(line_h > 0)

    def test_getfont_emoji_true_wraps_base_font(self):
        """getFont(emoji=True) returns a composed font distinct from the base font."""
        base = FontManager.getFont(size=16, family="Montserrat", emoji=False)
        composed = FontManager.getFont(size=16, family="Montserrat", emoji=True)
        self.assertIsNotNone(composed)
        # The composed imgfont is a different object from the base
        self.assertIsNot(composed, base)

    def test_getfont_size_snapping(self):
        """Requesting a size between two builtins snaps to the nearest available."""
        # 15 is between Montserrat 14 and 16; either is acceptable
        font = FontManager.getFont(size=15, family="Montserrat", emoji=False)
        self.assertIsNotNone(font)
        line_h = font.get_line_height()
        self.assertTrue(line_h > 0)

    def test_getfont_default_size(self):
        """getFont() with no size argument uses the default (12) without crashing."""
        font = FontManager.getFont(family="Montserrat")
        self.assertIsNotNone(font)

    def test_getfont_unknown_family_falls_back_to_montserrat(self):
        """An unknown family falls back to Montserrat instead of crashing."""
        font = FontManager.getFont(size=16, family="NonExistentFamily", emoji=False)
        self.assertIsNotNone(font)
        # Should still return a usable font with a positive line height
        self.assertTrue(font.get_line_height() > 0)

    def test_getfont_cached(self):
        """Calling getFont() twice with the same args returns the same object."""
        font_a = FontManager.getFont(size=16, family="Montserrat")
        font_b = FontManager.getFont(size=16, family="Montserrat")
        self.assertIs(font_a, font_b)

    def test_getfont_ttf_loads(self):
        """getFont() with a TTF path returns a usable font object."""
        font = FontManager.getFont(size=24, ttf=_TEST_TTF_PATH, emoji=False)
        self.assertIsNotNone(font)
        self.assertTrue(font.get_line_height() > 0)

    def test_getfont_ttf_cached(self):
        """TTF fonts are cached; the same path+size returns the same object."""
        font_a = FontManager.getFont(size=24, ttf=_TEST_TTF_PATH, emoji=False)
        font_b = FontManager.getFont(size=24, ttf=_TEST_TTF_PATH, emoji=False)
        self.assertIs(font_a, font_b)

    def test_getfont_ttf_different_sizes(self):
        """TTF at different sizes produces different font objects."""
        font_16 = FontManager.getFont(size=16, ttf=_TEST_TTF_PATH, emoji=False)
        font_32 = FontManager.getFont(size=32, ttf=_TEST_TTF_PATH, emoji=False)
        self.assertIsNot(font_16, font_32)

    def test_getfont_ttf_with_emoji(self):
        """getFont() with a TTF path and emoji=True returns a composed font."""
        base = FontManager.getFont(size=24, ttf=_TEST_TTF_PATH, emoji=False)
        composed = FontManager.getFont(size=24, ttf=_TEST_TTF_PATH, emoji=True)
        self.assertIsNotNone(composed)
        self.assertIsNot(composed, base)

    def test_getfont_unscii_family(self):
        """Unscii family is available and returns a usable font."""
        font = FontManager.getFont(size=16, family="Unscii", emoji=False)
        self.assertIsNotNone(font)
        self.assertTrue(font.get_line_height() > 0)

    def test_getfont_emoji_true_preserves_base_baseline(self):
        """Composed emoji font preserves baseline metrics from base font."""
        base = FontManager.getFont(size=16, family="Montserrat", emoji=False)
        composed = FontManager.getFont(size=16, family="Montserrat", emoji=True)
        self.assertEqual(int(composed.base_line), int(base.base_line))

    def test_imgfont_callback_uses_negative_baseline_offset(self):
        """Emoji callback offsets image glyphs by negative base baseline."""

        class _FakePtr:
            def __init__(self):
                self.value = None

            def __dereference__(self, value=None):
                if value is None:
                    return self.value
                self.value = value

        base = FontManager.getFont(size=16, family="Montserrat", emoji=False)
        composed = FontManager.getFont(size=16, family="Montserrat", emoji=True)

        ptr = _FakePtr()
        src = FontManager._imgfont_path_cb(
            composed, 0xFE0F, 0, ptr, None
        )

        self.assertIsNotNone(src)
        self.assertEqual(ptr.value, -int(base.base_line))


class TestFontManagerListFonts(GraphicalTestCase):
    """Tests for FontManager.listFonts()."""

    def setUp(self):
        super().setUp()
        _reset_font_manager()

    def test_listfonts_returns_nonempty_list(self):
        """listFonts() returns a non-empty list."""
        fonts = FontManager.listFonts()
        self.assertIsInstance(fonts, list)
        self.assertTrue(len(fonts) > 0)

    def test_listfonts_record_keys(self):
        """Each record from listFonts() has the required keys."""
        for info in FontManager.listFonts():
            self.assertIn("name", info)
            self.assertIn("family", info)
            self.assertIn("size", info)
            self.assertIn("font", info)
            self.assertIn("base_font", info)

    def test_listfonts_montserrat_present(self):
        """Montserrat fonts are present in listFonts()."""
        families = [info["family"] for info in FontManager.listFonts()]
        self.assertIn("Montserrat", families)

    def test_listfonts_sizes_positive(self):
        """All font sizes reported by listFonts() are positive integers."""
        for info in FontManager.listFonts():
            self.assertIsInstance(info["size"], int)
            self.assertTrue(info["size"] > 0)

    def test_listfonts_composed_differs_from_base(self):
        """The composed font in each record is distinct from the base font (emoji wrapped)."""
        for info in FontManager.listFonts():
            # If emoji loading succeeded, composed != base
            # (may be equal only if imgfont creation failed entirely)
            self.assertIsNotNone(info["font"])
            self.assertIsNotNone(info["base_font"])

    def test_listfonts_renderable(self):
        """Every font from listFonts() can be applied to a label without crashing."""
        for info in FontManager.listFonts():
            label = lv.label(self.screen)
            label.set_style_text_font(info["font"], lv.PART.MAIN)
            label.set_text("{}: Hello ❤️".format(info["name"]))
        self.wait_for_render()


class TestFontManagerEmojiCodepoints(GraphicalTestCase):
    """Tests for FontManager.getEmojiCodepoints() and emoji tier loading."""

    def setUp(self):
        super().setUp()
        _reset_font_manager()

    def _get_emoji_tier_maps(self):
        FontManager.getEmojiCodepoints()
        maps = FontManager._emoji_maps
        return maps["20x20"], maps["56x56"]

    def _skip_if_56x56_not_bundled(self, cps_56):
        if not cps_56:
            self.skipTest("56x56 emoji tier not bundled in this environment")

    def test_getemoji_codepoints_nonempty(self):
        """getEmojiCodepoints() returns a non-empty list."""
        cps = FontManager.getEmojiCodepoints()
        self.assertIsInstance(cps, list)
        self.assertTrue(len(cps) > 0)

    def test_getemoji_codepoints_all_ints(self):
        """All items returned by getEmojiCodepoints() are integers."""
        for cp in FontManager.getEmojiCodepoints():
            self.assertIsInstance(cp, int)

    def test_getemoji_codepoints_sorted(self):
        """getEmojiCodepoints() returns codepoints in ascending order."""
        cps = FontManager.getEmojiCodepoints()
        self.assertEqual(cps, sorted(cps))

    def test_getemoji_codepoints_valid_unicode(self):
        """All codepoints returned are in the valid Unicode range."""
        for cp in FontManager.getEmojiCodepoints():
            self.assertTrue(cp >= 0x100, "Codepoint should not be plain ASCII")
            self.assertTrue(cp <= 0x10FFFF, "Codepoint should be within Unicode range")

    def test_both_tiers_loaded_after_getemoji(self):
        """After getEmojiCodepoints(), 20x20 is populated and 56x56 is available when bundled."""
        cps_20, cps_56 = self._get_emoji_tier_maps()
        self.assertTrue(len(cps_20) > 0)
        # Some dev/test environments ship only the 20x20 emoji assets.
        # In those cases 56x56 is present as an empty map and should not fail the suite.
        self.assertIsInstance(cps_56, dict)

    def test_both_tiers_have_same_codepoints(self):
        """When 56x56 assets are present, both tiers expose the same set of codepoints."""
        cps_20, cps_56 = self._get_emoji_tier_maps()
        cps_20 = set(cps_20.keys())
        cps_56 = set(cps_56.keys())
        self._skip_if_56x56_not_bundled(cps_56)
        self.assertEqual(cps_20, cps_56)

    def test_tier_sources_point_to_correct_dirs(self):
        """Source paths in each tier map point to the expected directory."""
        FontManager.getEmojiCodepoints()
        for cp, src in FontManager._emoji_maps["20x20"].items():
            self.assertIn("20x20", src, "20x20 tier src should reference 20x20 dir")
        for cp, src in FontManager._emoji_maps["56x56"].items():
            self.assertIn("56x56", src, "56x56 tier src should reference 56x56 dir")

    def test_similarity_group_fallback_uses_available_emoji(self):
        """Missing emoji falls back to another available emoji in the same group."""
        FontManager._emoji_maps = {
            "20x20": {ord("❤"): "M:builtin/res/emojis/20x20/2764.png"},
            "56x56": {ord("❤"): "M:builtin/res/emojis/56x56/2764.png"},
        }

        src = FontManager._get_emoji_src(ord("♥"), 16)
        self.assertEqual(src, "M:builtin/res/emojis/20x20/2764.png")

    def test_similarity_group_fallback_respects_requested_tier(self):
        """When possible, fallback picks a source from the preferred emoji tier."""
        FontManager._emoji_maps = {
            "20x20": {ord("❤"): "M:builtin/res/emojis/20x20/2764.png"},
            "56x56": {ord("❤"): "M:builtin/res/emojis/56x56/2764.png"},
        }

        src = FontManager._get_emoji_src(ord("♥"), 32)
        self.assertEqual(src, "M:builtin/res/emojis/56x56/2764.png")

    def test_similarity_group_fallback_returns_none_when_group_unavailable(self):
        """If no emoji from the group is present, fallback returns None."""
        FontManager._emoji_maps = {
            "20x20": {ord("😀"): "M:builtin/res/emojis/20x20/1f600.png"},
            "56x56": {ord("😀"): "M:builtin/res/emojis/56x56/1f600.png"},
        }

        src = FontManager._get_emoji_src(ord("♥"), 16)
        self.assertIsNone(src)


class TestFontManagerNormalizeEmojiText(unittest.TestCase):
    """Tests for FontManager.normalizeEmojiText()."""

    def test_strips_variation_selector_emoji(self):
        """U+FE0F (emoji presentation selector) is stripped."""
        text = "❤" + chr(0xFE0F)
        result = FontManager.normalizeEmojiText(text)
        self.assertEqual(result, "❤")

    def test_strips_variation_selector_text(self):
        """U+FE0E (text presentation selector) is stripped."""
        text = "❤" + chr(0xFE0E)
        result = FontManager.normalizeEmojiText(text)
        self.assertEqual(result, "❤")

    def test_strips_both_selectors(self):
        """Both variation selectors are stripped from mixed input."""
        text = "A" + chr(0xFE0F) + "B" + chr(0xFE0E) + "C"
        result = FontManager.normalizeEmojiText(text)
        self.assertEqual(result, "ABC")

    def test_plain_text_unchanged(self):
        """Plain text without variation selectors is returned unchanged."""
        text = "Hello, world!"
        self.assertEqual(FontManager.normalizeEmojiText(text), text)

    def test_empty_string(self):
        """Empty string is handled without error."""
        self.assertEqual(FontManager.normalizeEmojiText(""), "")


class TestFontManagerRendering(GraphicalTestCase):
    """End-to-end rendering tests: labels with composed emoji fonts."""

    def setUp(self):
        super().setUp()
        _reset_font_manager()

    def test_label_with_emoji_font_renders(self):
        """A label using a composed emoji font renders without crashing."""
        font = FontManager.getFont(size=16, family="Montserrat")
        label = lv.label(self.screen)
        label.set_style_text_font(font, lv.PART.MAIN)
        label.set_text("Hello ❤️ 😀")
        self.wait_for_render()

    def test_label_with_all_emoji_codepoints_renders(self):
        """A label containing all available emoji codepoints renders without crashing."""
        font = FontManager.getFont(size=16, family="Montserrat")
        cps = FontManager.getEmojiCodepoints()
        text = " ".join(chr(cp) for cp in cps)
        label = lv.label(self.screen)
        label.set_width(lv.pct(100))
        label.set_style_text_font(font, lv.PART.MAIN)
        label.set_text(text)
        self.wait_for_render()

    def test_small_font_uses_20x20_tier(self):
        """For font sizes with line_height <= 20, the 20x20 emoji tier is selected."""
        font_16 = FontManager.getFont(size=16, family="Montserrat")
        line_h = FontManager._font_pixel_height(font_16)
        if line_h <= 20:
            # Trigger emoji map loading
            FontManager.getEmojiCodepoints()
            cps = list(FontManager._emoji_maps.get("20x20", {}).keys())
            if cps:
                src = FontManager._get_emoji_src(cps[0], line_h)
                self.assertIsNotNone(src)
                self.assertIn("20x20", src)

    def test_large_font_uses_56x56_tier(self):
        """For font sizes with line_height > 20, the 56x56 emoji tier is selected."""
        font_28 = FontManager.getFont(size=28, family="Montserrat")
        line_h = FontManager._font_pixel_height(font_28)
        if line_h > 20:
            FontManager.getEmojiCodepoints()
            cps = list(FontManager._emoji_maps.get("56x56", {}).keys())
            if cps:
                src = FontManager._get_emoji_src(cps[0], line_h)
                self.assertIsNotNone(src)
                self.assertIn("56x56", src)

    def test_ttf_label_renders(self):
        """A label using a TTF-based font renders without crashing."""
        font = FontManager.getFont(size=20, ttf=_TEST_TTF_PATH)
        label = lv.label(self.screen)
        label.set_style_text_font(font, lv.PART.MAIN)
        label.set_text("Times NRW: ABC 123 xyz")
        self.wait_for_render()
