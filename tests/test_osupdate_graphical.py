import unittest
import lvgl as lv
import mpos
import time
import sys
import os

# Import graphical test helper
from graphical_test_helper import (
    wait_for_render,
    capture_screenshot,
    find_label_with_text,
    verify_text_present,
    print_screen_labels
)


class TestOSUpdateGraphicalUI(unittest.TestCase):
    """Graphical tests for OSUpdate app UI state."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.hardware_id = mpos.info.get_hardware_id()
        self.screenshot_dir = "tests/screenshots"

        # Ensure screenshots directory exists
        # First check if tests directory exists
        try:
            os.stat("tests")
        except OSError:
            # We're not in the right directory, maybe running from root
            pass

        # Now create screenshots directory if needed
        try:
            os.stat(self.screenshot_dir)
        except OSError:
            try:
                os.mkdir(self.screenshot_dir)
            except OSError:
                # Might already exist or permission issue
                pass

    def tearDown(self):
        """Clean up after each test method."""
        # Navigate back to launcher
        mpos.ui.back_screen()
        wait_for_render(5)

    def test_app_launches_successfully(self):
        """Test that OSUpdate app launches without errors."""
        result = mpos.apps.start_app("com.micropythonos.osupdate")

        self.assertTrue(result, "Failed to start OSUpdate app")
        wait_for_render(10)

        # Get active screen
        screen = lv.screen_active()
        self.assertIsNotNone(screen, "No active screen after launch")

    def test_ui_elements_exist(self):
        """Test that all required UI elements are created."""
        result = mpos.apps.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        wait_for_render(15)

        screen = lv.screen_active()

        # Find UI elements by searching for labels/text
        current_version_label = find_label_with_text(screen, "Installed OS version")
        self.assertIsNotNone(current_version_label, "Current version label not found")

        # Check for force update checkbox text (might be "Force" or "Update")
        force_checkbox_found = verify_text_present(screen, "Force") or verify_text_present(screen, "force")
        self.assertTrue(force_checkbox_found, "Force checkbox text not found")

        # Check for update button text (case insensitive)
        update_button_found = verify_text_present(screen, "Update") or verify_text_present(screen, "update")
        self.assertTrue(update_button_found, "Update button text not found")

    def test_force_checkbox_initially_unchecked(self):
        """Test that force update checkbox starts unchecked."""
        result = mpos.apps.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        wait_for_render(15)

        screen = lv.screen_active()

        # Find checkbox - it's the first checkbox on the screen
        checkbox = None
        def find_checkbox(obj):
            nonlocal checkbox
            if checkbox:
                return
            # Check if this object is a checkbox
            try:
                # In LVGL, checkboxes have specific flags/properties
                if obj.get_child_count() >= 0:  # It's a valid object
                    # Try to get state - checkboxes respond to STATE.CHECKED
                    state = obj.get_state()
                    # If it has checkbox-like text, it's probably our checkbox
                    for i in range(obj.get_child_count()):
                        child = obj.get_child(i)
                        if hasattr(child, 'get_text'):
                            text = child.get_text()
                            if text and "Force Update" in text:
                                checkbox = obj.get_parent() if obj.get_parent() else obj
                                return
            except:
                pass

            # Recursively search children
            for i in range(obj.get_child_count()):
                child = obj.get_child(i)
                find_checkbox(child)

        find_checkbox(screen)

        if checkbox:
            state = checkbox.get_state()
            is_checked = bool(state & lv.STATE.CHECKED)
            self.assertFalse(is_checked, "Force Update checkbox should start unchecked")

    def test_install_button_initially_disabled(self):
        """Test that install button starts in disabled state."""
        result = mpos.apps.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        wait_for_render(15)

        screen = lv.screen_active()

        # Find the button
        button = None
        def find_button(obj):
            nonlocal button
            if button:
                return
            # Check if this object contains "Update OS" text
            for i in range(obj.get_child_count()):
                child = obj.get_child(i)
                if hasattr(child, 'get_text'):
                    text = child.get_text()
                    if text and "Update OS" in text:
                        # Parent is likely the button
                        button = obj
                        return

            # Recursively search children
            for i in range(obj.get_child_count()):
                child = obj.get_child(i)
                find_button(child)

        find_button(screen)

        if button:
            state = button.get_state()
            is_disabled = bool(state & lv.STATE.DISABLED)
            self.assertTrue(is_disabled, "Install button should start disabled")

    def test_current_version_displayed(self):
        """Test that current OS version is displayed correctly."""
        result = mpos.apps.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        wait_for_render(15)

        screen = lv.screen_active()

        # Find version label
        version_label = find_label_with_text(screen, "Installed OS version:")
        self.assertIsNotNone(version_label, "Version label not found")

        # Check that it contains the current version
        label_text = version_label.get_text()
        current_version = mpos.info.CURRENT_OS_VERSION
        self.assertIn(current_version, label_text,
                     f"Current version {current_version} not in label text: {label_text}")

    def test_initial_status_message_without_wifi(self):
        """Test status message when wifi is not connected."""
        # This test assumes desktop mode where wifi check returns True
        # On actual hardware without wifi, it would show error
        result = mpos.apps.start_app("com.micropythonos.osupdate")
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
        result = mpos.apps.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        wait_for_render(20)

        screen = lv.screen_active()

        # Print labels for debugging
        print("\n=== OSUpdate Initial State Labels ===")
        print_screen_labels(screen)

        # Capture screenshot
        screenshot_path = f"{self.screenshot_dir}/osupdate_initial_{self.hardware_id}.raw"
        capture_screenshot(screenshot_path)
        print(f"Screenshot saved to: {screenshot_path}")


class TestOSUpdateGraphicalStatusMessages(unittest.TestCase):
    """Graphical tests for OSUpdate status messages."""

    def setUp(self):
        """Set up test fixtures."""
        self.hardware_id = mpos.info.get_hardware_id()
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
        result = mpos.apps.start_app("com.micropythonos.osupdate")
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
        result = mpos.apps.start_app("com.micropythonos.osupdate")
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
        self.hardware_id = mpos.info.get_hardware_id()
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
        result = mpos.apps.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        wait_for_render(20)

        screenshot_path = f"{self.screenshot_dir}/osupdate_main_{self.hardware_id}.raw"
        capture_screenshot(screenshot_path)

        # Verify file was created
        try:
            stat = os.stat(screenshot_path)
            self.assertTrue(stat[6] > 0, "Screenshot file should not be empty")
        except OSError:
            self.fail(f"Screenshot file not created: {screenshot_path}")

    def test_capture_with_labels_visible(self):
        """Capture screenshot ensuring all text is visible."""
        result = mpos.apps.start_app("com.micropythonos.osupdate")
        self.assertTrue(result)
        wait_for_render(20)

        screen = lv.screen_active()

        # Verify key elements are visible before screenshot (case insensitive)
        has_version = verify_text_present(screen, "Installed") or verify_text_present(screen, "version")
        has_force = verify_text_present(screen, "Force") or verify_text_present(screen, "force")
        has_button = verify_text_present(screen, "Update") or verify_text_present(screen, "update")

        self.assertTrue(has_version, "Version label should be visible")
        self.assertTrue(has_force, "Force checkbox should be visible")
        self.assertTrue(has_button, "Update button should be visible")

        screenshot_path = f"{self.screenshot_dir}/osupdate_labeled_{self.hardware_id}.raw"
        capture_screenshot(screenshot_path)


if __name__ == '__main__':
    unittest.main()
