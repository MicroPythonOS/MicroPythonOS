"""
Test for app launching functionality.

This test verifies that the app starting system works correctly,
including launching existing apps and handling non-existent apps.

Works on both desktop and ESP32 by using the standard boot/main
initialization pattern.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_start_app.py
    Device:  ./tests/unittest.sh tests/test_graphical_start_app.py --ondevice
"""

import unittest
from mpos import ui, wait_for_render, PackageManager


class TestStartApp(unittest.TestCase):
    """Test suite for app launching functionality."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        print("\n=== Test Setup ===")
        # No custom initialization needed - boot.py/main.py already ran

    def tearDown(self):
        """Clean up after each test method."""
        # Navigate back to launcher to close any opened apps
        try:
            mpos.ui.back_screen()
            wait_for_render(5)  # Allow navigation to complete
        except:
            pass  # Already on launcher or error

        print("=== Test Cleanup Complete ===\n")

    def test_normal(self):
        """Test that launching an existing app succeeds."""
        print("Testing normal app launch...")

        result = PackageManager.start_app("com.micropythonos.launcher")
        wait_for_render(10)  # Wait for app to load

        self.assertTrue(result, "com.micropythonos.launcher should start")
        print("Normal app launch successful")

    def test_nonexistent(self):
        """Test that launching a non-existent app fails gracefully."""
        print("Testing non-existent app launch...")

        result = PackageManager.start_app("com.micropythonos.nonexistent")

        self.assertFalse(result, "com.micropythonos.nonexistent should not start")
        print("Non-existent app handled correctly")

    def test_restart_launcher(self):
        """Test that restarting the launcher succeeds."""
        print("Testing launcher restart...")

        result = PackageManager.restart_launcher()
        wait_for_render(10)  # Wait for launcher to load

        self.assertTrue(result, "restart_launcher() should succeed")
        print("Launcher restart successful")


