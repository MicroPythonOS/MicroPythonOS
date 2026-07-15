"""
Test that Sorter persists its shuffled emoji order across restarts and new games.

This test verifies that:
- The emoji order is randomized per new game.
- Restarting the current level keeps the same emoji order.
- Starting a new game generates a different emoji order.

Usage:
"""

import unittest

import lvgl as lv

from mpos import AppManager, SharedPreferences, wait_for_render
from mpos.ui import screen_stack
from mpos.ui.testing import click_button, find_label_on_any_layer


APP_NAME = "com.micropythonos.sorter"


def _clear_sorter_prefs():
    prefs = SharedPreferences(APP_NAME)
    editor = prefs.edit()
    editor.remove_all()
    editor.commit()


def _click_labelled_popup_button(text):
    """Find a popup label and click its clickable parent.

    lv.msgbox footer buttons are clickable obj containers, not lv.button,
    so the regular click_button helper cannot find them.
    """
    label = find_label_on_any_layer(text)
    if label is None:
        return False
    parent = label.get_parent()
    if parent is None:
        return False
    parent.send_event(lv.EVENT.CLICKED, None)
    wait_for_render(10)
    return True


class TestSorterEmojiPersistence(unittest.TestCase):
    """Verify emoji order persistence behavior."""

    def setUp(self):
        """Return to launcher and clear sorter autosave before each test."""
        AppManager.restart_launcher()
        wait_for_render(10)
        _clear_sorter_prefs()

    def tearDown(self):
        """Navigate back to launcher after each test."""
        try:
            from mpos import ui

            ui.back_screen()
            wait_for_render(5)
        except Exception:
            pass

    def _current_activity(self):
        """Return the currently running Sorter activity."""
        return screen_stack[-1][0]

    def test_emoji_order_persists_on_restart_and_changes_on_new_game(self):
        """Emoji order survives a restart and changes on a new game."""
        result = AppManager.start_app(APP_NAME)
        self.assertTrue(result, "Sorter should start")
        wait_for_render(10)

        first_order = list(self._current_activity().emoji_order)
        self.assertEqual(len(first_order), 20)

        click_button(lv.SYMBOL.REFRESH)
        wait_for_render(10)

        restart_order = list(self._current_activity().emoji_order)
        self.assertEqual(first_order, restart_order)

        click_button("New Game")
        wait_for_render(10)

        self.assertTrue(_click_labelled_popup_button("Yes"))
        wait_for_render(10)

        new_order = list(self._current_activity().emoji_order)
        self.assertEqual(len(new_order), 20)
        self.assertNotEqual(first_order, new_order)


if __name__ == "__main__":
    unittest.main()
