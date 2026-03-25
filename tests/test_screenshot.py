"""
Graphical test for screenshot capture.

This test focuses on screenshot capture for visual regression testing.

Usage:
    Desktop: ./tests/unittest.sh tests/test_screenshot.py
    Device:  ./tests/unittest.sh tests/test_screenshot.py --ondevice
"""

import os
import sys
import unittest
import mpos.ui
from mpos import AppManager, DeviceInfo, capture_screenshot, wait_for_render


class TestScreenshotCapture(unittest.TestCase):
    """Test suite for screenshot capture."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        if sys.platform == "esp32":
            self.screenshot_dir = "tests/screenshots"
        else:
            self.screenshot_dir = "../tests/screenshots"

        try:
            os.mkdir(self.screenshot_dir)
        except OSError:
            pass

        self.hardware_id = DeviceInfo.hardware_id
        print(f"Testing with hardware ID: {self.hardware_id}")

    def tearDown(self):
        """Clean up after each test method."""
        try:
            mpos.ui.back_screen()
            wait_for_render(5)
        except Exception:
            pass

    def test_capture_about_app_screenshot(self):
        """Capture screenshot of the About app for regression testing."""
        print("\n=== Starting About app screenshot test ===")

        result = AppManager.start_app("com.micropythonos.about")
        self.assertTrue(result, "Failed to start About app")

        wait_for_render(iterations=15)

        screenshot_path = f"{self.screenshot_dir}/about_app_{self.hardware_id}.raw"
        print(f"\nCapturing screenshot to: {screenshot_path}")

        try:
            buffer = capture_screenshot(screenshot_path, width=320, height=240)
            print(f"Screenshot captured: {len(buffer)} bytes")

            stat = os.stat(screenshot_path)
            self.assertTrue(
                stat[6] > 0,
                "Screenshot file is empty",
            )
            print(f"Screenshot file size: {stat[6]} bytes")
        except Exception as exc:
            self.fail(f"Failed to capture screenshot: {exc}")

        print("\n=== About app screenshot test completed successfully ===")
