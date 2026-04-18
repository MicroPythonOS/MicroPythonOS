"""
Unit tests for the app-local theme override helper in the Lightning Piggy app.

Targets LightningPiggyApp PR #27 (app-local Light/Dark theme toggle). The
override lives in the app's own prefs under `theme_override`; if set, it
takes precedence over the OS-level theme but never writes to OS prefs.

This test covers the `_AppThemeView` adapter class that feeds
AppearanceManager.init() a synthesised prefs view (override value + OS
primary color) without touching OS prefs on disk.

Usage:
    Desktop: ./tests/unittest.sh tests/test_displaywallet_theme_override.py
    Device:  ./tests/unittest.sh tests/test_displaywallet_theme_override.py --ondevice
"""

import sys
import unittest

sys.path.append("apps/com.lightningpiggy.displaywallet/assets/")

# The _AppThemeView class is defined at module-level in displaywallet.py.
# Importing displaywallet pulls in LVGL+SettingsActivity machinery which is
# heavy/noisy, but it works in the test harness. If the feature isn't landed
# yet, _AppThemeView won't exist and the tests skip gracefully.
try:
    import displaywallet
    _HAVE_APP_THEME_VIEW = hasattr(displaywallet, "_AppThemeView")
except Exception:
    _HAVE_APP_THEME_VIEW = False


@unittest.skipUnless(_HAVE_APP_THEME_VIEW, "_AppThemeView not installed (PR #27 not landed)")
class TestAppThemeView(unittest.TestCase):
    """The `_AppThemeView` duck-type mimics the `SharedPreferences.get_string`
    surface needed by `AppearanceManager.init()`, so the theme can be
    reinitialised with an app-local override without touching OS prefs."""

    def test_returns_stored_theme_light_dark(self):
        v = displaywallet._AppThemeView("dark", "0x1234AB")
        self.assertEqual(v.get_string("theme_light_dark"), "dark")

    def test_returns_stored_primary_color(self):
        v = displaywallet._AppThemeView("light", "0xABCDEF")
        self.assertEqual(v.get_string("theme_primary_color"), "0xABCDEF")

    def test_unknown_key_returns_default(self):
        v = displaywallet._AppThemeView("dark", "0x123456")
        self.assertEqual(v.get_string("unrelated_key", "fallback"), "fallback")
        # And None default when no default provided
        self.assertIsNone(v.get_string("unrelated_key"))

    def test_does_not_expose_set_or_edit(self):
        # The view intentionally exposes only get_string — AppearanceManager.init
        # reads from it and shouldn't try to write. Missing setters would be a
        # regression.
        v = displaywallet._AppThemeView("light", "0x000000")
        self.assertFalse(hasattr(v, "set_string"))
        self.assertFalse(hasattr(v, "edit"))


@unittest.skipUnless(_HAVE_APP_THEME_VIEW, "_AppThemeView not installed")
class TestAppThemeViewIntegrationWithAppearanceManager(unittest.TestCase):
    """Once PR #120 lands, AppearanceManager.init() uses edit/put_string/commit
    on its prefs arg when called from the setters — but *not* from init() itself,
    which only reads via get_string. So an _AppThemeView (read-only) is
    compatible with init() even though it has no edit() method."""

    def test_init_reads_from_view_without_writing(self):
        from mpos import AppearanceManager
        saved = AppearanceManager.is_light_mode()
        try:
            v = displaywallet._AppThemeView("dark", "0xF0A010")
            # Must not raise, must not attempt to write.
            AppearanceManager.init(v)
            self.assertFalse(AppearanceManager.is_light_mode())

            v = displaywallet._AppThemeView("light", "0xF0A010")
            AppearanceManager.init(v)
            self.assertTrue(AppearanceManager.is_light_mode())
        finally:
            AppearanceManager._is_light_mode = saved


_HAVE_APPLY_SCREEN_THEME = _HAVE_APP_THEME_VIEW and hasattr(displaywallet, "_apply_screen_theme") if _HAVE_APP_THEME_VIEW else False


@unittest.skipUnless(_HAVE_APPLY_SCREEN_THEME, "_apply_screen_theme not installed")
class TestApplyScreenTheme(unittest.TestCase):
    """`_apply_screen_theme(screen)` forces an explicit bg colour that matches
    the app's main display — pure black in dark mode, pure white in light mode.
    MUST set both directions: once an explicit style is set it overrides LVGL's
    default-theme bg, so a dark→light toggle would leave a lingering black bg
    if we only set black."""

    class _RecordingScreen:
        """Minimal screen stub that records the last `set_style_bg_color` call."""
        def __init__(self):
            self.last_color = None
            self.last_part = None
            self.calls = 0

        def set_style_bg_color(self, color, part):
            self.last_color = color
            self.last_part = part
            self.calls += 1

    def _force_mode(self, is_light):
        from mpos import AppearanceManager
        AppearanceManager._is_light_mode = bool(is_light)

    def test_dark_mode_sets_black_bg(self):
        from mpos import AppearanceManager
        saved = AppearanceManager.is_light_mode()
        try:
            self._force_mode(False)
            import lvgl as lv
            screen = self._RecordingScreen()
            displaywallet._apply_screen_theme(screen)
            # Compare underlying 0xRRGGBB int because LVGL color_t objects
            # don't implement __eq__ across all builds.
            self.assertEqual(screen.calls, 1)
            self.assertEqual(screen.last_part, lv.PART.MAIN)
            # color_black == 0x000000
            self.assertEqual(screen.last_color.full if hasattr(screen.last_color, 'full') else None,
                             lv.color_black().full if hasattr(lv.color_black(), 'full') else None)
        finally:
            AppearanceManager._is_light_mode = saved

    def test_light_mode_sets_white_bg(self):
        from mpos import AppearanceManager
        saved = AppearanceManager.is_light_mode()
        try:
            self._force_mode(True)
            import lvgl as lv
            screen = self._RecordingScreen()
            displaywallet._apply_screen_theme(screen)
            self.assertEqual(screen.calls, 1)
            self.assertEqual(screen.last_part, lv.PART.MAIN)
            self.assertEqual(screen.last_color.full if hasattr(screen.last_color, 'full') else None,
                             lv.color_white().full if hasattr(lv.color_white(), 'full') else None)
        finally:
            AppearanceManager._is_light_mode = saved

    def test_applies_in_both_directions(self):
        """Regression: if only dark mode set a bg, a dark→light flip leaves the
        black style lingering on screen. Guard that BOTH branches write."""
        from mpos import AppearanceManager
        saved = AppearanceManager.is_light_mode()
        try:
            screen = self._RecordingScreen()

            self._force_mode(False)
            displaywallet._apply_screen_theme(screen)
            dark_count = screen.calls

            self._force_mode(True)
            displaywallet._apply_screen_theme(screen)
            light_count = screen.calls

            self.assertEqual(dark_count, 1, "dark mode should set bg once")
            self.assertEqual(light_count, 2, "light mode should also set bg (not skip)")
        finally:
            AppearanceManager._is_light_mode = saved


if __name__ == "__main__":
    unittest.main()
