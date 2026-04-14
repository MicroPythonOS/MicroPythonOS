"""
Graphical test to verify notification bar visibility in the launcher.
"""

import time
import unittest

import lvgl as lv

from mpos import AppManager, AppearanceManager, get_widget_coords, wait_for_render
from mpos.battery_manager import BatteryManager
from mpos.ui import topmenu


class TestNotificationBarVisibility(unittest.TestCase):
    """Ensure the notification bar widgets are visible in the launcher."""

    def setUp(self):
        AppManager.start_app("com.micropythonos.launcher")
        topmenu.open_bar()
        self._wait_for_bar_visible()

    def _wait_for_bar_visible(self, timeout_ms=2500):
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < timeout_ms:
            bar = topmenu.notification_bar
            if bar is not None:
                bar_coords = get_widget_coords(bar)
                if bar_coords and bar_coords["y1"] >= 0:
                    return
            wait_for_render(iterations=10)
        wait_for_render(iterations=50)

    def _get_bar_labels(self, bar):
        labels = []
        try:
            child_count = bar.get_child_count()
        except Exception:
            child_count = 0
        for idx in range(child_count):
            child = bar.get_child(idx)
            try:
                text = child.get_text()
            except Exception:
                continue
            labels.append((child, text))
        return labels

    def _assert_within_bar(self, widget, bar_coords, label):
        coords = get_widget_coords(widget)
        self.assertIsNotNone(coords, f"{label} coords not available")
        self.assertGreaterEqual(
            coords["y1"],
            bar_coords["y1"],
            f"{label} is above the notification bar",
        )
        self.assertLessEqual(
            coords["y2"],
            bar_coords["y2"],
            f"{label} is below the notification bar",
        )

    def test_notification_bar_widgets_visible(self):
        bar = topmenu.notification_bar
        self.assertIsNotNone(bar, "Notification bar was not created")

        bar_coords = get_widget_coords(bar)
        self.assertIsNotNone(bar_coords, "Notification bar coords not available")
        self.assertGreaterEqual(
            bar_coords["y1"],
            -1,
            "Notification bar is not visible (y position is too high)",
        )
        self.assertGreaterEqual(
            bar_coords["y2"],
            AppearanceManager.NOTIFICATION_BAR_HEIGHT - 1,
            "Notification bar height is smaller than expected",
        )

        labels = self._get_bar_labels(bar)
        time_label = next((child for child, text in labels if ":" in text), None)
        temp_label = next((child for child, text in labels if "°C" in text), None)
        wifi_label = next((child for child, text in labels if text == lv.SYMBOL.WIFI), None)

        battery_symbols = {
            lv.SYMBOL.BATTERY_FULL,
            lv.SYMBOL.BATTERY_3,
            lv.SYMBOL.BATTERY_2,
            lv.SYMBOL.BATTERY_1,
            lv.SYMBOL.BATTERY_EMPTY,
        }
        battery_label = next((child for child, text in labels if text in battery_symbols), None)

        self.assertIsNotNone(time_label, "Clock label not found in notification bar")
        self.assertIsNotNone(temp_label, "Temperature label not found in notification bar")
        self.assertIsNotNone(wifi_label, "WiFi icon not found in notification bar")
        if BatteryManager.has_battery():
            self.assertIsNotNone(battery_label, "Battery icon not found in notification bar")

        self._assert_within_bar(time_label, bar_coords, "Clock label")
        self._assert_within_bar(temp_label, bar_coords, "Temperature label")
        self._assert_within_bar(wifi_label, bar_coords, "WiFi icon")
        if battery_label is not None:
            self._assert_within_bar(battery_label, bar_coords, "Battery icon")
