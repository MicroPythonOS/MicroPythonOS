"""
Graphical test for screenshot capture.

This test focuses on screenshot capture for visual regression testing.

Usage:
"""

import os
import sys
import unittest
import lvgl as lv
import mpos.ui
from mpos import AppManager, DeviceInfo, DisplayMetrics, capture_screenshot, wait_for_render, wait_for_text


class TestScreenshotCapture(unittest.TestCase):
    """Test suite for screenshot capture."""

    def setUp(self):
        """Set up test fixtures before each test method."""
        if sys.platform == "esp32":
            self.screenshot_dir = "screenshots"
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
        except Exception:
            pass

    def test_capture_about_app_screenshot(self):
        """Capture screenshot of the About app for regression testing."""
        print("\n=== Starting About app screenshot test ===")

        result = AppManager.start_app("com.micropythonos.about")
        self.assertTrue(result, "Failed to start About app")

        self.assertTrue(
            wait_for_text("Hardware ID:", timeout=10),
            "About app did not load within timeout",
        )

        screenshot_path = f"{self.screenshot_dir}/about_app_{self.hardware_id}.raw"
        print(f"\nCapturing screenshot to: {screenshot_path}")

        try:
            width = DisplayMetrics.width()
            height = DisplayMetrics.height()
            buffer = capture_screenshot(screenshot_path, width=width, height=height)
            print(f"Screenshot captured: {len(buffer)} bytes")

            stat = os.stat(screenshot_path)
            self.assertTrue(
                stat[6] > 0,
                "Screenshot file is empty",
            )
            expected_size = width * height * 2
            self.assertEqual(
                stat[6],
                expected_size,
                f"Screenshot file size {stat[6]} does not match expected {expected_size}",
            )
            print(f"Screenshot file size: {stat[6]} bytes")
        except Exception as exc:
            self.fail(f"Failed to capture screenshot: {exc}")
        finally:
            try:
                print(f"Removing screenshot {screenshot_path}")
                os.remove(screenshot_path)
            except OSError:
                pass

        print("\n=== About app screenshot test completed successfully ===")


class TestScreenshotDefaultSize(unittest.TestCase):
    """capture_screenshot() must size its buffer from the screen it captures."""

    def setUp(self):
        self.disp = lv.display_get_default()
        self.orig_size = (self.disp.get_horizontal_resolution(),
                          self.disp.get_vertical_resolution())

    def tearDown(self):
        self.disp.set_resolution(self.orig_size[0], self.orig_size[1])
        wait_for_render(5)

    def test_default_size_follows_active_screen(self):
        """A screen that is not 320x240 still yields a full-size capture."""
        self.disp.set_resolution(400, 300)
        wait_for_render(2)

        buffer = capture_screenshot()

        self.assertEqual(len(buffer), 400 * 300 * 2,
                         "capture_screenshot() did not use the active screen size")
