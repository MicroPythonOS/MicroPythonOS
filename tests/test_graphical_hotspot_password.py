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
    wait_for_render,
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
        wait_for_render(iterations=20)

        screen = lv.screen_active()
        print("\nInitial screen labels:")
        print_screen_labels(screen)

        self.assertTrue(
            click_button("Settings"),
            "Could not find Settings button in hotspot app",
        )
        wait_for_render(iterations=40)

        screen = lv.screen_active()
        print("\nSettings screen labels:")
        print_screen_labels(screen)
        return screen

    def tearDown(self):
        """Clean up after each test method."""
        # Navigate back to launcher to close any opened apps
        try:
            mpos.ui.back_screen()
            wait_for_render(5)
        except:
            pass

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
            "(defaults to none)",
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

        self.assertTrue(
            click_label("Auth Mode"),
            "Could not click Auth Mode setting",
        )
        wait_for_render(iterations=40)

        screen = lv.screen_active()
        dropdown = find_dropdown_widget(screen)
        self.assertIsNotNone(dropdown, "Auth Mode dropdown not found")

        coords = get_widget_coords(dropdown)
        self.assertIsNotNone(coords, "Could not get dropdown coordinates")

        print(f"Clicking dropdown at ({coords['center_x']}, {coords['center_y']})")
        simulate_click(coords["center_x"], coords["center_y"], press_duration_ms=100)
        wait_for_render(iterations=20)

        self.assertTrue(
            select_dropdown_option_by_text(dropdown, "WPA2", allow_partial=True),
            "Could not select WPA2 option in dropdown",
        )
        wait_for_render(iterations=20)

        self.assertTrue(
            click_button("Save"),
            "Could not click Save button in Auth Mode settings",
        )
        wait_for_render(iterations=40)

        screen = lv.screen_active()
        self.assertTrue(
            verify_text_present(screen, "Password"),
            "Password setting did not appear after selecting WPA2",
        )

        self.assertTrue(
            click_label("Auth Mode"),
            "Could not click Auth Mode setting to revert",
        )
        wait_for_render(iterations=40)

        screen = lv.screen_active()
        dropdown = find_dropdown_widget(screen)
        self.assertIsNotNone(dropdown, "Auth Mode dropdown not found on revert")

        coords = get_widget_coords(dropdown)
        self.assertIsNotNone(coords, "Could not get dropdown coordinates on revert")

        print(f"Clicking dropdown at ({coords['center_x']}, {coords['center_y']})")
        simulate_click(coords["center_x"], coords["center_y"], press_duration_ms=100)
        wait_for_render(iterations=20)

        self.assertTrue(
            select_dropdown_option_by_text(dropdown, "None", allow_partial=True),
            "Could not select None option in dropdown",
        )
        wait_for_render(iterations=20)

        self.assertTrue(
            click_button("Save"),
            "Could not click Save button in Auth Mode settings (revert)",
        )
        wait_for_render(iterations=40)

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

        self.assertTrue(
            click_label("Auth Mode"),
            "Could not click Auth Mode setting",
        )
        wait_for_render(iterations=40)

        screen = lv.screen_active()
        dropdown = find_dropdown_widget(screen)
        self.assertIsNotNone(dropdown, "Auth Mode dropdown not found")

        coords = get_widget_coords(dropdown)
        self.assertIsNotNone(coords, "Could not get dropdown coordinates")

        print(f"Clicking dropdown at ({coords['center_x']}, {coords['center_y']})")
        simulate_click(coords["center_x"], coords["center_y"], press_duration_ms=100)
        wait_for_render(iterations=20)

        self.assertTrue(
            select_dropdown_option_by_text(dropdown, "WPA2", allow_partial=True),
            "Could not select WPA2 option in dropdown",
        )
        wait_for_render(iterations=20)

        self.assertTrue(
            click_button("Save"),
            "Could not click Save button in Auth Mode settings",
        )
        wait_for_render(iterations=40)

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

        self.assertTrue(
            click_label("Auth Mode"),
            "Could not click Auth Mode setting",
        )
        wait_for_render(iterations=40)

        screen = lv.screen_active()
        print("\nAuth Mode edit screen labels:")
        print_screen_labels(screen)

        dropdown = find_dropdown_widget(screen)
        self.assertIsNotNone(dropdown, "Auth Mode dropdown not found")

        coords = get_widget_coords(dropdown)
        self.assertIsNotNone(coords, "Could not get dropdown coordinates")

        print(f"Clicking dropdown at ({coords['center_x']}, {coords['center_y']})")
        simulate_click(coords["center_x"], coords["center_y"], press_duration_ms=100)
        wait_for_render(iterations=20)

        self.assertTrue(
            select_dropdown_option_by_text(dropdown, "WPA2", allow_partial=True),
            "Could not select WPA2 option in dropdown",
        )
        wait_for_render(iterations=20)

        self.assertTrue(
            click_button("Save"),
            "Could not click Save button in Auth Mode settings",
        )
        wait_for_render(iterations=40)

        screen = lv.screen_active()
        print("\nSettings screen labels after save:")
        print_screen_labels(screen)

        value_text = get_setting_value_text(screen, "Auth Mode")
        print(f"Auth Mode value text after save: {value_text}")
        self.assertEqual(
            value_text,
            "wpa2",
            "Auth Mode value did not update to wpa2",
        )

        print("\n=== Hotspot settings Auth Mode dropdown test completed ===")


if __name__ == "__main__":
    pass
