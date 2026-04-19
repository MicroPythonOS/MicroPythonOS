"""
Unit tests for AppearanceManager.set_light_mode / set_primary_color.

Regression tests: pre-fix these methods called prefs.set_string(...) — a method
that does not exist on SharedPreferences — so any third-party caller supplying a
prefs object hit AttributeError. These tests pin down the corrected
edit/put_string/commit write path and the expected on-disk values.

Usage:
    Desktop: ./tests/unittest.sh tests/test_appearance_manager.py
    Device:  ./tests/unittest.sh tests/test_appearance_manager.py --ondevice
"""

import os
import unittest

from mpos import AppearanceManager, SharedPreferences


class TestAppearanceManagerPrefs(unittest.TestCase):

    APP_ID = "com.test.appearance_manager"
    FILEPATH = "data/com.test.appearance_manager/config.json"

    def setUp(self):
        # Scrub any leftover prefs from previous runs so get_string()
        # observations reflect only what this test writes.
        self._remove(self.FILEPATH)
        # Snapshot AppearanceManager state so a test that flips light_mode
        # doesn't leak into the next test.
        self._saved_is_light = AppearanceManager.is_light_mode()
        self._saved_primary = AppearanceManager.get_primary_color()

    def tearDown(self):
        self._remove(self.FILEPATH)
        # Best-effort restore.
        AppearanceManager._is_light_mode = self._saved_is_light
        AppearanceManager._primary_color = self._saved_primary

    def _remove(self, path):
        try:
            os.remove(path)
        except OSError:
            pass

    # ---- set_light_mode --------------------------------------------------

    def test_set_light_mode_dark_persists(self):
        prefs = SharedPreferences(self.APP_ID)
        AppearanceManager.set_light_mode(False, prefs)
        self.assertEqual(prefs.get_string("theme_light_dark"), "dark")
        self.assertFalse(AppearanceManager.is_light_mode())

    def test_set_light_mode_light_persists(self):
        prefs = SharedPreferences(self.APP_ID)
        AppearanceManager.set_light_mode(True, prefs)
        self.assertEqual(prefs.get_string("theme_light_dark"), "light")
        self.assertTrue(AppearanceManager.is_light_mode())

    def test_set_light_mode_without_prefs_updates_memory_only(self):
        # Without a prefs arg the method must not raise and must still update
        # the in-memory flag, matching the documented "prefs optional" signature.
        AppearanceManager.set_light_mode(False)
        self.assertFalse(AppearanceManager.is_light_mode())
        AppearanceManager.set_light_mode(True)
        self.assertTrue(AppearanceManager.is_light_mode())

    # ---- set_primary_color -----------------------------------------------

    def test_set_primary_color_persists_hex_string(self):
        prefs = SharedPreferences(self.APP_ID)
        AppearanceManager.set_primary_color(0xFF5722, prefs)
        self.assertEqual(prefs.get_string("theme_primary_color"), "0xFF5722")

    def test_set_primary_color_non_int_does_not_persist(self):
        # The method only persists when the colour is an int; anything else
        # (e.g. an lv.color_t) just updates the in-memory value. It must not
        # raise either way.
        prefs = SharedPreferences(self.APP_ID)
        try:
            AppearanceManager.set_primary_color("not-an-int", prefs)
        except Exception as e:
            self.fail("set_primary_color raised for non-int colour: %r" % e)
        # Key wasn't written, so get_string returns the explicit default.
        self.assertEqual(
            prefs.get_string("theme_primary_color", "__unset__"),
            "__unset__",
        )


if __name__ == "__main__":
    unittest.main()
