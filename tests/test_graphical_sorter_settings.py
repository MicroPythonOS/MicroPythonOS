"""
Test that Sorter's settings button opens the SettingActivity screen for the
sound-effects setting and that changes to the preference are persisted.

Usage:
"""

import unittest

import lvgl as lv

from mpos import AppManager, SharedPreferences, wait_for_render
from mpos.ui.input_activity import InputActivity
from mpos.ui.testing import (
    click_button,
    wait_for_text,
)
from mpos.ui.view import screen_stack


APP_NAME = "com.micropythonos.sorter"


def _clear_sorter_prefs():
    prefs = SharedPreferences(APP_NAME)
    editor = prefs.edit()
    editor.remove_all()
    editor.commit()


def _current_activity():
    if not screen_stack:
        return None
    return screen_stack[-1][0]


class TestSorterSettingsActivity(unittest.TestCase):
    """Verify the Sorter settings button opens the shared SettingActivity."""

    def setUp(self):
        """Return to launcher and clear sorter prefs before each test."""
        AppManager.restart_launcher()
        wait_for_render(10)
        _clear_sorter_prefs()

    def tearDown(self):
        """Navigate back to launcher after each test."""
        try:
            from mpos import ui

            ui.back_screen()
            wait_for_render(5)
        except Exception:
            pass

    def test_settings_opens_sound_effects_setting(self):
        """Clicking the settings icon opens the sound-effects setting."""
        result = AppManager.start_app(APP_NAME)
        self.assertTrue(result, "Sorter should start")
        wait_for_render(10)

        self.assertTrue(click_button(lv.SYMBOL.SETTINGS))
        wait_for_render(10)

        self.assertTrue(wait_for_text("Sound effects", timeout=5), "Setting title should be visible")
        self.assertTrue(wait_for_text("On", timeout=5), "On option should be visible")
        self.assertTrue(wait_for_text("Off", timeout=5), "Off option should be visible")
        self.assertTrue(wait_for_text("Save", timeout=5), "Save button should be visible")

    def test_sound_effects_persists(self):
        """Changing the sound-effects preference through SettingActivity saves it."""
        result = AppManager.start_app(APP_NAME)
        self.assertTrue(result, "Sorter should start")
        wait_for_render(10)

        self.assertTrue(click_button(lv.SYMBOL.SETTINGS))
        wait_for_render(10)

        # SettingActivity immediately launches InputActivity for the radio
        # picker. Interacting with the LVGL checkbox wrappers from a test is
        # fragile, so we set the activity's selected index directly and save.
        input_activity = _current_activity()
        self.assertIsInstance(
            input_activity,
            InputActivity,
            "SettingActivity should have launched InputActivity",
        )
        self.assertEqual(
            input_activity.active_radio_index,
            0,
            "The default value 'true' should pre-select the 'On' option",
        )
        input_activity.active_radio_index = 1
        wait_for_render(2)

        self.assertTrue(click_button("Save"))
        wait_for_render(10)

        self.assertTrue(
            wait_for_text("Level: 1", timeout=10),
            "Should return to the Sorter screen",
        )

        activity = _current_activity()
        self.assertIsNotNone(activity)
        self.assertFalse(activity.sound_effects)
        self.assertEqual(
            SharedPreferences(APP_NAME).get_string("sound_effects", ""),
            "false",
        )


if __name__ == "__main__":
    unittest.main()
