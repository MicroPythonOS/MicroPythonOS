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
import mpos.ui
import sys
from mpos import (
    wait_for_text,
    verify_text_present,
    print_screen_labels,
    find_button_with_text,
    AppManager
)


class TestIMUCalibration(unittest.TestCase):
    """Test suite for IMU calibration activities."""

    def _start_activity_from_settings_assets(self, filename, classname):
        app_fullname = "com.micropythonos.settings"
        entrypoint = f"builtin/apps/{app_fullname}/assets/{filename}"
        cwd = f"builtin/apps/{app_fullname}/assets/"
        result = AppManager.execute_script(entrypoint, classname, cwd, app_fullname=app_fullname)
        self.assertTrue(result, f"Failed to start {classname} from {entrypoint}")

    def tearDown(self):
        """Clean up after test."""
        mpos.ui.back_screen()

    def test_check_calibration_activity_loads(self):
        """Test that CheckIMUCalibrationActivity loads and displays."""
        print("\n=== Testing CheckIMUCalibrationActivity ===")

        # Navigate directly to activity to avoid flaky settings clicks
        self._start_activity_from_settings_assets("check_imu_calibration.py", "CheckIMUCalibrationActivity")

        # Wait for activity UI to render (polling, not fixed — handles slow CI)
        self.assertTrue(wait_for_text("Quality", timeout=10),
                        "CheckIMUCalibrationActivity: 'Quality' label not found within timeout")

        # Verify key elements are present
        screen = lv.screen_active()
        print_screen_labels(screen)
        self.assertTrue(verify_text_present(screen, "Accel."), "Accel. label not found")
        self.assertTrue(verify_text_present(screen, "Gyro"), "Gyro label not found")

        print("=== CheckIMUCalibrationActivity test complete ===")

    def test_calibrate_activity_flow(self):
        """Test CalibrateIMUActivity full calibration flow."""
        print("\n=== Testing CalibrateIMUActivity Flow ===")

        # Navigate directly to activity to avoid flaky settings clicks
        self._start_activity_from_settings_assets("calibrate_imu.py", "CalibrateIMUActivity")

        # Wait for activity UI to render (polling, not fixed)
        self.assertTrue(wait_for_text("IMU Calibration", timeout=10),
                        "CalibrateIMUActivity title not found within timeout")
        screen = lv.screen_active()
        print_screen_labels(screen)
        self.assertTrue(verify_text_present(screen, "Place device on flat"),
                       "Instructions not shown")

        # Click "Calibrate Now" button to start calibration
        calibrate_btn = find_button_with_text(screen, "Calibrate Now")
        self.assertIsNotNone(calibrate_btn, "Could not find 'Calibrate Now' button")
        calibrate_btn.send_event(lv.EVENT.CLICKED, None)

        # Wait for calibration to complete — poll for the success message
        # instead of fixed sleep (handles slow/fast CI equally well)
        self.assertTrue(
            wait_for_text("Calibration successful!", timeout=15),
            "Calibration completion message not found within timeout"
        )

        # Verify offsets are shown
        screen = lv.screen_active()
        print_screen_labels(screen)
        self.assertTrue(verify_text_present(screen, "Accel offsets") or
                       verify_text_present(screen, "offsets"),
                       "Calibration offsets not shown")

        print("=== CalibrateIMUActivity flow test complete ===")

    def test_navigation_from_check_to_calibrate(self):
        """Test navigation from Check to Calibrate activity via button."""
        print("\n=== Testing Check -> Calibrate Navigation ===")

        # Navigate directly to Check activity
        self._start_activity_from_settings_assets("check_imu_calibration.py", "CheckIMUCalibrationActivity")

        # Wait for Check activity to render
        self.assertTrue(wait_for_text("Quality", timeout=10),
                        "CheckIMUCalibrationActivity: 'Quality' label not found")

        # Click "Calibrate" button to navigate to Calibrate activity
        screen = lv.screen_active()
        calibrate_btn = find_button_with_text(screen, "Calibrate")
        self.assertIsNotNone(calibrate_btn, "Could not find 'Calibrate' button")

        assets_path = "builtin/apps/com.micropythonos.settings/assets/"
        added_path = False
        if assets_path not in sys.path:
            sys.path.append(assets_path)
            added_path = True
        try:
            calibrate_btn.send_event(lv.EVENT.CLICKED, None)
        finally:
            if added_path:
                try:
                    sys.path.remove(assets_path)
                except ValueError:
                    pass

        # Wait for CalibrateIMUActivity to load (polling, not fixed)
        self.assertTrue(
            wait_for_text("Calibrate Now", timeout=10),
            "Did not navigate to CalibrateIMUActivity within timeout"
        )
        screen = lv.screen_active()
        print_screen_labels(screen)
        self.assertTrue(verify_text_present(screen, "Place device on flat"),
                       "CalibrateIMUActivity instructions not shown")

        print("=== Navigation test complete ===")
