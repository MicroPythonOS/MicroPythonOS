"""Test for calibration check bug after calibrating.

Reproduces issue where check_calibration_quality() returns None after calibration.

Uses the real IMU via auto-detection (chip-ID probing in SensorManager), so it
works on both Waveshare (QMI8658) and fri3d_2026 (LSM6DSO). On desktop there is
no sensor hardware, so the deterministic mock driver is used instead.
"""
import os
import sys
import unittest

from mpos import SensorManager

_IS_DEVICE = sys.platform == "esp32"

_CALIBRATION_PATH = "prefs/com.micropythonos.settings/imu_calibration.json"


def _save_calibration_backup():
    """Read the current calibration file so it can be restored after the test."""
    try:
        with open(_CALIBRATION_PATH, "r") as f:
            return f.read()
    except OSError:
        return None


def _restore_calibration(backup):
    """Restore the calibration file that existed before the test (or remove it)."""
    try:
        os.remove(_CALIBRATION_PATH)
    except OSError:
        pass
    if backup is not None:
        dirname = os.path.dirname(_CALIBRATION_PATH)
        try:
            os.mkdir(dirname)
        except OSError:
            pass
        with open(_CALIBRATION_PATH, "w") as f:
            f.write(backup)


class TestCalibrationCheckBug(unittest.TestCase):
    """Test case for calibration check bug."""

    def setUp(self):
        """Set up test fixtures before each test."""
        if not _IS_DEVICE:
            # Deterministic static level device on desktop (no sensor HW).
            SensorManager.init_mock(motion=False)
        self._cal_backup = _save_calibration_backup()

    def tearDown(self):
        _restore_calibration(self._cal_backup)

    def test_check_quality_after_calibration(self):
        """Test that check_calibration_quality() works after calibration.

        This reproduces the bug where check_calibration_quality() returns
        None or shows "--" after performing calibration.
        """
        accel = SensorManager.get_default_sensor(SensorManager.TYPE_ACCELEROMETER)
        gyro = SensorManager.get_default_sensor(SensorManager.TYPE_GYROSCOPE)

        self.assertIsNotNone(accel, "Accelerometer should be available")
        self.assertIsNotNone(gyro, "Gyroscope should be available")

        # Step 1: Check calibration quality BEFORE calibration (should work)
        print("\n=== Step 1: Check quality BEFORE calibration ===")
        quality_before = SensorManager.check_calibration_quality(samples=10)
        self.assertIsNotNone(quality_before, "Quality check BEFORE calibration should return data")
        self.assertIn('quality_score', quality_before)
        print(f"Quality before: {quality_before['quality_rating']} ({quality_before['quality_score']:.2f})")

        # Step 2: Calibrate sensors
        print("\n=== Step 2: Calibrate sensors ===")
        accel_offsets = SensorManager.calibrate_sensor(accel, samples=10)
        print(f"Accel offsets: {accel_offsets}")
        self.assertIsNotNone(accel_offsets, "Accelerometer calibration should succeed")

        gyro_offsets = SensorManager.calibrate_sensor(gyro, samples=10)
        print(f"Gyro offsets: {gyro_offsets}")
        self.assertIsNotNone(gyro_offsets, "Gyroscope calibration should succeed")

        # Step 3: Check calibration quality AFTER calibration (BUG: returns None)
        print("\n=== Step 3: Check quality AFTER calibration ===")
        quality_after = SensorManager.check_calibration_quality(samples=10)
        self.assertIsNotNone(quality_after, "Quality check AFTER calibration should return data (BUG: returns None)")
        self.assertIn('quality_score', quality_after)
        print(f"Quality after: {quality_after['quality_rating']} ({quality_after['quality_score']:.2f})")

        # Verify sensor reads still work
        print("\n=== Step 4: Verify sensor reads still work ===")
        accel_data = SensorManager.read_sensor(accel)
        self.assertIsNotNone(accel_data, "Accelerometer should still be readable")
        print(f"Accel data: {accel_data}")

        gyro_data = SensorManager.read_sensor(gyro)
        self.assertIsNotNone(gyro_data, "Gyroscope should still be readable")
        print(f"Gyro data: {gyro_data}")


if __name__ == '__main__':
    unittest.main()