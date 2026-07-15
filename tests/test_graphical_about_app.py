"""
Graphical test for the About app.

This test verifies that the About app displays correct information,
specifically that the Hardware ID shown matches the actual hardware ID.

This is a proof of concept for graphical testing that:
1. Starts an app programmatically
2. Verifies UI content via direct widget inspection
3. Works on both desktop and device

Usage:
"""

import unittest
import lvgl as lv
import mpos.ui
from mpos import (
    wait_for_text,
    find_label_with_text,
    verify_text_present,
    print_screen_labels,
    DeviceInfo,
    BuildInfo,
    AppManager,
)


class TestGraphicalAboutApp(unittest.TestCase):
    """Test suite for About app graphical verification."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.hardware_id = DeviceInfo.hardware_id
        print(f"Testing with hardware ID: {self.hardware_id}")

    def tearDown(self):
        """Clean up after each test method."""
        try:
            mpos.ui.back_screen()
        except:
            pass

    def test_about_app_shows_correct_hardware_id(self):
        """
        Test that About app displays the correct Hardware ID.
        """
        print("\n=== Starting About app test ===")

        result = AppManager.start_app("com.micropythonos.about")
        self.assertTrue(result, "Failed to start About app")

        self.assertTrue(
            wait_for_text("Hardware ID:", timeout=10),
            "About app did not load within timeout",
        )

        screen = lv.screen_active()
        print("\nLabels found on screen:")
        print_screen_labels(screen)

        hardware_id_label = find_label_with_text(screen, "Hardware ID:")
        self.assertIsNotNone(
            hardware_id_label,
            "Could not find 'Hardware ID:' label on screen"
        )

        hardware_id_text = hardware_id_label.get_text()
        print(f"\nHardware ID label text: {hardware_id_text}")

        expected_text = f"Hardware ID: {self.hardware_id}"
        self.assertEqual(
            hardware_id_text,
            expected_text,
            f"Hardware ID mismatch. Expected '{expected_text}', got '{hardware_id_text}'"
        )

        self.assertTrue(
            wait_for_text(self.hardware_id, timeout=5),
            f"Hardware ID '{self.hardware_id}' not found on screen"
        )

        print("\n=== About app test completed successfully ===")

    def test_about_app_shows_os_version(self):
        """
        Test that About app displays the OS version.
        """
        print("\n=== Starting About app OS version test ===")

        result = AppManager.start_app("com.micropythonos.about")
        self.assertTrue(result, "Failed to start About app")

        self.assertTrue(
            wait_for_text("Release version:", timeout=10),
            "About app did not load within timeout",
        )

        os_version = BuildInfo.version.release
        self.assertTrue(
            wait_for_text(os_version, timeout=5),
            f"OS version '{os_version}' not found on screen"
        )

        print(f"Found OS version: {os_version}")
        print("=== OS version test completed successfully ===")
