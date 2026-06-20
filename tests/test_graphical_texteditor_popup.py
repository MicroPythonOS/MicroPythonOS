"""
Test that the TextEditor uses lv.msgbox() for its save-as popup.

This test verifies that pressing Save on an untitled file opens a popup
with the prompt "Enter filename:" and OK/Cancel buttons, implemented as
an lv.msgbox() on the top layer.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_texteditor_popup.py
    Device:  ./tests/unittest.sh tests/test_graphical_texteditor_popup.py --ondevice
"""

import unittest

import lvgl as lv

from mpos import AppManager, wait_for_render
from mpos.ui.testing import click_button, find_label_with_text


class TestTextEditorSaveAsPopup(unittest.TestCase):
    """Verify the TextEditor save-as popup uses lv.msgbox()."""

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

    def test_save_as_opens_msgbox(self):
        """Clicking Save on an untitled file opens a save-as msgbox."""
        result = AppManager.start_app("com.micropythonos.texteditor")
        self.assertTrue(result, "TextEditor should start")
        wait_for_render(10)

        click_button("Save")
        wait_for_render(10)

        label = find_label_with_text(lv.layer_top(), "Enter filename:")
        self.assertIsNotNone(label)

        self.assertIsNotNone(find_label_with_text(lv.layer_top(), "OK"))
        self.assertIsNotNone(find_label_with_text(lv.layer_top(), "Cancel"))


if __name__ == "__main__":
    unittest.main()
