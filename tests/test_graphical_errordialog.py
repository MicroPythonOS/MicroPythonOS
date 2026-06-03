"""
Test that error dialogs are shown properly when apps fail to load or crash.

Tests both import-time failures (com.micropythonos.errortest) and
lifecycle failures (com.micropythonos.errortest_resume).
"""

import unittest
import lvgl as lv

from mpos.ui.testing import (
    GraphicalTestCase,
    wait_for_render,
    find_label_on_any_layer,
    verify_text_on_any_layer,
    find_button_with_text,
)
from mpos import AppManager


class TestErrorDialog(GraphicalTestCase):
    """Test that error/warning dialogs appear when apps fail."""

    def test_import_error_shows_error_dialog(self):
        """Import-time failure should show 'could not load app' dialog."""
        AppManager.start_app("com.micropythonos.errortest")
        wait_for_render(iterations=15)

        self.assertTrue(
            verify_text_on_any_layer("Could not load app"),
            "Expected 'Could not load app' text in error dialog",
        )
        self.assertTrue(
            verify_text_on_any_layer("com.micropythonos.errortest"),
            "Expected app name in error dialog",
        )

        show_details = find_label_on_any_layer("Show Details")
        self.assertIsNotNone(
            show_details, "Expected 'Show Details' button in error dialog"
        )

        self.assertTrue(
            verify_text_on_any_layer("Close"),
            "Expected Close button in error dialog",
        )

    def test_lifecycle_error_shows_warning_dialog(self):
        """onResume failure should show 'threw exception' warning dialog."""
        AppManager.start_app("com.micropythonos.errortest_resume")
        wait_for_render(iterations=15)

        self.assertTrue(
            verify_text_on_any_layer("threw an exception"),
            "Expected 'threw an exception' text in warning dialog",
        )
        self.assertTrue(
            verify_text_on_any_layer("com.micropythonos.errortest_resume"),
            "Expected app name in warning dialog",
        )

        show_details = find_label_on_any_layer("Show Details")
        self.assertIsNotNone(
            show_details, "Expected 'Show Details' button in warning dialog"
        )

    def _click_top_layer_button(self, button_text):
        """Click a button on lv.layer_top() by text."""
        label = find_label_on_any_layer(button_text)
        if label:
            parent = label.get_parent()
            parent.send_event(lv.EVENT.CLICKED, None)
            wait_for_render(iterations=15)
            return True
        return False

    def test_show_details_reveals_exception(self):
        """Clicking 'Show Details' should reveal the exception traceback."""
        AppManager.start_app("com.micropythonos.errortest_resume")
        wait_for_render(iterations=15)

        self.assertTrue(
            verify_text_on_any_layer("threw an exception"),
            "Warning dialog should be visible",
        )

        clicked = self._click_top_layer_button("Show Details")
        self.assertTrue(clicked, "Show Details button should be clickable")
        wait_for_render(iterations=15)

        self.assertTrue(
            verify_text_on_any_layer("this_should_fail"),
            "Exception details should be visible after clicking Show Details",
        )

    def test_import_error_details_reveals_error(self):
        """Clicking 'Show Details' on import error shows the import exception."""
        AppManager.start_app("com.micropythonos.errortest")
        wait_for_render(iterations=15)

        self.assertTrue(
            verify_text_on_any_layer("Could not load app"),
            "Error dialog should be visible",
        )

        clicked = self._click_top_layer_button("Show Details")
        self.assertTrue(clicked, "Show Details button should be clickable")
        wait_for_render(iterations=15)

        self.assertTrue(
            verify_text_on_any_layer("ActivityDoesntExist"),
            "Exception details should mention the missing import",
        )
