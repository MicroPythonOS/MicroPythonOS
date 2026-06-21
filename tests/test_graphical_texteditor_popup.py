"""
Test that the TextEditor Save As flow launches InputActivity.

This test verifies that pressing Save on an untitled file opens the
InputActivity save-as screen with a "Save As" title and Save/Cancel
buttons.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_texteditor_popup.py
    Device:  ./tests/unittest.sh tests/test_graphical_texteditor_popup.py --ondevice
"""

import unittest

import lvgl as lv

from mpos import AppManager, InputActivity, wait_for_render
from mpos.ui.testing import click_button, find_label_with_text
from mpos.ui.view import screen_stack


class TestTextEditorSaveAsInput(unittest.TestCase):
    """Verify the TextEditor save-as flow uses InputActivity."""

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

    def test_save_as_opens_input_activity(self):
        """Clicking Save on an untitled file opens InputActivity."""
        result = AppManager.start_app("com.micropythonos.texteditor")
        self.assertTrue(result, "TextEditor should start")
        wait_for_render(10)

        click_button("Save")
        wait_for_render(10)

        self.assertIsInstance(screen_stack[-1][0], InputActivity)

        label = find_label_with_text(lv.screen_active(), "Save As")
        self.assertIsNotNone(label)

        self.assertIsNotNone(find_label_with_text(lv.screen_active(), "Save"))
        self.assertIsNotNone(find_label_with_text(lv.screen_active(), "Cancel"))


if __name__ == "__main__":
    unittest.main()
