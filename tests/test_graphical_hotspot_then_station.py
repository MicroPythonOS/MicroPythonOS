"""
Graphical test for enabling hotspot from the Hotspot Settings app.

This test launches the hotspot settings app, verifies the hotspot is initially
stopped, clicks the "Start" button, then verifies the hotspot is running.

Usage:
"""

import unittest
import lvgl as lv
import mpos.ui
from mpos import (
    AppManager,
    WifiService,
    wait_for_text,
    wait_for_widget,
    click_button,
    print_screen_labels,
    get_widget_coords,
    simulate_click,
)


class TestGraphicalHotspotThenStation(unittest.TestCase):
    """Test hotspot start flow via the hotspot settings app."""

    def _first_text_in_tree(self, node):
        try:
            if hasattr(node, "get_text"):
                text = node.get_text()
                if text:
                    return text
        except Exception:
            pass

        try:
            child_count = node.get_child_count()
        except Exception:
            return None

        for i in range(child_count):
            text = self._first_text_in_tree(node.get_child(i))
            if text:
                return text
        return None

    def _find_first_list_item(self, screen):
        def find_list(node):
            try:
                if node.__class__.__name__ == "list":
                    return node
            except Exception:
                pass
            try:
                if hasattr(node, "add_button") and hasattr(node, "get_child_count"):
                    return node
            except Exception:
                pass
            try:
                child_count = node.get_child_count()
            except Exception:
                child_count = 0
            for i in range(child_count):
                child = node.get_child(i)
                found = find_list(child)
                if found:
                    return found
            return None

        wifi_list = find_list(screen)
        if wifi_list is None:
            return None
        try:
            child_count = wifi_list.get_child_count()
            if child_count < 1:
                return None

            for idx in range(child_count):
                child = wifi_list.get_child(idx)
                text = self._first_text_in_tree(child)
                if not text:
                    continue
                if text == "Add network":
                    continue
                if "Scanning" in text:
                    continue
                if "ERROR TEXT" in text:
                    continue
                return child

            return None
        except Exception:
            return None

    def tearDown(self):
        """Clean up after each test method."""
        try:
            WifiService.disable_hotspot()
        except Exception:
            pass

        try:
            mpos.ui.back_screen()
        except Exception:
            pass

    def test_hotspot_start_button_enables_hotspot(self):
        """Start the hotspot app and verify hotspot toggles on."""
        print("\n=== Starting hotspot start-flow test ===")

        WifiService.disable_hotspot()

        result = AppManager.start_app("com.micropythonos.settings.hotspot")
        self.assertTrue(result, "Failed to start hotspot settings app")
        self.assertTrue(
            wait_for_text("Start", timeout=10),
            "Hotspot app did not load within timeout",
        )

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

        self.assertTrue(
            WifiService.is_hotspot_enabled(),
            "Hotspot should be enabled after pressing Start",
        )

        result = AppManager.start_app("com.micropythonos.settings.wifi")
        self.assertTrue(result, "Failed to start WiFi settings app")
        self.assertTrue(
            wait_for_text("Scanning", timeout=10) or wait_for_text("WiFi", timeout=10),
            "WiFi settings app did not load within timeout",
        )

        screen = lv.screen_active()
        print("\nWiFi screen labels (before scan wait):")
        print_screen_labels(screen)

        print("\nWaiting for first discovered access point...")
        first_item = wait_for_widget(
            lambda: self._find_first_list_item(lv.screen_active()),
            timeout=25,
        )

        screen = lv.screen_active()
        print("\nWiFi screen labels (after scan wait):")
        print_screen_labels(screen)

        self.assertIsNotNone(first_item, "Could not find first WiFi access point")

        coords = get_widget_coords(first_item)
        if coords:
            print(f"Clicking first WiFi access point at ({coords['center_x']}, {coords['center_y']})")
            first_item.send_event(lv.EVENT.CLICKED, None)
        else:
            first_item.send_event(lv.EVENT.CLICKED, None)

        self.assertTrue(
            wait_for_text("Connect", timeout=10),
            "Connect button did not appear after selecting access point",
        )

        self.assertTrue(
            click_button("Connect"),
            "Could not find Connect button in WiFi edit screen",
        )

        self.assertFalse(
            WifiService.is_hotspot_enabled(),
            "Hotspot should be disabled after connecting to a WiFi access point",
        )

        print("\n=== Hotspot start-flow test completed ===")


if __name__ == "__main__":
    pass
