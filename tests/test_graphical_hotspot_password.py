"""
Graphical test for hotspot settings password defaults.

This test verifies that the hotspot settings screen shows the
"(defaults to none)" value under the "Auth Mode" setting.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_hotspot_password.py
    Device:  ./tests/unittest.sh tests/test_graphical_hotspot_password.py --ondevice
"""

import unittest
import lvgl as lv
import mpos.ui
from mpos import (
    AppManager,
    wait_for_text,
    wait_for_widget,
    print_screen_labels,
    click_button,
    verify_text_present,
    find_setting_value_label,
    get_setting_value_text,
    click_label,
    simulate_click,
    get_widget_coords,
    select_dropdown_option_by_text,
    find_dropdown_widget,
    SharedPreferences,
)


class TestGraphicalHotspotPassword(unittest.TestCase):
    """Test suite for hotspot password defaults in settings UI."""

    def _reset_hotspot_preferences(self):
        """Clear hotspot preferences to ensure default values are shown."""
        prefs = SharedPreferences("com.micropythonos.settings.hotspot")
        editor = prefs.edit()
        editor.remove_all()
        editor.commit()

    def _open_hotspot_settings_screen(self):
        """Start hotspot app and open the Settings screen."""
        result = AppManager.start_app("com.micropythonos.settings.hotspot")
        self.assertTrue(result, "Failed to start hotspot settings app")
        self.assertTrue(
            wait_for_text("Settings", timeout=10),
            "Hotspot app did not load within timeout",
        )

        screen = lv.screen_active()
        print("\nInitial screen labels:")
        print_screen_labels(screen)

        self.assertTrue(
            click_button("Settings"),
            "Could not find Settings button in hotspot app",
        )
        self.assertTrue(
            wait_for_text("Auth Mode", timeout=10),
            "Settings screen did not load within timeout",
        )

        screen = lv.screen_active()
        print("\nSettings screen labels:")
        print_screen_labels(screen)
        return screen

    def tearDown(self):
        try:
            mpos.ui.back_screen()
        except:
            pass

    def _wait_for_settings_after_save(self):
        """After clicking Save on an edit screen, wait for settings to reload."""
        return wait_for_text("Auth Mode", timeout=10)

    def _click_auth_mode_and_wait_for_dropdown(self):
        self.assertTrue(
            click_label("Auth Mode"),
            "Could not click Auth Mode setting",
        )
        dropdown = wait_for_widget(
            lambda: find_dropdown_widget(lv.screen_active()),
            timeout=10,
        )
        self.assertIsNotNone(dropdown, "Auth Mode dropdown not found")
        return dropdown

    def _open_dropdown_and_select(self, dropdown, option):
        coords = get_widget_coords(dropdown)
        self.assertIsNotNone(coords, "Could not get dropdown coordinates")
        simulate_click(coords["center_x"], coords["center_y"], press_duration_ms=100)
        self.assertTrue(
            select_dropdown_option_by_text(dropdown, option, allow_partial=True),
            f"Could not select {option} option in dropdown",
        )

    def test_auth_mode_defaults_label(self):
        """Verify Auth Mode shows defaults to none in hotspot settings."""
        print("\n=== Starting Hotspot Settings Auth Mode default test ===")

        self._reset_hotspot_preferences()
        screen = self._open_hotspot_settings_screen()

        self.assertTrue(
            verify_text_present(screen, "Auth Mode"),
            "Auth Mode setting title not found on settings screen",
        )

        value_label = find_setting_value_label(screen, "Auth Mode")
        self.assertIsNotNone(
            value_label,
            "Could not find value label for Auth Mode setting",
        )

        value_text = get_setting_value_text(screen, "Auth Mode")
        print(f"Auth Mode value text: {value_text}")
        self.assertEqual(
            value_text,
            "(defaults to None)",
            "Auth Mode value text did not match expected default",
        )

        print("\n=== Hotspot settings Auth Mode default test completed ===")

    def test_auth_mode_change_hides_password_setting(self):
        """Verify Password setting disappears after switching Auth Mode to None."""
        print("\n=== Starting Hotspot Settings Password hide test ===")

        self._reset_hotspot_preferences()
        screen = self._open_hotspot_settings_screen()

        self.assertFalse(
            verify_text_present(screen, "Password"),
            "Password setting should not be visible with Auth Mode None",
        )

        dropdown = self._click_auth_mode_and_wait_for_dropdown()

        self._open_dropdown_and_select(dropdown, "WPA2")

        self.assertTrue(
            click_button("Save"),
            "Could not click Save button in Auth Mode settings",
        )
        self.assertTrue(
            self._wait_for_settings_after_save(),
            "Settings screen did not reload after Save",
        )

        screen = lv.screen_active()
        self.assertTrue(
            verify_text_present(screen, "Password"),
            "Password setting did not appear after selecting WPA2",
        )

        dropdown = self._click_auth_mode_and_wait_for_dropdown()

        self._open_dropdown_and_select(dropdown, "None")

        self.assertTrue(
            click_button("Save"),
            "Could not click Save button in Auth Mode settings (revert)",
        )
        self.assertTrue(
            self._wait_for_settings_after_save(),
            "Settings screen did not reload after Save (revert)",
        )

        screen = lv.screen_active()
        print("\nSettings screen labels after Auth Mode revert:")
        print_screen_labels(screen)

        self.assertFalse(
            verify_text_present(screen, "Password"),
            "Password setting did not disappear after selecting None",
        )

        print("\n=== Hotspot settings Password hide test completed ===")

    def test_auth_mode_change_shows_password_setting(self):
        """Verify Password setting appears after switching Auth Mode to WPA2."""
        print("\n=== Starting Hotspot Settings Password visibility test ===")

        self._reset_hotspot_preferences()
        screen = self._open_hotspot_settings_screen()

        self.assertFalse(
            verify_text_present(screen, "Password"),
            "Password setting should not be visible with Auth Mode None",
        )

        dropdown = self._click_auth_mode_and_wait_for_dropdown()

        self._open_dropdown_and_select(dropdown, "WPA2")

        self.assertTrue(
            click_button("Save"),
            "Could not click Save button in Auth Mode settings",
        )
        self.assertTrue(
            self._wait_for_settings_after_save(),
            "Settings screen did not reload after Save",
        )

        screen = lv.screen_active()
        print("\nSettings screen labels after Auth Mode change:")
        print_screen_labels(screen)

        self.assertTrue(
            verify_text_present(screen, "Password"),
            "Password setting did not appear after selecting WPA2",
        )

        print("\n=== Hotspot settings Password visibility test completed ===")

    def test_auth_mode_dropdown_select_wpa2(self):
        """Change Auth Mode via dropdown and verify stored value label."""
        print("\n=== Starting Hotspot Settings Auth Mode dropdown test ===")

        self._reset_hotspot_preferences()
        screen = self._open_hotspot_settings_screen()

        dropdown = self._click_auth_mode_and_wait_for_dropdown()

        screen = lv.screen_active()
        print("\nAuth Mode edit screen labels:")
        print_screen_labels(screen)

        self._open_dropdown_and_select(dropdown, "WPA2")

        self.assertTrue(
            click_button("Save"),
            "Could not click Save button in Auth Mode settings",
        )
        self.assertTrue(
            self._wait_for_settings_after_save(),
            "Settings screen did not reload after Save",
        )

        screen = lv.screen_active()
        print("\nSettings screen labels after save:")
        print_screen_labels(screen)

        value_text = get_setting_value_text(screen, "Auth Mode")
        print(f"Auth Mode value text after save: {value_text}")
        self.assertEqual(
            value_text,
            "WPA2",
            "Auth Mode value did not update to WPA2",
        )

        print("\n=== Hotspot settings Auth Mode dropdown test completed ===")


if __name__ == "__main__":
    pass
