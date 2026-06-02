"""
Graphical tests for the notification bar (top menu bar).

Covers:
- Bar is hidden on a plain app, visible in the launcher
- open_bar() / close_bar() API changes the visible state
- Bar is NOT clickable and NOT in the focus group
- Bar widgets (clock, wifi, bell) are present after open
"""

import time
import unittest

import lvgl as lv

from mpos import (
    AppManager,
    AppearanceManager,
    get_widget_coords,
    wait_for_widget,
)
from mpos.ui import topmenu


# ---------------------------------------------------------------------------
# Helpers shared across test cases
# ---------------------------------------------------------------------------

def _wait_ms(ms):
    """Busy-wait using ticks so it works on both desktop and device."""
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        lv.task_handler()
        time.sleep(0.01)


def _bar_y2(bar):
    """Return the current y2 coordinate of the bar widget, or None."""
    coords = get_widget_coords(bar)
    return coords["y2"] if coords else None


def _bar_is_on_screen(bar):
    """Return True when the bar's bottom edge is at/above the bar height (i.e. visible)."""
    y2 = _bar_y2(bar)
    if y2 is None:
        return False
    return y2 >= AppearanceManager.NOTIFICATION_BAR_HEIGHT - 2


def _bar_is_off_screen(bar):
    """Return True when the bar has been scrolled fully above y=0."""
    y2 = _bar_y2(bar)
    if y2 is None:
        return True
    return y2 < 0


# ---------------------------------------------------------------------------

class TestNotificationBarOpenClose(unittest.TestCase):
    """Verify that open_bar / close_bar move the bar in and out of view."""

    def setUp(self):
        AppManager.start_app("com.micropythonos.launcher")
        _wait_ms(500)
        # Start from a known closed state.
        if topmenu.bar_open:
            topmenu.close_bar(animate=False)
        bar = topmenu.notification_bar
        self.assertIsNotNone(bar, "notification_bar not created")
        wait_for_widget(lambda: bar if _bar_is_off_screen(bar) else None, timeout=6)

    def test_open_bar_makes_bar_visible(self):
        """open_bar() should bring the bar into the visible viewport."""
        topmenu.open_bar()
        bar = topmenu.notification_bar
        result = wait_for_widget(lambda: bar if _bar_is_on_screen(bar) else None, timeout=8)
        self.assertIsNotNone(result, "Bar did not become visible after open_bar()")
        self.assertTrue(topmenu.bar_open, "bar_open flag not set after open_bar()")

    def test_close_bar_hides_bar(self):
        """close_bar() should move the bar above the top edge."""
        topmenu.open_bar()
        bar = topmenu.notification_bar
        wait_for_widget(lambda: bar if _bar_is_on_screen(bar) else None, timeout=8)

        topmenu.close_bar(animate=False)
        result = wait_for_widget(lambda: bar if _bar_is_off_screen(bar) else None, timeout=8)
        self.assertIsNotNone(result, "Bar did not hide after close_bar()")
        self.assertFalse(topmenu.bar_open, "bar_open flag still set after close_bar()")

    def test_open_bar_idempotent(self):
        """Calling open_bar() twice should not raise and should keep bar visible."""
        topmenu.open_bar()
        topmenu.open_bar()  # second call is a no-op
        bar = topmenu.notification_bar
        result = wait_for_widget(lambda: bar if _bar_is_on_screen(bar) else None, timeout=8)
        self.assertIsNotNone(result, "Bar not visible after double open_bar()")
        self.assertTrue(topmenu.bar_open)

    def test_close_bar_idempotent(self):
        """Calling close_bar() when already closed should not raise."""
        # Already closed from setUp
        self.assertFalse(topmenu.bar_open)
        topmenu.close_bar(animate=False)  # should be a no-op
        self.assertFalse(topmenu.bar_open)


class TestNotificationBarNotFocusable(unittest.TestCase):
    """Verify that the notification bar is not in the focus group and not clickable."""

    def setUp(self):
        AppManager.start_app("com.micropythonos.launcher")
        _wait_ms(500)
        topmenu.open_bar()
        bar = topmenu.notification_bar
        wait_for_widget(lambda: bar if _bar_is_on_screen(bar) else None, timeout=8)

    def test_bar_not_clickable(self):
        """notification_bar must not have the CLICKABLE flag."""
        bar = topmenu.notification_bar
        self.assertIsNotNone(bar)
        self.assertFalse(
            bar.has_flag(lv.obj.FLAG.CLICKABLE),
            "notification_bar should not be clickable",
        )

    def test_bar_not_in_focus_group(self):
        """notification_bar must not be registered in the default LVGL focus group."""
        bar = topmenu.notification_bar
        self.assertIsNotNone(bar)
        group = lv.group_get_default()
        if group is None:
            return  # no focus group — trivially not in it
        for i in range(group.get_obj_count()):
            obj = group.get_obj_by_index(i)
            self.assertIsNot(
                obj, bar,
                "notification_bar must not be in the default focus group",
            )


class TestNotificationBarWidgets(unittest.TestCase):
    """Verify the clock and status-icon labels are present inside the bar."""

    def setUp(self):
        AppManager.start_app("com.micropythonos.launcher")
        _wait_ms(500)
        topmenu.open_bar()
        bar = topmenu.notification_bar
        wait_for_widget(lambda: bar if _bar_is_on_screen(bar) else None, timeout=8)

    def _collect_label_texts(self, root):
        texts = []
        stack = [root]
        while stack:
            node = stack.pop()
            try:
                t = node.get_text()
                if t:
                    texts.append(t)
            except Exception:
                pass
            try:
                for i in range(node.get_child_count()):
                    stack.append(node.get_child(i))
            except Exception:
                pass
        return texts

    def test_clock_label_present(self):
        """A label containing ':' (HH:MM:SS) should be inside the bar."""
        bar = topmenu.notification_bar
        texts = self._collect_label_texts(bar)
        clock = next((t for t in texts if ":" in t), None)
        self.assertIsNotNone(clock, f"No clock label found in bar. Labels: {texts}")

    def test_bar_height_matches_appearance_manager(self):
        """The bar widget height must equal AppearanceManager.NOTIFICATION_BAR_HEIGHT.

        get_widget_coords returns height = y2 - y1 which is one less than the actual
        pixel height because LVGL area coordinates are inclusive on both ends.
        """
        bar = topmenu.notification_bar
        coords = get_widget_coords(bar)
        self.assertIsNotNone(coords)
        # LVGL area coords are inclusive: height in pixels = (y2 - y1) + 1
        actual_h = coords["height"] + 1
        expected_h = AppearanceManager.NOTIFICATION_BAR_HEIGHT
        self.assertEqual(
            actual_h, expected_h,
            f"Bar height {actual_h} != AppearanceManager.NOTIFICATION_BAR_HEIGHT {expected_h}",
        )
