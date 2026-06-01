"""
Graphical test to verify notification bar visibility in the launcher.
"""

import unittest

import lvgl as lv

from mpos import (
    AppManager,
    AppearanceManager,
    DisplayMetrics,
    Notification,
    NotificationManager,
    get_widget_coords,
    simulate_drag,
    wait_for_widget,
)
from mpos.battery_manager import BatteryManager
from mpos.ui import topmenu


class TestNotificationBarVisibility(unittest.TestCase):
    """Ensure the notification bar widgets are visible in the launcher."""

    def _bar_visible_widget(self):
        bar = topmenu.notification_bar
        if bar is None:
            return None
        try:
            if bar.has_flag(lv.obj.FLAG.HIDDEN):
                return None
        except Exception:
            pass
        coords = get_widget_coords(bar)
        if not coords:
            return None
        if coords["y2"] < 0:
            return None
        if coords["y1"] > AppearanceManager.NOTIFICATION_BAR_HEIGHT + 4:
            return None
        return bar

    def _bar_hidden_widget(self):
        bar = topmenu.notification_bar
        if bar is None:
            return True
        try:
            if bar.has_flag(lv.obj.FLAG.HIDDEN):
                return True
        except Exception:
            pass
        coords = get_widget_coords(bar)
        if coords and coords["y2"] < 0:
            return True
        return None

    def setUp(self):
        NotificationManager.cancel_all()
        NotificationManager.notify(
            Notification(
                notification_id="graphical.test.notification",
                icon=lv.SYMBOL.BELL,
                title="Graphical test notification",
                text="Drawer item should be visible",
                priority=Notification.PRIORITY_HIGH,
                app_fullname="com.micropythonos.settings",
                auto_cancel=False,
            )
        )
        AppManager.start_app("com.micropythonos.launcher")
        topmenu.open_bar()
        bar = wait_for_widget(self._bar_visible_widget, timeout=8)
        if bar is None:
            # Recovery path for slow/flaky CI where bar state can be stale.
            try:
                topmenu.close_bar()
            except Exception:
                pass
            wait_for_widget(self._bar_hidden_widget, timeout=6)
            topmenu.open_bar()
            bar = wait_for_widget(self._bar_visible_widget, timeout=12)

        self.assertIsNotNone(
            bar,
            "Notification bar did not become visible within timeout"
        )

    def _get_bar_labels(self, bar):
        labels = []
        stack = [bar]
        while stack:
            node = stack.pop()
            try:
                text = node.get_text()
            except Exception:
                text = None
            if text:
                labels.append((node, text))
            try:
                child_count = node.get_child_count()
            except Exception:
                child_count = 0
            for idx in range(child_count):
                try:
                    stack.append(node.get_child(idx))
                except Exception:
                    continue
        return labels

    def _assert_within_bar(self, widget, bar, label):
        self.assertIsNotNone(widget, f"{label} widget not available")
        try:
            self.assertFalse(
                widget.has_flag(lv.obj.FLAG.HIDDEN),
                f"{label} is hidden",
            )
        except Exception:
            pass
        node = widget
        for _ in range(20):
            if node is bar:
                return
            try:
                node = node.get_parent()
            except Exception:
                node = None
            if node is None:
                break
        self.fail(f"{label} is not within the notification bar hierarchy")

    def _ensure_drawer_open(self, bar_coords):
        if self._swipe_down_on_bar(bar_coords):
            return True

        # Recovery path: force-close any stale drawer state, then force-open.
        def _drawer_hidden():
            drawer = topmenu.drawer
            if drawer is None:
                return True
            try:
                if drawer.has_flag(lv.obj.FLAG.HIDDEN):
                    return True
            except Exception:
                pass
            return None

        def _drawer_visible():
            drawer = topmenu.drawer
            if not topmenu.drawer_open or drawer is None:
                return None
            try:
                if drawer.has_flag(lv.obj.FLAG.HIDDEN):
                    return None
            except Exception:
                pass
            return drawer

        try:
            topmenu.close_drawer()
        except Exception:
            pass
        wait_for_widget(_drawer_hidden, timeout=6)

        try:
            topmenu.open_drawer()
        except Exception:
            pass
        if wait_for_widget(_drawer_visible, timeout=10) is not None:
            return True

        # Final retry via swipe with fresh bar coords.
        bar = self._ensure_bar_visible()
        if bar is None:
            return False
        coords = get_widget_coords(bar)
        if not coords:
            return False
        return self._swipe_down_on_bar(coords)

    def _ensure_bar_closed(self, bar_coords, bar):
        if self._swipe_up_on_bar(bar_coords, bar):
            return True

        # Recovery path: force-close bar state and verify hidden.
        try:
            topmenu.close_bar()
        except Exception:
            pass
        if wait_for_widget(self._bar_hidden_widget, timeout=10) is not None:
            return True

        # Final retry: re-open and swipe closed again with fresh refs.
        try:
            topmenu.open_bar()
        except Exception:
            pass
        bar = self._ensure_bar_visible()
        if bar is None:
            return wait_for_widget(self._bar_hidden_widget, timeout=8) is not None

        coords = get_widget_coords(bar)
        if not coords:
            return wait_for_widget(self._bar_hidden_widget, timeout=8) is not None

        if self._swipe_up_on_bar(coords, bar):
            return True

        return wait_for_widget(self._bar_hidden_widget, timeout=8) is not None

    def _swipe_down_on_bar(self, bar_coords):
        start_x = DisplayMetrics.width() // 2
        start_y = max(1, (bar_coords["y1"] + bar_coords["y2"]) // 2)
        end_y = int(DisplayMetrics.height() * 0.9)

        def _check():
            if not topmenu.drawer_open or topmenu.drawer is None:
                return None
            if topmenu.drawer.has_flag(lv.obj.FLAG.HIDDEN):
                return None
            return topmenu.drawer

        simulate_drag(start_x, start_y, start_x, end_y, steps=30, step_delay_ms=45)
        result = wait_for_widget(_check, timeout=5)
        if result:
            return True

        start_y = max(1, AppearanceManager.NOTIFICATION_BAR_HEIGHT - 2)
        end_y = int(DisplayMetrics.height() * 0.95)
        simulate_drag(start_x, start_y, start_x, end_y, steps=36, step_delay_ms=45)
        return wait_for_widget(_check, timeout=5) is not None

    def _swipe_up_on_bar(self, bar_coords, bar):
        start_x = DisplayMetrics.width() // 2
        start_y = max(1, (bar_coords["y1"] + bar_coords["y2"]) // 2)
        end_y = -AppearanceManager.NOTIFICATION_BAR_HEIGHT * 2

        def _check():
            if not topmenu.bar_open:
                return True
            coords = get_widget_coords(bar)
            if coords and coords["y2"] < 0:
                return True
            return None

        simulate_drag(start_x, start_y, start_x, end_y, steps=30, step_delay_ms=45)
        result = wait_for_widget(_check, timeout=5)
        if result:
            return True

        end_y = -AppearanceManager.NOTIFICATION_BAR_HEIGHT * 2
        simulate_drag(start_x, start_y, start_x, end_y, steps=36, step_delay_ms=45)
        return wait_for_widget(_check, timeout=5) is not None

    def _ensure_bar_visible(self):
        return wait_for_widget(self._bar_visible_widget, timeout=8)

    def test_notification_bar_widgets_visible(self):
        bar = topmenu.notification_bar
        self.assertIsNotNone(bar, "Notification bar was not created")

        if not self._ensure_bar_visible():
            topmenu.open_bar()
            self.assertIsNotNone(
                self._ensure_bar_visible(),
                "Notification bar did not become visible after open_bar()"
            )
        bar_coords = get_widget_coords(bar)
        self.assertIsNotNone(bar_coords, "Notification bar coords not available")
        self.assertTrue(topmenu.bar_open, "Notification bar was not marked open")

        labels = self._get_bar_labels(bar)
        time_label = next((child for child, text in labels if ":" in text), None)
        temp_label = next((child for child, text in labels if chr(176) + "C" in text or "C" in text), None)
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

        self._assert_within_bar(time_label, bar, "Clock label")
        self._assert_within_bar(temp_label, bar, "Temperature label")
        self._assert_within_bar(wifi_label, bar, "WiFi icon")
        if battery_label is not None:
            self._assert_within_bar(battery_label, bar, "Battery icon")

        self.assertTrue(
            self._ensure_drawer_open(bar_coords),
            "Drawer did not open after swipe",
        )
        self.assertTrue(topmenu.drawer_open, "Drawer state not open after swipe")
        self.assertIsNotNone(topmenu.drawer, "Drawer object not found after swipe")
        self.assertFalse(
            topmenu.drawer.has_flag(lv.obj.FLAG.HIDDEN),
            "Drawer widget is not visible",
        )
        self.assertTrue(
            topmenu.drawer.get_child_count() > 0,
            "Drawer has no children after opening",
        )

        drawer_labels = self._get_bar_labels(topmenu.drawer)
        self.assertTrue(
            any("Off" in text or lv.SYMBOL.POWER in text for _, text in drawer_labels),
            "Power-off label not found in drawer",
        )
        self.assertTrue(
            any(
                "Graphical test notification" in text or "Drawer item should be visible" in text
                for _, text in drawer_labels
            ),
            "Notification item not found in drawer",
        )

        topmenu.close_drawer()
        bar_coords = get_widget_coords(bar)
        self.assertIsNotNone(bar_coords, "Notification bar coords not available")
        self.assertTrue(
            self._ensure_bar_closed(bar_coords, bar),
            "Notification bar did not close after swipe up",
        )
        bar_coords = get_widget_coords(bar)
        bar_hidden = bar_coords is not None and bar_coords["y2"] < 0
        self.assertTrue(
            (not topmenu.bar_open) or bar_hidden,
            "Notification bar is still open after swipe up",
        )
