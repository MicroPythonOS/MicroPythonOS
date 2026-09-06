"""
test_graphical_appstore_row_tap.py - Verify taps anywhere on a store list row
open the app detail screen.

Each row registers a single CLICKED handler on the row item; taps on
non-clickable children (name/description labels) must fall through to it
through LVGL's normal input handling.

Usage:
    python3 scripts/test_runner.py tests/test_graphical_appstore_row_tap.py
"""

import unittest

import mpos
import mpos.ui

from mpos import App, AppManager
from mpos.ui.testing import wait_for_render, simulate_click, get_widget_coords


def _get_activity():
    activity, _, _, _ = mpos.ui.screen_stack[-1]
    return activity


def _make_app(i, name):
    return App(
        name,
        "TapTest",
        "Tap description %d" % i,
        "Long description for tap test app number %d." % i,
        None,
        None,
        "com.taptap.app%d" % i,
        "1.0",
        "Tools",
        [],
    )


class TestAppStoreRowTap(unittest.TestCase):

    def setUp(self):
        result = AppManager.start_app("com.micropythonos.appstore")
        self.assertTrue(result, "AppStore failed to launch")
        wait_for_render(40)
        self.activity = _get_activity()
        self.assertIsNotNone(self.activity, "Could not get AppStore activity")
        self.activity._icon_pipeline = "none"
        self.activity._selected_category = None
        self.activity.apps = [_make_app(0, "Zulu App"), _make_app(1, "Alpha App")]
        self.activity.create_apps_list()
        wait_for_render(20)

    def tearDown(self):
        try:
            while type(_get_activity()).__name__ == "AppDetail":
                mpos.ui.back_screen()
                wait_for_render(20)
        finally:
            mpos.ui.back_screen()
            wait_for_render(20)

    def _row_parts(self, row_index):
        item = self.activity.apps_list.get_child(row_index)
        label_cont = item.get_child(item.get_child_count() - 1)
        name_row = label_cont.get_child(0)
        desc_label = label_cont.get_child(1)
        name_label = name_row.get_child(0)
        return item, name_label, desc_label

    def _click_center(self, obj):
        coords = get_widget_coords(obj)
        self.assertIsNotNone(coords, "widget has no coordinates")
        simulate_click(coords["center_x"], coords["center_y"])
        wait_for_render(30)

    def test_tap_description_label_opens_detail(self):
        _, _, desc = self._row_parts(0)
        self.assertEqual(desc.get_text(), "Tap description 0")
        self._click_center(desc)
        self.assertEqual(type(_get_activity()).__name__, "AppDetail")

    def test_tap_name_label_opens_detail(self):
        _, name_label, _ = self._row_parts(1)
        self.assertEqual(name_label.get_text(), "Alpha App")
        self._click_center(name_label)
        self.assertEqual(type(_get_activity()).__name__, "AppDetail")


if __name__ == "__main__":
    unittest.main()
