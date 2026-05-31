"""
Graphical test for hotspot settings refreshing overview values.

This test verifies:
1) Auth Mode changes in settings are reflected on the hotspot overview.
2) SSID changes in settings are reflected on the hotspot overview.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_hotspot_settings.py
    Device:  ./tests/unittest.sh tests/test_graphical_hotspot_settings.py --ondevice
"""

import unittest
import lvgl as lv
import mpos.ui
from mpos import (
    AppManager,
    SharedPreferences,
    WifiService,
    wait_for_text,
    wait_for_widget,
    click_button,
    click_label,
    print_screen_labels,
    verify_text_present,
    find_dropdown_widget,
    select_dropdown_option_by_text,
    get_widget_coords,
    simulate_click,
)


class TestGraphicalHotspotSettings(unittest.TestCase):
    """Graphical tests for hotspot settings refresh."""

    def _reset_hotspot_preferences(self):
        prefs = SharedPreferences("com.micropythonos.settings.hotspot")
        editor = prefs.edit()
        editor.remove_all()
        editor.commit()

    def _open_hotspot_settings_screen(self):
        result = AppManager.start_app("com.micropythonos.settings.hotspot")
        self.assertTrue(result, "Failed to start hotspot settings app")
        self.assertTrue(
            wait_for_text("Settings", timeout=10),
            "Hotspot app did not load within timeout",
        )

        screen = lv.screen_active()
        print("\nHotspot overview labels:")
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
        print("\nHotspot settings labels:")
        print_screen_labels(screen)
        return screen

    def _find_textarea(self, node):
        try:
            if node.__class__.__name__ == "textarea":
                return node
            if hasattr(node, "set_one_line") and hasattr(node, "set_text") and hasattr(node, "get_text"):
                return node
        except Exception:
            pass

        try:
            child_count = node.get_child_count()
        except Exception:
            return None

        for i in range(child_count):
            child = node.get_child(i)
            result = self._find_textarea(child)
            if result:
                return result
        return None

    def tearDown(self):
        try:
            WifiService.disable_hotspot()
        except Exception:
            pass

        try:
            mpos.ui.back_screen()
        except Exception:
            pass

    def test_auth_mode_change_updates_overview_security(self):
        """Verify Auth Mode change is reflected on the hotspot overview."""
        print("\n=== Starting hotspot Auth Mode overview refresh test ===")

        self._reset_hotspot_preferences()
        self._open_hotspot_settings_screen()

        self.assertTrue(
            click_label("Auth Mode"),
            "Could not click Auth Mode setting",
        )
        dropdown = wait_for_widget(
            lambda: find_dropdown_widget(lv.screen_active()),
            timeout=10,
        )
        self.assertIsNotNone(dropdown, "Auth Mode dropdown not found")

        coords = get_widget_coords(dropdown)
        self.assertIsNotNone(coords, "Could not get dropdown coordinates")
        simulate_click(coords["center_x"], coords["center_y"], press_duration_ms=100)

        self.assertTrue(
            select_dropdown_option_by_text(dropdown, "WPA2", allow_partial=True),
            "Could not select WPA2 option in dropdown",
        )

        self.assertTrue(
            click_button("Save"),
            "Could not click Save button in Auth Mode settings",
        )
        self.assertTrue(
            wait_for_text("Auth Mode", timeout=10),
            "Settings screen did not reload after Save",
        )

        mpos.ui.back_screen()
        self.assertTrue(
            wait_for_text("Security: WPA2", timeout=10),
            "Hotspot overview did not update Security after Auth Mode change",
        )

        print("\n=== Hotspot Auth Mode overview refresh test completed ===")

    def test_ssid_change_updates_overview_name(self):
        """Verify SSID change is reflected on the hotspot overview."""
        print("\n=== Starting hotspot SSID overview refresh test ===")

        new_ssid = "MPOS-Test-SSID"

        self._reset_hotspot_preferences()
        self._open_hotspot_settings_screen()

        self.assertTrue(
            click_label("Network Name (SSID)"),
            "Could not click Network Name (SSID) setting",
        )
        textarea = wait_for_widget(
            lambda: self._find_textarea(lv.screen_active()),
            timeout=10,
        )
        self.assertIsNotNone(textarea, "SSID textarea not found")
        textarea.set_text(new_ssid)

        self.assertTrue(
            click_button("Save"),
            "Could not click Save button in SSID settings",
        )
        self.assertTrue(
            wait_for_text("Auth Mode", timeout=10),
            "Settings screen did not reload after Save",
        )

        mpos.ui.back_screen()
        self.assertTrue(
            wait_for_text(f"Hotspot name: {new_ssid}", timeout=10),
            "Hotspot overview did not update SSID after settings change",
        )

        print("\n=== Hotspot SSID overview refresh test completed ===")


if __name__ == "__main__":
    pass
