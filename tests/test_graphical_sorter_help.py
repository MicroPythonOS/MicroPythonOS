"""
Test that Sorter's help button shows solution moves.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_sorter_help.py
"""

import time
import unittest

from mpos import AppManager, SharedPreferences, wait_for_render
from mpos.ui import screen_stack
from mpos.ui.testing import find_label_with_text
import lvgl as lv

APP_NAME = "com.micropythonos.sorter"


def _clear_sorter_prefs():
    prefs = SharedPreferences(APP_NAME)
    editor = prefs.edit()
    editor.remove_all()
    editor.commit()


class TestSorterHelp(unittest.TestCase):

    def setUp(self):
        AppManager.restart_launcher()
        wait_for_render(10)
        _clear_sorter_prefs()

    def tearDown(self):
        try:
            from mpos import ui
            ui.back_screen()
            wait_for_render(5)
        except Exception:
            pass

    def test_help_shows_solution_moves(self):
        result = AppManager.start_app(APP_NAME)
        self.assertTrue(result, "Sorter should start")
        wait_for_render(10)

        act = screen_stack[-1][0]
        self.assertTrue(len(act.shuffle_moves) > 0,
                        "shuffle_moves should not be empty")
        self.assertEqual(len(act.tubes), 4,
                         "Level 1 should have 4 tubes (2 filled + 2 extra)")

        act.on_help(None)
        wait_for_render(5)

        self.assertIsNotNone(act.popup_modal, "Help msgbox should be open")

        act._close_popup()
        wait_for_render(3)
        self.assertIsNone(act.popup_modal, "Help msgbox should be closed")

    def test_help_button_exists(self):
        result = AppManager.start_app(APP_NAME)
        self.assertTrue(result, "Sorter should start")
        wait_for_render(10)

        help_label = find_label_with_text(lv.screen_active(), "?")
        self.assertIsNotNone(help_label, "Help button ('?') should be on screen")


if __name__ == "__main__":
    unittest.main()
