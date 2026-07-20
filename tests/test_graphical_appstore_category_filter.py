"""
Graphical test for AppStore category dropdown filtering.

Verifies that the category dropdown filters the app list and
that selecting "All Categories" shows all apps again.
Also verifies category names are title-cased and consistent.
"""

import unittest

import lvgl as lv

from mpos import AppManager
from mpos.ui.testing import (
    find_dropdown_widget,
    get_dropdown_options,
    get_screen_widget_tree,
    select_dropdown_option_by_text,
    wait_for_render,
)


def _count_list_items():
    tree = get_screen_widget_tree()
    for widget in tree:
        if widget.get("type") == "list" and widget.get("layer") == "active":
            return len(widget.get("children", []))
    return 0


class TestGraphicalAppStoreCategoryFilter(unittest.TestCase):

    def setUp(self):
        AppManager.refresh_apps()

    def tearDown(self):
        try:
            from mpos.ui import back_screen
            back_screen()
        except Exception:
            pass

    def test_category_filtering_and_reset(self):
        AppManager.start_app("com.micropythonos.appstore")
        wait_for_render(iterations=40)

        dropdown = find_dropdown_widget(lv.screen_active())
        self.assertIsNotNone(dropdown, "Category dropdown should exist")

        options = get_dropdown_options(dropdown)
        self.assertEqual(options[0], "All Categories",
                         "First option should be 'All Categories'")

        if len(options) <= 1:
            print("No categories available, skipping filter test")
            return

        all_count = _count_list_items()
        self.assertGreater(all_count, 0, "App list should have items")

        target = options[1]
        self.assertEqual(target, target[0].upper() + target[1:].lower(),
                         f"Category '{target}' should be title-cased")

        result = select_dropdown_option_by_text(dropdown, target)
        self.assertTrue(result, f"Should select category '{target}'")
        wait_for_render(iterations=10)

        filtered_count = _count_list_items()
        self.assertLessEqual(filtered_count, all_count,
                            f"Filtered count {filtered_count} > all {all_count}")

        result = select_dropdown_option_by_text(dropdown, "All Categories", allow_partial=False)
        self.assertTrue(result, "Should select 'All Categories' to reset")
        wait_for_render(iterations=10)

        reset_count = _count_list_items()
        self.assertEqual(reset_count, all_count,
                         f"Reset count {reset_count} != original {all_count}")
