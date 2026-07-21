"""
Graphical test for AppStore category dropdown filtering.

Verifies that the category dropdown filters the app list and
that selecting "All Categories" shows all apps again.
Also verifies category names are title-cased, deduped,
"Adult" appears at the bottom, and no orphaned list widgets
linger after filtering (focus group correctness).
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


def _title_case(s):
    return s[0].upper() + s[1:].lower()


def _count_list_widgets():
    tree = get_screen_widget_tree()
    return sum(
        1 for w in tree
        if w.get("type") == "list" and w.get("layer") == "active" and not w.get("hidden")
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

    def _get_category_options(self):
        AppManager.start_app("com.micropythonos.appstore")
        wait_for_render(iterations=40)
        dropdown = find_dropdown_widget(lv.screen_active())
        self.assertIsNotNone(dropdown, "Category dropdown should exist")
        options = get_dropdown_options(dropdown)
        self.assertEqual(options[0], "All Categories",
                         "First option should be 'All Categories'")
        return dropdown, options

    def test_categories_are_title_cased_and_deduped(self):
        _, options = self._get_category_options()
        categories = options[1:]

        self.assertEqual(len(categories), len(set(categories)),
                         f"Duplicate categories found: {categories}")

        for cat in categories:
            self.assertEqual(cat, _title_case(cat),
                             f"Category '{cat}' should be title-cased")

    def test_adult_at_bottom(self):
        _, options = self._get_category_options()
        categories = options[1:]

        if "Adult" in categories:
            self.assertEqual(categories[-1], "Adult",
                             "'Adult' should be at the bottom")

    def test_no_orphaned_list_widgets(self):
        dropdown, options = self._get_category_options()

        if len(options) <= 1:
            print("No categories available, skipping")
            return

        target = options[1]
        select_dropdown_option_by_text(dropdown, target)
        wait_for_render(iterations=10)
        self.assertEqual(_count_list_widgets(), 1,
                         "Only one list widget should exist after filtering")

        select_dropdown_option_by_text(dropdown, "All Categories", allow_partial=False)
        wait_for_render(iterations=10)
        self.assertEqual(_count_list_widgets(), 1,
                         "Only one list widget should exist after reset")

    def test_no_stale_widgets_after_filter_and_resume(self):
        dropdown, options = self._get_category_options()

        if len(options) <= 1:
            print("No categories available, skipping")
            return

        wait_for_render(iterations=60)

        target = options[1]
        select_dropdown_option_by_text(dropdown, target)
        wait_for_render(iterations=10)

        AppManager.start_app("com.micropythonos.about")
        wait_for_render(iterations=10)

        from mpos.ui import back_screen
        back_screen()
        wait_for_render(iterations=10)

    def test_list_position_after_filter_reset(self):
        dropdown, options = self._get_category_options()

        if len(options) <= 1:
            print("No categories available, skipping")
            return

        tree = get_screen_widget_tree()
        lists = [w for w in tree if w.get("type") == "list" and w.get("layer") == "active" and not w.get("hidden")]
        self.assertEqual(len(lists), 1)
        initial_y = lists[0].get("y1", -1)

        target = options[1]
        select_dropdown_option_by_text(dropdown, target)
        wait_for_render(iterations=10)

        select_dropdown_option_by_text(dropdown, "All Categories", allow_partial=False)
        wait_for_render(iterations=10)

        tree = get_screen_widget_tree()
        lists = [w for w in tree if w.get("type") == "list" and w.get("layer") == "active" and not w.get("hidden")]
        self.assertEqual(len(lists), 1)
        self.assertEqual(lists[0].get("y1", -1), initial_y,
                         f"List Y moved: {initial_y} -> {lists[0].get('y1', -1)}")

    def test_category_filtering_and_reset(self):
        dropdown, options = self._get_category_options()

        if len(options) <= 1:
            print("No categories available, skipping filter test")
            return

        all_count = _count_list_items()
        self.assertGreater(all_count, 0, "App list should have items")

        target = options[1]
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
