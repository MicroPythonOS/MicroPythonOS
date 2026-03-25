"""
Graphical test for hotspot start flow with security none and invalid password handling.

This test verifies:
1) Starting hotspot with default settings and Security: None succeeds.
2) Starting hotspot with an invalid WPA2 password fails and leaves hotspot disabled.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_hotspot_security_none.py
    Device:  ./tests/unittest.sh tests/test_graphical_hotspot_security_none.py --ondevice
"""

import unittest
import lvgl as lv
import mpos.ui
from mpos import (
    AppManager,
    WifiService,
    SharedPreferences,
    wait_for_render,
    click_button,
    print_screen_labels,
    verify_text_present,
)


class TestGraphicalHotspotSecurityNone(unittest.TestCase):
    """Graphical tests for hotspot security handling."""

    def _reset_hotspot_preferences(self):
        prefs = SharedPreferences("com.micropythonos.settings.hotspot")
        editor = prefs.edit()
        editor.remove_all()
        editor.commit()

    def _set_hotspot_preferences(self, ssid=None, password=None, authmode=None):
        prefs = SharedPreferences("com.micropythonos.settings.hotspot")
        editor = prefs.edit()
        if ssid is not None:
            editor.put_string("ssid", ssid)
        if password is not None:
            editor.put_string("password", password)
        if authmode is not None:
            editor.put_string("authmode", authmode)
        editor.commit()

    def _open_hotspot_screen(self):
        result = AppManager.start_app("com.micropythonos.settings.hotspot")
        self.assertTrue(result, "Failed to start hotspot settings app")
        wait_for_render(iterations=20)
        screen = lv.screen_active()
        print("\nHotspot screen labels:")
        print_screen_labels(screen)
        return screen

    def tearDown(self):
        try:
            WifiService.disable_hotspot()
        except Exception:
            pass

        try:
            mpos.ui.back_screen()
            wait_for_render(5)
        except Exception:
            pass

    def test_security_none_allows_open_hotspot(self):
        """Ensure Security: None starts an open hotspot successfully."""
        print("\n=== Starting hotspot security none test ===")

        self._reset_hotspot_preferences()
        screen = self._open_hotspot_screen()

        self.assertFalse(
            WifiService.is_hotspot_enabled(),
            "Hotspot should be disabled before pressing Start",
        )

        WifiService.wifi_busy = False

        self.assertTrue(
            click_button("Start"),
            "Could not find Start button in hotspot app",
        )
        wait_for_render(iterations=40)

        self.assertTrue(
            WifiService.is_hotspot_enabled(),
            "Hotspot should be enabled with Security: None",
        )

        screen = lv.screen_active()
        print("\nHotspot screen labels after Start:")
        print_screen_labels(screen)
        self.assertTrue(
            verify_text_present(screen, "Security: None"),
            "Hotspot should display Security: None after start",
        )
        self.assertTrue(
            verify_text_present(screen, "Status: Running"),
            "Hotspot should display Status: Running after start",
        )

        print("\n=== Hotspot security none test completed ===")

    @unittest.skipIf(
        WifiService._is_desktop_mode(None),
        "Invalid password handling requires device network stack",
    )
    def test_invalid_password_fails_and_reports_disabled(self):
        """Ensure invalid WPA2 password fails and hotspot remains disabled."""
        print("\n=== Starting hotspot invalid password test ===")

        self._reset_hotspot_preferences()
        self._set_hotspot_preferences(password="123", authmode="wpa2")

        screen = self._open_hotspot_screen()

        self.assertFalse(
            WifiService.is_hotspot_enabled(),
            "Hotspot should be disabled before pressing Start",
        )

        WifiService.wifi_busy = False

        self.assertTrue(
            click_button("Start"),
            "Could not find Start button in hotspot app",
        )
        wait_for_render(iterations=40)

        self.assertFalse(
            WifiService.is_hotspot_enabled(),
            "Hotspot should remain disabled when password is invalid",
        )

        screen = lv.screen_active()
        print("\nHotspot screen labels after invalid password attempt:")
        print_screen_labels(screen)
        self.assertTrue(
            verify_text_present(screen, "Status: Stopped"),
            "Hotspot should display Status: Stopped after failed start",
        )

        print("\n=== Hotspot invalid password test completed ===")


if __name__ == "__main__":
    pass
