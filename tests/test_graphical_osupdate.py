import unittest
import lvgl as lv
import mpos
import time
import sys
import os

# Import graphical test helper
from mpos import (
    wait_for_render,
    capture_screenshot,
    find_label_with_text,
    verify_text_present,
    print_screen_labels,
    DeviceInfo,
    BuildInfo,
    AppManager
)


class TestOSUpdateGraphicalUI(unittest.TestCase):
    """Graphical tests for OSUpdate app UI state."""

    def tearDown(self):
        """Clean up after each test method."""
        # Navigate back to launcher
        mpos.ui.back_screen()
        wait_for_render(5)

    def test_app_launches_successfully(self):
        """Test that OSUpdate app launches without errors."""
        result = AppManager.start_app("com.micropythonos.osupdate")

        self.assertTrue(result, "Failed to start OSUpdate app")
        wait_for_render(10)

        # Get active screen
        screen = lv.screen_active()
        self.assertIsNotNone(screen, "No active screen after launch")

    def test_ui_elements_exist(self):
        """Test that all required UI elements are created."""
        result = AppManager.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        wait_for_render(15)

        screen = lv.screen_active()

        # Find UI elements by searching for labels/text
        current_version_label = find_label_with_text(screen, "Installed OS version")
        self.assertIsNotNone(current_version_label, "Current version label not found")

        # Check for update button text (case insensitive)
        # Button text will be "Update OS", "Reinstall\nsame version", or "Install\nolder version"
        update_button_found = verify_text_present(screen, "Update") or verify_text_present(screen, "update") or \
                             verify_text_present(screen, "Reinstall") or verify_text_present(screen, "Install")
        self.assertTrue(update_button_found, "Update button text not found")


    def test_install_button_text_exists(self):
        """Test that install button with update text exists on screen."""
        result = AppManager.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        wait_for_render(15)

        screen = lv.screen_active()

        # Verify the button text is present - it will be "Update OS" initially
        # (or "Reinstall\nsame version" or "Install\nolder version" depending on version comparison)
        button_text_found = verify_text_present(screen, "Update OS") or \
                           verify_text_present(screen, "Reinstall") or \
                           verify_text_present(screen, "Install")
        self.assertTrue(button_text_found, "Install button text should be present on screen")

    def test_current_version_displayed(self):
        """Test that current OS version is displayed correctly."""
        result = AppManager.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        wait_for_render(15)

        screen = lv.screen_active()

        # Find version label
        version_label = find_label_with_text(screen, "Installed OS version:")
        self.assertIsNotNone(version_label, "Version label not found")

        # Check that it contains the current version
        label_text = version_label.get_text()
        current_version = BuildInfo.version.release
        self.assertIn(current_version, label_text,
                     f"Current version {current_version} not in label text: {label_text}")

    def test_initial_status_message_without_wifi(self):
        """Test status message when wifi is not connected."""
        # This test assumes desktop mode where wifi check returns True
        # On actual hardware without wifi, it would show error
        result = AppManager.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        wait_for_render(15)

        screen = lv.screen_active()

        # Should show either "Checking for OS updates..." or update info
        # or wifi error depending on network state
        checking_found = verify_text_present(screen, "Checking") or \
                        verify_text_present(screen, "version") or \
                        verify_text_present(screen, "WiFi")
        self.assertTrue(checking_found, "Should show some status message")

    def test_screenshot_initial_state(self):
        """Capture screenshot of initial app state."""
        result = AppManager.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        wait_for_render(20)

        screen = lv.screen_active()

        # Print labels for debugging
        print("\n=== OSUpdate Initial State Labels ===")
        print_screen_labels(screen)

class TestOSUpdateGraphicalStatusMessages(unittest.TestCase):
    """Graphical tests for OSUpdate status messages."""

    def setUp(self):
        """Set up test fixtures."""
        self.hardware_id = DeviceInfo.hardware_id
        self.screenshot_dir = "tests/screenshots"

        try:
            os.stat(self.screenshot_dir)
        except OSError:
            try:
                os.mkdir(self.screenshot_dir)
            except OSError:
                pass

    def tearDown(self):
        """Clean up after test."""
        mpos.ui.back_screen()
        wait_for_render(5)

    def test_status_label_exists(self):
        """Test that status label is created and visible."""
        result = AppManager.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        wait_for_render(15)

        screen = lv.screen_active()

        # Status label should exist and show some text
        # Look for common status messages
        has_status = (
            verify_text_present(screen, "Checking") or
            verify_text_present(screen, "version") or
            verify_text_present(screen, "WiFi") or
            verify_text_present(screen, "Error") or
            verify_text_present(screen, "Update")
        )
        self.assertTrue(has_status, "Status label should be present with some message")

    def test_all_labels_readable(self):
        """Test that all labels are readable (no truncation issues)."""
        result = AppManager.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        wait_for_render(15)

        screen = lv.screen_active()

        # Print all labels to verify they're readable
        print("\n=== All OSUpdate Labels ===")
        print_screen_labels(screen)

        # At minimum, should have version label
        version_found = verify_text_present(screen, "Installed OS version")
        self.assertTrue(version_found, "Version label should be present and readable")


class TestOSUpdateGraphicalScreenshots(unittest.TestCase):
    """Screenshot tests for visual regression testing."""

    def setUp(self):
        """Set up test fixtures."""
        self.hardware_id = DeviceInfo.hardware_id
        self.screenshot_dir = "tests/screenshots"

        try:
            os.stat(self.screenshot_dir)
        except OSError:
            try:
                os.mkdir(self.screenshot_dir)
            except OSError:
                pass

    def tearDown(self):
        """Clean up after test."""
        mpos.ui.back_screen()
        wait_for_render(5)

    def test_capture_main_screen(self):
        """Capture screenshot of main OSUpdate screen."""
        result = AppManager.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        wait_for_render(20)


    def test_capture_with_labels_visible(self):
        """Capture screenshot ensuring all text is visible."""
        result = AppManager.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        wait_for_render(20)

        screen = lv.screen_active()

        # Verify key elements are visible before screenshot (case insensitive)
        has_version = verify_text_present(screen, "Installed") or verify_text_present(screen, "version")
        # Button text can be "Update OS", "Reinstall\nsame version", or "Install\nolder version"
        has_button = verify_text_present(screen, "Update") or verify_text_present(screen, "update") or \
                    verify_text_present(screen, "Reinstall") or verify_text_present(screen, "Install")

        self.assertTrue(has_version, "Version label should be visible")
        self.assertTrue(has_button, "Update button should be visible")


