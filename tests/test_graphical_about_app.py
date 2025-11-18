"""
Graphical test for the About app.

This test verifies that the About app displays correct information,
specifically that the Hardware ID shown matches the actual hardware ID.

This is a proof of concept for graphical testing that:
1. Starts an app programmatically
2. Verifies UI content via direct widget inspection
3. Captures screenshots for visual regression testing
4. Works on both desktop and device

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_about_app.py
    Device:  ./tests/unittest.sh tests/test_graphical_about_app.py --ondevice
"""

import unittest
import lvgl as lv
import mpos.apps
import mpos.info
import mpos.ui
import os
from mpos.ui.testing import (
    wait_for_render,
    capture_screenshot,
    find_label_with_text,
    verify_text_present,
    print_screen_labels
)


class TestGraphicalAboutApp(unittest.TestCase):
    """Test suite for About app graphical verification."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Get absolute path to screenshots directory
        # When running tests, we're in internal_filesystem/, so go up one level
        import sys
        if sys.platform == "esp32":
            self.screenshot_dir = "tests/screenshots"
        else:
            # On desktop, tests directory is in parent
            self.screenshot_dir = "../tests/screenshots"

        # Ensure screenshots directory exists
        try:
            os.mkdir(self.screenshot_dir)
        except OSError:
            pass  # Directory already exists

        # Store hardware ID for verification
        self.hardware_id = mpos.info.get_hardware_id()
        print(f"Testing with hardware ID: {self.hardware_id}")

    def tearDown(self):
        """Clean up after each test method."""
        # Navigate back to launcher (closes the About app)
        try:
            mpos.ui.back_screen()
            wait_for_render(5)  # Allow navigation to complete
        except:
            pass  # Already on launcher or error

    def test_about_app_shows_correct_hardware_id(self):
        """
        Test that About app displays the correct Hardware ID.

        Verification approach:
        1. Start the About app
        2. Wait for UI to render
        3. Find the "Hardware ID:" label
        4. Verify it contains the actual hardware ID
        5. Capture screenshot for visual verification
        """
        print("\n=== Starting About app test ===")

        # Start the About app
        result = mpos.apps.start_app("com.micropythonos.about")
        self.assertTrue(result, "Failed to start About app")

        # Wait for UI to fully render
        wait_for_render(iterations=15)

        # Get current screen
        screen = lv.screen_active()

        # Debug: Print all labels found (helpful for development)
        print("\nLabels found on screen:")
        print_screen_labels(screen)

        # Verify that Hardware ID text is present
        hardware_id_label = find_label_with_text(screen, "Hardware ID:")
        self.assertIsNotNone(
            hardware_id_label,
            "Could not find 'Hardware ID:' label on screen"
        )

        # Get the full text from the Hardware ID label
        hardware_id_text = hardware_id_label.get_text()
        print(f"\nHardware ID label text: {hardware_id_text}")

        # Verify the hardware ID matches
        expected_text = f"Hardware ID: {self.hardware_id}"
        self.assertEqual(
            hardware_id_text,
            expected_text,
            f"Hardware ID mismatch. Expected '{expected_text}', got '{hardware_id_text}'"
        )

        # Also verify using the helper function
        self.assertTrue(
            verify_text_present(screen, self.hardware_id),
            f"Hardware ID '{self.hardware_id}' not found on screen"
        )

        # Capture screenshot for visual regression testing
        screenshot_path = f"{self.screenshot_dir}/about_app_{self.hardware_id}.raw"
        print(f"\nCapturing screenshot to: {screenshot_path}")

        try:
            buffer = capture_screenshot(screenshot_path, width=320, height=240)
            print(f"Screenshot captured: {len(buffer)} bytes")

            # Verify screenshot file was created
            stat = os.stat(screenshot_path)
            self.assertTrue(
                stat[6] > 0,  # stat[6] is file size
                "Screenshot file is empty"
            )
            print(f"Screenshot file size: {stat[6]} bytes")

        except Exception as e:
            self.fail(f"Failed to capture screenshot: {e}")

        print("\n=== About app test completed successfully ===")

    def test_about_app_shows_os_version(self):
        """
        Test that About app displays the OS version.

        This is a simpler test that just verifies version info is present.
        """
        print("\n=== Starting About app OS version test ===")

        # Start the About app
        result = mpos.apps.start_app("com.micropythonos.about")
        self.assertTrue(result, "Failed to start About app")

        # Wait for UI to render
        wait_for_render(iterations=15)

        # Get current screen
        screen = lv.screen_active()

        # Verify that MicroPythonOS version text is present
        self.assertTrue(
            verify_text_present(screen, "MicroPythonOS version:"),
            "Could not find 'MicroPythonOS version:' on screen"
        )

        # Verify the actual version string is present
        os_version = mpos.info.CURRENT_OS_VERSION
        self.assertTrue(
            verify_text_present(screen, os_version),
            f"OS version '{os_version}' not found on screen"
        )

        print(f"Found OS version: {os_version}")
        print("=== OS version test completed successfully ===")


