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


if __name__ == "__main__":
    unittest.main()
