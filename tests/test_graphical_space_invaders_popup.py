"""
Test that SpaceInvaders uses lv.msgbox() for its high score reset popup.

This test verifies that the high-score reset callback opens a confirmation
popup with the message "Reset high score?" and Yes/No buttons, implemented
as an lv.msgbox() on the top layer.

Usage:
"""

import unittest

import lvgl as lv

from mpos import AppManager, wait_for_render
from mpos.ui.testing import find_label_with_text, wait_for_widget


class TestSpaceInvadersResetPopup(unittest.TestCase):
    """Verify the SpaceInvaders reset popup uses lv.msgbox()."""

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

    def test_reset_highscore_opens_msgbox(self):
        """The high-score reset callback opens a confirmation msgbox."""
        import mpos.ui.view as view

        result = AppManager.start_app("com.micropythonos.space_invaders")
        self.assertTrue(result, "SpaceInvaders should start")
        wait_for_render(10)

        activity = view.screen_stack[-1][0]
        activity._on_highscore_tap(None)
        wait_for_render(10)

        label = wait_for_widget(lambda: find_label_with_text(lv.layer_top(), "Reset high score?"), timeout=5)
        self.assertIsNotNone(label)

        self.assertIsNotNone(wait_for_widget(lambda: find_label_with_text(lv.layer_top(), "Yes"), timeout=5))
        self.assertIsNotNone(wait_for_widget(lambda: find_label_with_text(lv.layer_top(), "No"), timeout=5))


if __name__ == "__main__":
    unittest.main()
