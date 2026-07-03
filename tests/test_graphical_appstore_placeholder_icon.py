"""
Graphical test for the AppStore generated placeholder icon.

Verifies that when an app has no icon_data, AppStore renders the generated
SHA1-based placeholder as a visible, non-white image rather than a blank/white
square.  This exercises the raw RGB565 image descriptor path used by
AppStore._generate_raw_app_icon.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_appstore_placeholder_icon.py
    Device:  ./tests/unittest.sh tests/test_graphical_appstore_placeholder_icon.py --ondevice
"""

import time
import unittest

import lvgl as lv
import mpos
import mpos.ui

from mpos import App, AppManager
from mpos.ui.testing import capture_screenshot, get_screen_widget_tree, wait_for_render


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wait_ms(ms):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        lv.task_handler()
        time.sleep(0.01)


def _get_appstore_activity():
    if not mpos.ui.screen_stack:
        return None
    activity, _, _, _ = mpos.ui.screen_stack[-1]
    return activity


def _inject_fake_apps(activity):
    """Populate activity.apps with two dummy entries and rebuild the list."""
    activity.apps = [
        App("Alpha App", "Test", "Short desc", "Long desc",
            None, "http://example.com/a.mpk", "com.test.alpha", "1.0.0", "test", []),
        App("Beta App", "Test", "Short desc", "Long desc",
            None, "http://example.com/b.mpk", "com.test.beta", "1.0.0", "test", []),
    ]
    activity.create_apps_list()
    _wait_ms(200)


def _is_icon(widget):
    """Return True for an image widget roughly 64x64 located below the top bar."""
    if widget.get("type") != "image":
        return False
    return widget.get("w", 0) >= 60 and widget.get("h", 0) >= 60 and widget.get("y1", 0) > 30


def _find_icons(tree):
    """Recursively collect icon widgets from a widget tree dump."""
    icons = []
    stack = list(tree)
    while stack:
        node = stack.pop()
        if _is_icon(node):
            icons.append(node)
        stack.extend(node.get("children") or [])
    return icons


def _pixel_rgb565(buf, width, x, y):
    """Return the RGB565 value at (x, y) from a raw RGB565 screenshot buffer."""
    i = (y * width + x) * 2
    return buf[i] | (buf[i + 1] << 8)


# ---------------------------------------------------------------------------


class TestAppStorePlaceholderIcon(unittest.TestCase):
    """Verify the generated AppStore placeholder icon renders visibly."""

    def setUp(self):
        result = AppManager.start_app("com.micropythonos.appstore")
        self.assertTrue(result, "AppStore failed to launch")
        wait_for_render(20)
        activity = _get_appstore_activity()
        self.assertIsNotNone(activity, "Could not get AppStore activity instance")
        _inject_fake_apps(activity)

    def tearDown(self):
        mpos.ui.back_screen()
        _wait_ms(200)

    # ------------------------------------------------------------------

    def test_placeholder_icon_is_not_white(self):
        """Generated placeholder icons must contain at least one non-white pixel."""
        icons = _find_icons(get_screen_widget_tree(lv.screen_active()))
        self.assertTrue(len(icons) >= 2, "Expected at least two app icons on screen")

        buf = capture_screenshot(width=320, height=240)
        white = 0xFFFF
        for icon in icons:
            cx = (icon["x1"] + icon["x2"]) // 2
            cy = (icon["y1"] + icon["y2"]) // 2
            center = _pixel_rgb565(buf, 320, cx, cy)
            self.assertNotEqual(center, white,
                                "Placeholder icon center is pure white")

    def test_placeholder_icons_differ_between_apps(self):
        """Different app names must produce visibly different placeholders."""
        icons = _find_icons(get_screen_widget_tree(lv.screen_active()))
        self.assertTrue(len(icons) >= 2, "Expected at least two app icons on screen")

        buf = capture_screenshot(width=320, height=240)
        values = []
        for icon in icons[:2]:
            cx = (icon["x1"] + icon["x2"]) // 2
            cy = (icon["y1"] + icon["y2"]) // 2
            values.append(_pixel_rgb565(buf, 320, cx, cy))
        self.assertNotEqual(values[0], values[1],
                            "Two different app names produced identical placeholder pixels")
