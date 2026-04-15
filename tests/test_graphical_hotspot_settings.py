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
    wait_for_render,
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
        wait_for_render(iterations=40)

        screen = lv.screen_active()
        print("\nHotspot overview labels:")
        print_screen_labels(screen)

        self.assertTrue(
            click_button("Settings"),
            "Could not find Settings button in hotspot app",
        )
        wait_for_render(iterations=60)

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
            wait_for_render(25)
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
        wait_for_render(iterations=50)

        screen = lv.screen_active()
        dropdown = find_dropdown_widget(screen)
        self.assertIsNotNone(dropdown, "Auth Mode dropdown not found")

        coords = get_widget_coords(dropdown)
        self.assertIsNotNone(coords, "Could not get dropdown coordinates")

        print(f"Clicking dropdown at ({coords['center_x']}, {coords['center_y']})")
        simulate_click(coords["center_x"], coords["center_y"], press_duration_ms=100)
        wait_for_render(iterations=25)

        self.assertTrue(
            select_dropdown_option_by_text(dropdown, "WPA2", allow_partial=True),
            "Could not select WPA2 option in dropdown",
        )
        wait_for_render(iterations=25)

        self.assertTrue(
            click_button("Save"),
            "Could not click Save button in Auth Mode settings",
        )
        wait_for_render(iterations=50)

        mpos.ui.back_screen()
        wait_for_render(iterations=25)

        screen = lv.screen_active()
        print("\nHotspot overview labels after Auth Mode change:")
        print_screen_labels(screen)
        self.assertTrue(
            verify_text_present(screen, "Security: WPA2"),
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
        wait_for_render(iterations=40)

        screen = lv.screen_active()
        textarea = self._find_textarea(screen)
        self.assertIsNotNone(textarea, "SSID textarea not found")
        textarea.set_text(new_ssid)
        wait_for_render(iterations=25)

        self.assertTrue(
            click_button("Save"),
            "Could not click Save button in SSID settings",
        )
        wait_for_render(iterations=40)

        mpos.ui.back_screen()
        wait_for_render(iterations=25)

        screen = lv.screen_active()
        print("\nHotspot overview labels after SSID change:")
        print_screen_labels(screen)
        self.assertTrue(
            verify_text_present(screen, f"Hotspot name: {new_ssid}"),
            "Hotspot overview did not update SSID after settings change",
        )

        print("\n=== Hotspot SSID overview refresh test completed ===")


if __name__ == "__main__":
    pass
