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
import time
import sys
from mpos import (
    wait_for_render,
    find_label_with_text,
    verify_text_present,
    print_screen_labels,
    simulate_click,
    get_widget_coords,
    find_button_with_text,
    find_text_on_screen,
    AppManager
)


class TestIMUCalibration(unittest.TestCase):
    """Test suite for IMU calibration activities."""

    def _open_settings_item(self, title, timeout=2.0):
        start = time.time()
        label = None
        while time.time() - start < timeout:
            screen = lv.screen_active()
            label = find_label_with_text(screen, title)
            if label:
                break
            wait_for_render(iterations=5)
        self.assertIsNotNone(label, f"Could not find {title} menu item")
        container = None
        try:
            container = label.get_parent()
        except Exception:
            container = None
        if container:
            try:
                container.scroll_to_view(True)
            except Exception:
                pass
        else:
            try:
                label.scroll_to_view_recursive(True)
            except Exception:
                pass
        wait_for_render(iterations=20)
        target = container if container else label
        coords = get_widget_coords(target) or get_widget_coords(label)
        if coords:
            simulate_click(coords["center_x"], coords["center_y"])
        wait_for_render(iterations=30)

    def _start_activity_from_settings_assets(self, filename, classname):
        app_fullname = "com.micropythonos.settings"
        entrypoint = f"builtin/apps/{app_fullname}/assets/{filename}"
        cwd = f"builtin/apps/{app_fullname}/assets/"
        result = AppManager.execute_script(entrypoint, True, classname, cwd, app_fullname=app_fullname)
        self.assertTrue(result, f"Failed to start {classname} from {entrypoint}")
        wait_for_render(iterations=20)

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

        # Navigate directly to activity to avoid flaky settings clicks
        self._start_activity_from_settings_assets("check_imu_calibration.py", "CheckIMUCalibrationActivity")

        # Verify key elements are present
        screen = lv.screen_active()
        print_screen_labels(screen)
        self.assertTrue(verify_text_present(screen, "Quality"), "Quality label not found")
        self.assertTrue(verify_text_present(screen, "Accel."), "Accel. label not found")
        self.assertTrue(verify_text_present(screen, "Gyro"), "Gyro label not found")

        print("=== CheckIMUCalibrationActivity test complete ===")

    def test_calibrate_activity_flow(self):
        """Test CalibrateIMUActivity full calibration flow."""
        print("\n=== Testing CalibrateIMUActivity Flow ===")

        # Navigate directly to activity to avoid flaky settings clicks
        self._start_activity_from_settings_assets("calibrate_imu.py", "CalibrateIMUActivity")

        # Verify activity loaded and shows instructions
        screen = lv.screen_active()
        print_screen_labels(screen)
        self.assertTrue(verify_text_present(screen, "IMU Calibration"),
                       "CalibrateIMUActivity title not found")
        self.assertTrue(verify_text_present(screen, "Place device on flat"),
                       "Instructions not shown")

        # Click "Calibrate Now" button to start calibration
        calibrate_btn = find_button_with_text(screen, "Calibrate Now")
        self.assertIsNotNone(calibrate_btn, "Could not find 'Calibrate Now' button")
        calibrate_btn.send_event(lv.EVENT.CLICKED, None)
        wait_for_render(10)

        # Wait for calibration to complete (mock takes ~3 seconds)
        time.sleep(4)
        wait_for_render(40)

        # Verify calibration completed
        screen = lv.screen_active()
        print_screen_labels(screen)
        self.assertTrue(verify_text_present(screen, "Calibration successful!"),
                       "Calibration completion message not found")

        # Verify offsets are shown
        self.assertTrue(verify_text_present(screen, "Accel offsets") or
                       verify_text_present(screen, "offsets"),
                       "Calibration offsets not shown")

        print("=== CalibrateIMUActivity flow test complete ===")

    def test_navigation_from_check_to_calibrate(self):
        """Test navigation from Check to Calibrate activity via button."""
        print("\n=== Testing Check -> Calibrate Navigation ===")

        # Navigate directly to Check activity
        self._start_activity_from_settings_assets("check_imu_calibration.py", "CheckIMUCalibrationActivity")

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
            wait_for_render(30)
        finally:
            if added_path:
                try:
                    sys.path.remove(assets_path)
                except ValueError:
                    pass

        # Verify CalibrateIMUActivity loaded
        screen = lv.screen_active()
        print_screen_labels(screen)
        self.assertTrue(verify_text_present(screen, "Calibrate Now"),
                       "Did not navigate to CalibrateIMUActivity")
        self.assertTrue(verify_text_present(screen, "Place device on flat"),
                       "CalibrateIMUActivity instructions not shown")

        print("=== Navigation test complete ===")
