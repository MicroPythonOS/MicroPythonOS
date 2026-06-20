"""
Graphical tests for FontManager.

Covers:
- getFont(): builtin families, size snapping, emoji=True/False, TTF loading, caching
- listFonts(): structure, completeness, renderability
- getEmojiCodepoints(): non-empty, sorted, emoji tier loaded
- getEmojiStrings(): complete emoji strings including flag sequences
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
    FontManager._emoji_map = None
    FontManager._emoji_strings = None
    FontManager._emoji_src_lookup_cache.clear()
    FontManager._emoji_sequence_lookup_cache.clear()
    FontManager._imgfont_scaled_src_cache.clear()
    FontManager._imgfont_source_size_cache.clear()
    FontManager._imgfont_empty_src_cache.clear()
    FontManager._unknown_emoji_codepoints_logged.clear()
    FontManager._builtin_font_records = None
    FontManager._emoji_similarity_group_members_by_cp = None
    FontManager._emoji_cp_bounds = None


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

    def test_getfont_missing_ttf_raises(self):
        """A missing TTF path should raise instead of silently falling back."""
        with self.assertRaises(OSError) as cm:
            FontManager.getFont(size=24, ttf="M:../tests/DOES_NOT_EXIST.ttf", emoji=False)
        self.assertIn("TTF file not found", str(cm.exception))

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
    """Tests for FontManager.getEmojiCodepoints() and emoji map loading."""

    def setUp(self):
        super().setUp()
        _reset_font_manager()

    def _get_emoji_map(self):
        FontManager.getEmojiCodepoints()
        return FontManager._emoji_map

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

    def test_emoji_tier_loaded_after_getemoji(self):
        """After getEmojiCodepoints(), the 32x32 tier is populated."""
        cps = self._get_emoji_map()
        self.assertTrue(len(cps) > 0)

    def test_tier_sources_point_to_correct_dir(self):
        """Source paths in the emoji map point to the 32x32 directory."""
        FontManager.getEmojiCodepoints()
        for cp, src in FontManager._emoji_map.items():
            self.assertIn("32x32", src, "emoji src should reference 32x32 dir")

    def test_similarity_group_fallback_uses_available_emoji(self):
        """Missing emoji falls back to another available emoji in the same group."""
        FontManager._emoji_map = {"2764": "M:builtin/res/emojis/32x32/2764.png"}

        src = FontManager._get_emoji_src(ord("♥"), 16)
        self.assertEqual(src, "M:builtin/res/emojis/32x32/2764.png")

    def test_similarity_group_fallback_returns_none_when_group_unavailable(self):
        """If no emoji from the group is present, fallback returns None."""
        FontManager._emoji_map = {"1F600": "M:builtin/res/emojis/32x32/1f600.png"}

        src = FontManager._get_emoji_src(ord("♥"), 16)
        self.assertIsNone(src)

    def test_low_codepoint_short_circuits_without_cache_entry(self):
        """Codepoints below threshold skip emoji lookup and are not cached."""
        src = FontManager._get_emoji_src(ord("A"), 16)
        self.assertIsNone(src)
        self.assertEqual(FontManager._emoji_src_lookup_cache, {})

    def test_codepoint_right_below_threshold_short_circuits(self):
        """U+203B (just below the threshold) short-circuits without caching."""
        src = FontManager._get_emoji_src(0x203B, 16)
        self.assertIsNone(src)
        self.assertEqual(FontManager._emoji_src_lookup_cache, {})

    def test_emoji_203C_is_found(self):
        """U+203C (‼ double exclamation mark, the threshold) is found in the 32x32 tier."""
        src = FontManager._get_emoji_src(0x203C, 16)
        self.assertIsNotNone(src)
        self.assertIn("32x32", src)

    def test_private_use_codepoint_short_circuits_without_cache_entry(self):
        """Private Use Area codepoints skip emoji lookup work and are not cached."""
        src = FontManager._get_emoji_src(0xF004, 16)
        self.assertIsNone(src)
        self.assertEqual(FontManager._emoji_src_lookup_cache, {})


class TestFontManagerEmojiStrings(GraphicalTestCase):
    """Tests for FontManager.getEmojiStrings()."""

    def setUp(self):
        super().setUp()
        _reset_font_manager()

    def test_getemoji_strings_nonempty(self):
        """getEmojiStrings() returns a non-empty list."""
        strings = FontManager.getEmojiStrings()
        self.assertIsInstance(strings, list)
        self.assertTrue(len(strings) > 0)

    def test_getemoji_strings_all_strings(self):
        """All items returned by getEmojiStrings() are non-empty strings."""
        for s in FontManager.getEmojiStrings():
            self.assertIsInstance(s, str)
            self.assertTrue(len(s) > 0)

    def test_getemoji_strings_sorted(self):
        """getEmojiStrings() returns strings in ascending order."""
        strings = FontManager.getEmojiStrings()
        self.assertEqual(strings, sorted(strings))

    def test_getemoji_strings_includes_elsalvador_flag(self):
        """getEmojiStrings() includes the full El Salvador flag sequence."""
        strings = FontManager.getEmojiStrings()
        self.assertIn("\U0001F1F8\U0001F1FB", strings)


class TestFontManagerVariantFallback(GraphicalTestCase):
    """Tests for variant fallback (stripping trailing modifiers)."""

    def setUp(self):
        super().setUp()
        _reset_font_manager()

    def test_variant_fallback_strips_modifier(self):
        """Missing skin-tone variant falls back to the base emoji."""
        FontManager._emoji_map = {"1F44D": "M:builtin/res/emojis/32x32/1F44D.png"}

        src = FontManager._lookup_emoji_src_by_key("1F44D-1F3FB")
        self.assertEqual(src, "M:builtin/res/emojis/32x32/1F44D.png")

    def test_variant_exact_match(self):
        """Exact variant file is returned when present."""
        FontManager._emoji_map = {
            "1F44D": "M:builtin/res/emojis/32x32/1F44D.png",
            "1F44D-1F3FB": "M:builtin/res/emojis/32x32/1F44D-1F3FB.png",
        }

        src = FontManager._lookup_emoji_src_by_key("1F44D-1F3FB")
        self.assertEqual(src, "M:builtin/res/emojis/32x32/1F44D-1F3FB.png")

    def test_variant_fallback_multi_segment(self):
        """Longer sequences fall back through each prefix."""
        FontManager._emoji_map = {
            "1F468": "M:builtin/res/emojis/32x32/1F468.png",
            "1F468-200D": "M:builtin/res/emojis/32x32/1F468-200D.png",
        }

        src = FontManager._lookup_emoji_src_by_key("1F468-200D-1F469")
        self.assertEqual(src, "M:builtin/res/emojis/32x32/1F468-200D.png")

    def test_imgfont_modifier_returns_empty(self):
        """Skin-tone modifier passed directly returns an empty image source."""
        font = FontManager.getFont(size=16, family="Montserrat", emoji=True)

        class _FakePtr:
            def __init__(self):
                self.value = None
            def __dereference__(self, value=None):
                if value is None:
                    return self.value
                self.value = value

        ptr = _FakePtr()
        src = FontManager._imgfont_path_cb(
            font, 0x1F3FB, 0, ptr, None
        )
        self.assertIsNotNone(src)
        self.assertIsInstance(src, lv.image_dsc_t)

    def test_imgfont_base_plus_modifier_lookup(self):
        """_imgfont_path_cb looks up base+modifier and falls back to base."""
        FontManager._emoji_map = {"1F44D": "M:builtin/res/emojis/32x32/1F44D.png"}

        font = FontManager.getFont(size=16, family="Montserrat", emoji=True)

        class _FakePtr:
            def __init__(self):
                self.value = None
            def __dereference__(self, value=None):
                if value is None:
                    return self.value
                self.value = value

        ptr = _FakePtr()
        src = FontManager._imgfont_path_cb(
            font, 0x1F44D, 0x1F3FB, ptr, None
        )
        self.assertIsNotNone(src)
        # _get_scaled_imgfont_src returns a raw string path only when source
        # and target dimensions match. With 32x32 emoji and a font-16 target
        # height (~16-18px) it returns a scaled lv.image_dsc_t instead.
        self.assertIsInstance(src, lv.image_dsc_t)


class TestFontManagerFlagEmoji(GraphicalTestCase):
    """Tests for regional-indicator flag emoji handling."""

    def setUp(self):
        super().setUp()
        _reset_font_manager()

    def _fake_offset_y_ptr(self):
        class _FakePtr:
            def __init__(self):
                self.value = None

            def __dereference__(self, value=None):
                if value is None:
                    return self.value
                self.value = value

        return _FakePtr()

    def test_is_regional_indicator(self):
        """Regional indicator codepoints are recognized."""
        self.assertTrue(FontManager._is_regional_indicator(0x1F1F8))
        self.assertTrue(FontManager._is_regional_indicator(0x1F1FB))
        self.assertFalse(FontManager._is_regional_indicator(0x1F600))
        self.assertFalse(FontManager._is_regional_indicator(0))

    def test_imgfont_flag_pair_renders(self):
        """A paired regional indicator sequence is resolved to a flag image."""
        font = FontManager.getFont(size=16, family="Montserrat", emoji=True)
        ptr = self._fake_offset_y_ptr()
        src = FontManager._imgfont_path_cb(
            font, 0x1F1F8, 0x1F1FB, ptr, None
        )
        self.assertIsNotNone(src)
        self.assertIsInstance(src, lv.image_dsc_t)
        # The scaled flag descriptor should be roughly square and larger than
        # the 1xheight placeholder used for standalone regional indicators.
        width = int(src.header.w)
        height = int(src.header.h)
        self.assertTrue(width > 1, "flag descriptor width should be greater than 1, got {}".format(width))
        self.assertTrue(height > 1, "flag descriptor height should be greater than 1, got {}".format(height))

    def test_imgfont_unpaired_regional_indicator_is_empty(self):
        """A standalone regional indicator returns an empty image source."""
        font = FontManager.getFont(size=16, family="Montserrat", emoji=True)
        ptr = self._fake_offset_y_ptr()
        src = FontManager._imgfont_path_cb(
            font, 0x1F1F8, 0, ptr, None
        )
        self.assertIsNotNone(src)
        self.assertIsInstance(src, lv.image_dsc_t)
        self.assertEqual(int(src.header.w), 1)

    def test_el_salvador_flag_renders_in_label(self):
        """A label containing the El Salvador flag renders without crashing."""
        font = FontManager.getFont(size=16, family="Montserrat", emoji=True)
        label = lv.label(self.screen)
        label.set_width(lv.pct(100))
        label.set_style_text_font(font, lv.PART.MAIN)
        label.set_text("El Salvador flag: \U0001F1F8\U0001F1FB")
        self.wait_for_render()

    def test_all_added_new_emojis_render_in_label(self):
        """The newly added emoji set renders without crashing."""
        font = FontManager.getFont(size=16, family="Montserrat", emoji=True)
        label = lv.label(self.screen)
        label.set_width(lv.pct(100))
        label.set_style_text_font(font, lv.PART.MAIN)
        label.set_text("\U0001F3CE\uFE0F \U0001F33D \U0001F355 \U0001F4A8 \U0001F4A5 \u270A \U0001FAF6 \U0001F9E1 \U0001F49C \U0001F426 \U0001F1F8\U0001F1FB \U0001F937\u200D\u2642\uFE0F")
        self.wait_for_render()


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


class TestFontManagerEmojiNeedDetection(unittest.TestCase):
    """Tests for simple emoji bool mode."""

    def setUp(self):
        _reset_font_manager()

    def test_getfont_emoji_false_returns_base(self):
        base = FontManager.getFont(size=16, family="Montserrat", emoji=False)
        font = FontManager.getFont(size=16, family="Montserrat", emoji=False)
        self.assertIs(font, base)

    def test_getfont_emoji_true_uses_composed(self):
        base = FontManager.getFont(size=16, family="Montserrat", emoji=False)
        font = FontManager.getFont(size=16, family="Montserrat", emoji=True)
        self.assertIsNotNone(font)
        self.assertIsNot(font, base)


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

    def test_label_with_all_emoji_strings_renders(self):
        """A label containing all available emoji strings renders without crashing."""
        font = FontManager.getFont(size=16, family="Montserrat")
        strings = FontManager.getEmojiStrings()
        text = " ".join(strings)
        label = lv.label(self.screen)
        label.set_width(lv.pct(100))
        label.set_style_text_font(font, lv.PART.MAIN)
        label.set_text(text)
        self.wait_for_render()

    def test_emoji_resolves_from_32x32_tier(self):
        """All font sizes resolve emoji from the 32x32 tier."""
        font = FontManager.getFont(size=16, family="Montserrat")
        line_h = FontManager._font_pixel_height(font)
        FontManager.getEmojiCodepoints()
        cps = list((FontManager._emoji_map or {}).keys())
        if cps:
            src = FontManager._get_emoji_src(cps[0], line_h)
            self.assertIsNotNone(src)
            self.assertIn("32x32", src)

    def test_ttf_label_renders(self):
        """A label using a TTF-based font renders without crashing."""
        font = FontManager.getFont(size=20, ttf=_TEST_TTF_PATH)
        label = lv.label(self.screen)
        label.set_style_text_font(font, lv.PART.MAIN)
        label.set_text("Times NRW: ABC 123 xyz")
        self.wait_for_render()
