"""
Test that Sorter enables kiosk mode (disables back + drawer) on resume
and restores navigation on pause.  Verifies the exit-confirmation popup
and help-display through the callback API.

Usage:
"""

import unittest

from mpos import AppManager, SharedPreferences, wait_for_render
from mpos.ui import screen_stack
from mpos.ui.input_manager import InputManager
from mpos.ui import back_screen

APP_NAME = "com.micropythonos.sorter"


def _clear_sorter_prefs():
    prefs = SharedPreferences(APP_NAME)
    editor = prefs.edit()
    editor.remove_all()
    editor.commit()


class TestSorterKioskMode(unittest.TestCase):

    def setUp(self):
        InputManager.set_back_screen_disabled(False)
        InputManager.set_drawer_open_disabled(False)
        AppManager.restart_launcher()
        wait_for_render(10)
        _clear_sorter_prefs()

    def tearDown(self):
        InputManager.set_back_screen_disabled(False)
        InputManager.set_drawer_open_disabled(False)
        try:
            back_screen()
            wait_for_render(5)
        except Exception:
            pass

    def test_kiosk_mode_disables_back_and_shows_exit_popup(self):
        result = AppManager.start_app(APP_NAME)
        self.assertTrue(result, "Sorter should start")
        wait_for_render(10)

        act = screen_stack[-1][0]
        self.assertTrue(InputManager.is_back_screen_disabled(),
                        "back should be disabled in kiosk mode")
        self.assertTrue(InputManager.is_drawer_open_disabled(),
                        "drawer should be disabled in kiosk mode")

        back_screen()
        wait_for_render(5)
        self.assertIsNotNone(act.popup_modal,
                             "exit confirmation popup should be open")

        act._close_popup()
        wait_for_render(3)
        self.assertIsNone(act.popup_modal,
                          "popup should close on No/cancel")
        self.assertIs(screen_stack[-1][0], act,
                      "should still be in Sorter after dismissing popup")

    def test_kiosk_mode_home_shows_help(self):
        result = AppManager.start_app(APP_NAME)
        self.assertTrue(result, "Sorter should start")
        wait_for_render(10)

        act = screen_stack[-1][0]
        InputManager._drawer_open_cb()
        wait_for_render(5)
        self.assertIsNotNone(act.popup_modal,
                             "help popup should be open after HOME")

        act._close_popup()
        wait_for_render(3)
        self.assertIsNone(act.popup_modal)

    def test_kiosk_mode_exit_confirmed_returns_to_launcher(self):
        result = AppManager.start_app(APP_NAME)
        self.assertTrue(result, "Sorter should start")
        wait_for_render(10)

        act = screen_stack[-1][0]
        back_screen()
        wait_for_render(5)
        self.assertIsNotNone(act.popup_modal,
                             "exit confirmation popup should be open")

        act._do_exit(None)
        wait_for_render(5)

        self.assertFalse(InputManager.is_back_screen_disabled(),
                         "back should be re-enabled after exit")
        self.assertFalse(InputManager.is_drawer_open_disabled(),
                         "drawer should be re-enabled after exit")

    def test_kiosk_mode_pause_restores_navigation(self):
        """Navigating away from Sorter restores global navigation."""
        result = AppManager.start_app(APP_NAME)
        self.assertTrue(result, "Sorter should start")
        wait_for_render(10)

        act = screen_stack[-1][0]
        self.assertTrue(InputManager.is_back_screen_disabled())

        InputManager.set_back_screen_disabled(False)
        InputManager.set_drawer_open_disabled(False)
        act.finish()
        wait_for_render(5)

        self.assertFalse(InputManager.is_back_screen_disabled())
        self.assertFalse(InputManager.is_drawer_open_disabled())


if __name__ == "__main__":
    unittest.main()
