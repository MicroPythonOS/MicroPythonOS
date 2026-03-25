"""
Graphical test for enabling hotspot from the Hotspot Settings app.

This test launches the hotspot settings app, verifies the hotspot is initially
stopped, clicks the "Start" button, then verifies the hotspot is running.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_hotspot_then_station.py
    Device:  ./tests/unittest.sh tests/test_graphical_hotspot_then_station.py --ondevice
"""

import unittest
import lvgl as lv
import mpos.ui
from mpos import AppManager, WifiService, wait_for_render, click_button, print_screen_labels


class TestGraphicalHotspotThenStation(unittest.TestCase):
    """Test hotspot start flow via the hotspot settings app."""

    def tearDown(self):
        """Clean up after each test method."""
        try:
            WifiService.disable_hotspot()
        except Exception:
            pass

        try:
            mpos.ui.back_screen()
            wait_for_render(5)
        except Exception:
            pass

    def test_hotspot_start_button_enables_hotspot(self):
        """Start the hotspot app and verify hotspot toggles on."""
        print("\n=== Starting hotspot start-flow test ===")

        WifiService.disable_hotspot()
        wait_for_render(5)

        result = AppManager.start_app("com.micropythonos.settings.hotspot")
        self.assertTrue(result, "Failed to start hotspot settings app")
        wait_for_render(iterations=20)

        screen = lv.screen_active()
        print("\nHotspot screen labels:")
        print_screen_labels(screen)

        self.assertFalse(
            WifiService.is_hotspot_enabled(),
            "Hotspot should be disabled before pressing Start",
        )

        WifiService.wifi_busy = False

        self.assertTrue(
            click_button("Start"),
            "Could not find Start button in hotspot app",
        )
        wait_for_render(iterations=20)

        self.assertTrue(
            WifiService.is_hotspot_enabled(),
            "Hotspot should be enabled after pressing Start",
        )

        print("\n=== Hotspot start-flow test completed ===")


if __name__ == "__main__":
    pass
