"""
Test that Memory uses lv.msgbox() for its confirmation popup.

This test verifies that pressing the "New Game" button opens a
confirmation popup with the message "New game?" and Yes/No buttons,
implemented as an lv.msgbox() on the top layer.

Usage:
"""

import unittest

import lvgl as lv

from mpos import AppManager, wait_for_render
from mpos.ui.testing import click_button, find_label_with_text, wait_for_widget


class TestMemoryConfirmPopup(unittest.TestCase):
    """Verify the Memory confirmation popup uses lv.msgbox()."""

    def setUp(self):
        """Return to launcher before each test."""
        AppManager.restart_launcher()
        wait_for_render(10)

    def tearDown(self):
        """Navigate back to launcher after each test."""
        try:
            from mpos import ui

            ui.back_screen()
            wait_for_render(5)
        except Exception:
            pass

    def test_new_game_opens_msgbox(self):
        """Clicking New Game opens a confirmation msgbox."""
        result = AppManager.start_app("com.micropythonos.memory")
        self.assertTrue(result, "Memory should start")
        wait_for_render(10)

        click_button("New Game")
        wait_for_render(10)

        label = wait_for_widget(lambda: find_label_with_text(lv.layer_top(), "New game?"), timeout=5)
        self.assertIsNotNone(label)

        self.assertIsNotNone(wait_for_widget(lambda: find_label_with_text(lv.layer_top(), "Yes"), timeout=5))
        self.assertIsNotNone(wait_for_widget(lambda: find_label_with_text(lv.layer_top(), "No"), timeout=5))


if __name__ == "__main__":
    unittest.main()
