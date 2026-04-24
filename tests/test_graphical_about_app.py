"""
Graphical test for the About app.

This test verifies that the About app displays correct information,
specifically that the Hardware ID shown matches the actual hardware ID.

This is a proof of concept for graphical testing that:
1. Starts an app programmatically
2. Verifies UI content via direct widget inspection
3. Works on both desktop and device

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_about_app.py
    Device:  ./tests/unittest.sh tests/test_graphical_about_app.py --ondevice
"""

import unittest
import time
import lvgl as lv
import mpos.ui
from mpos import (
    wait_for_render,
    find_label_with_text,
    verify_text_present,
    print_screen_labels,
    DeviceInfo,
    BuildInfo,
    AppManager,
)


class TestGraphicalAboutApp(unittest.TestCase):
    """Test suite for About app graphical verification."""

    def _wait_for_text(self, text, attempts=6, render_iterations=30):
        for attempt in range(1, attempts + 1):
            screen = lv.screen_active()
            print(f"\nText check attempt {attempt}/{attempts}:")
            print_screen_labels(screen)
            if verify_text_present(screen, text):
                return True
            wait_for_render(iterations=render_iterations)
            time.sleep(0.2)
        return False

    def _wait_for_label_with_text(self, text, attempts=6, render_iterations=30):
        for attempt in range(1, attempts + 1):
            screen = lv.screen_active()
            label = find_label_with_text(screen, text)
            if label is not None:
                return label
            print(f"\nLabel '{text}' not found (attempt {attempt}/{attempts}).")
            print_screen_labels(screen)
            wait_for_render(iterations=render_iterations)
            time.sleep(0.2)
        return None

    def setUp(self):
        """Set up test fixtures before each test method."""
        # Store hardware ID for verification
        self.hardware_id = DeviceInfo.hardware_id
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
        """
        print("\n=== Starting About app test ===")

        # Start the About app
        result = AppManager.start_app("com.micropythonos.about")
        self.assertTrue(result, "Failed to start About app")

        # Wait for UI to fully render
        wait_for_render(iterations=30)

        # Get current screen
        screen = lv.screen_active()

        # Debug: Print all labels found (helpful for development)
        print("\nLabels found on screen:")
        print_screen_labels(screen)

        # Verify that Hardware ID text is present
        hardware_id_label = self._wait_for_label_with_text("Hardware ID:")
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
            self._wait_for_text(self.hardware_id),
            f"Hardware ID '{self.hardware_id}' not found on screen"
        )

        print("\n=== About app test completed successfully ===")

    def test_about_app_shows_os_version(self):
        """
        Test that About app displays the OS version.

        This is a simpler test that just verifies version info is present.
        """
        print("\n=== Starting About app OS version test ===")

        # Start the About app
        result = AppManager.start_app("com.micropythonos.about")
        self.assertTrue(result, "Failed to start About app")

        # Wait for UI to render
        wait_for_render(iterations=150)

        # Get current screen
        screen = lv.screen_active()

        # Verify that MicroPythonOS version text is present
        self.assertTrue(
            self._wait_for_text("Release version:"),
            "Could not find 'Release version:' on screen"
        )

        # Verify the actual version string is present
        os_version = BuildInfo.version.release
        self.assertTrue(
            self._wait_for_text(os_version),
            f"OS version '{os_version}' not found on screen"
        )

        print(f"Found OS version: {os_version}")
        print("=== OS version test completed successfully ===")


