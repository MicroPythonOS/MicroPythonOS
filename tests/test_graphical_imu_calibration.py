"""
Graphical test for IMU calibration activities.

Tests both CheckIMUCalibrationActivity and CalibrateIMUActivity
with mock data on desktop.

Usage:
    Desktop: ./tests/unittest.sh tests/test_graphical_imu_calibration.py
    Device:  ./tests/unittest.sh tests/test_graphical_imu_calibration.py --ondevice
"""

import unittest
import lvgl as lv
import mpos.apps
import mpos.ui
import os
import sys
import time
from mpos.ui.testing import (
    wait_for_render,
    capture_screenshot,
    find_label_with_text,
    verify_text_present,
    print_screen_labels,
    simulate_click,
    get_widget_coords,
    find_button_with_text
)


class TestIMUCalibration(unittest.TestCase):
    """Test suite for IMU calibration activities."""

    def setUp(self):
        """Set up test fixtures."""
        # Get screenshot directory
        if sys.platform == "esp32":
            self.screenshot_dir = "tests/screenshots"
        else:
            self.screenshot_dir = "/home/user/MicroPythonOS/tests/screenshots"

        # Ensure directory exists
        try:
            os.mkdir(self.screenshot_dir)
        except OSError:
            pass

    def tearDown(self):
        """Clean up after test."""
        # Navigate back to launcher
        try:
            for _ in range(3):  # May need multiple backs
                mpos.ui.back_screen()
                wait_for_render(5)
        except:
            pass

    def test_check_calibration_activity_loads(self):
        """Test that CheckIMUCalibrationActivity loads and displays."""
        print("\n=== Testing CheckIMUCalibrationActivity ===")

        # Navigate: Launcher -> Settings -> Check IMU Calibration
        result = mpos.apps.start_app("com.micropythonos.settings")
        self.assertTrue(result, "Failed to start Settings app")
        wait_for_render(15)

        # Initialize touch device with dummy click
        simulate_click(10, 10)
        wait_for_render(10)

        # Find and click "Check IMU Calibration" setting
        screen = lv.screen_active()
        check_cal_label = find_label_with_text(screen, "Check IMU Calibration")
        self.assertIsNotNone(check_cal_label, "Could not find 'Check IMU Calibration' setting")

        # Click on the setting container
        coords = get_widget_coords(check_cal_label.get_parent())
        self.assertIsNotNone(coords, "Could not get coordinates of setting")
        simulate_click(coords['center_x'], coords['center_y'])
        wait_for_render(30)

        # Verify CheckIMUCalibrationActivity loaded
        screen = lv.screen_active()
        self.assertTrue(verify_text_present(screen, "IMU Calibration Check"),
                       "CheckIMUCalibrationActivity title not found")

        # Wait for real-time updates to populate
        wait_for_render(20)

        # Verify key elements are present
        print_screen_labels(screen)
        self.assertTrue(verify_text_present(screen, "Quality:"),
                       "Quality label not found")
        self.assertTrue(verify_text_present(screen, "Accelerometer"),
                       "Accelerometer label not found")
        self.assertTrue(verify_text_present(screen, "Gyroscope"),
                       "Gyroscope label not found")

        # Capture screenshot
        screenshot_path = f"{self.screenshot_dir}/check_imu_calibration.raw"
        print(f"Capturing screenshot: {screenshot_path}")
        capture_screenshot(screenshot_path)

        # Verify screenshot saved
        stat = os.stat(screenshot_path)
        self.assertTrue(stat[6] > 0, "Screenshot file is empty")

        print("=== CheckIMUCalibrationActivity test complete ===")

    def test_calibrate_activity_flow(self):
        """Test CalibrateIMUActivity full calibration flow."""
        print("\n=== Testing CalibrateIMUActivity Flow ===")

        # Navigate: Launcher -> Settings -> Calibrate IMU
        result = mpos.apps.start_app("com.micropythonos.settings")
        self.assertTrue(result, "Failed to start Settings app")
        wait_for_render(15)

        # Initialize touch device with dummy click
        simulate_click(10, 10)
        wait_for_render(10)

        # Find and click "Calibrate IMU" setting
        screen = lv.screen_active()
        calibrate_label = find_label_with_text(screen, "Calibrate IMU")
        self.assertIsNotNone(calibrate_label, "Could not find 'Calibrate IMU' setting")

        coords = get_widget_coords(calibrate_label.get_parent())
        self.assertIsNotNone(coords)
        simulate_click(coords['center_x'], coords['center_y'])
        wait_for_render(30)

        # Verify activity loaded
        screen = lv.screen_active()
        self.assertTrue(verify_text_present(screen, "IMU Calibration"),
                       "CalibrateIMUActivity title not found")

        # Capture initial state
        screenshot_path = f"{self.screenshot_dir}/calibrate_imu_01_initial.raw"
        capture_screenshot(screenshot_path)

        # Step 1: Click "Check Quality" button
        check_btn = find_button_with_text(screen, "Check Quality")
        self.assertIsNotNone(check_btn, "Could not find 'Check Quality' button")
        coords = get_widget_coords(check_btn)
        simulate_click(coords['center_x'], coords['center_y'])
        wait_for_render(10)

        # Wait for quality check to complete (mock is fast)
        time.sleep(2.5)  # Allow thread to complete
        wait_for_render(15)

        # Verify quality check completed
        screen = lv.screen_active()
        print_screen_labels(screen)
        self.assertTrue(verify_text_present(screen, "Current calibration:"),
                       "Quality check results not shown")

        # Capture after quality check
        screenshot_path = f"{self.screenshot_dir}/calibrate_imu_02_quality.raw"
        capture_screenshot(screenshot_path)

        # Step 2: Click "Calibrate Now" button
        calibrate_btn = find_button_with_text(screen, "Calibrate Now")
        self.assertIsNotNone(calibrate_btn, "Could not find 'Calibrate Now' button")
        coords = get_widget_coords(calibrate_btn)
        simulate_click(coords['center_x'], coords['center_y'])
        wait_for_render(10)

        # Wait for calibration to complete (mock takes ~3 seconds)
        time.sleep(4.0)
        wait_for_render(15)

        # Verify calibration completed
        screen = lv.screen_active()
        print_screen_labels(screen)
        self.assertTrue(verify_text_present(screen, "Calibration successful!") or
                       verify_text_present(screen, "Calibration complete!"),
                       "Calibration completion message not found")

        # Capture completion state
        screenshot_path = f"{self.screenshot_dir}/calibrate_imu_03_complete.raw"
        capture_screenshot(screenshot_path)

        print("=== CalibrateIMUActivity flow test complete ===")

    def test_navigation_from_check_to_calibrate(self):
        """Test navigation from Check to Calibrate activity via button."""
        print("\n=== Testing Check -> Calibrate Navigation ===")

        # Navigate to Check activity
        result = mpos.apps.start_app("com.micropythonos.settings")
        self.assertTrue(result)
        wait_for_render(15)

        # Initialize touch device with dummy click
        simulate_click(10, 10)
        wait_for_render(10)

        screen = lv.screen_active()
        check_cal_label = find_label_with_text(screen, "Check IMU Calibration")
        coords = get_widget_coords(check_cal_label.get_parent())
        simulate_click(coords['center_x'], coords['center_y'])
        wait_for_render(30)  # Wait for real-time updates

        # Click "Calibrate" button
        screen = lv.screen_active()
        calibrate_btn = find_button_with_text(screen, "Calibrate")
        self.assertIsNotNone(calibrate_btn, "Could not find 'Calibrate' button")

        coords = get_widget_coords(calibrate_btn)
        simulate_click(coords['center_x'], coords['center_y'])
        wait_for_render(15)

        # Verify CalibrateIMUActivity loaded
        screen = lv.screen_active()
        self.assertTrue(verify_text_present(screen, "Check Quality"),
                       "Did not navigate to CalibrateIMUActivity")

        print("=== Navigation test complete ===")
