import time

from mpos.imu.constants import GRAVITY, FACING_EARTH


class IMUDriverBase:
    """Base class for IMU drivers with shared calibration logic."""

    def __init__(self):
        self.accel_offset = [0.0, 0.0, 0.0]
        self.gyro_offset = [0.0, 0.0, 0.0]

    def read_acceleration(self):
        """Returns (x, y, z) in m/s²"""
        raise NotImplementedError

    def read_gyroscope(self):
        """Returns (x, y, z) in deg/s"""
        raise NotImplementedError

    def read_magnetometer(self):
        """Returns (x, y, z) in uT"""
        raise NotImplementedError

    def read_temperature(self):
        """Returns temperature in °C"""
        raise NotImplementedError

    def _raw_acceleration_mps2(self):
        """Returns raw (x, y, z) in m/s² for calibration sampling."""
        raise NotImplementedError

    def _raw_gyroscope_dps(self):
        """Returns raw (x, y, z) in deg/s for calibration sampling."""
        raise NotImplementedError

    def calibrate_accelerometer(self, samples):
        """Calibrate accel, return (x, y, z) offsets in m/s²"""
        sum_x, sum_y, sum_z = 0.0, 0.0, 0.0

        for _ in range(samples):
            ax, ay, az = self._raw_acceleration_mps2()
            sum_x += ax
            sum_y += ay
            sum_z += az
            time.sleep_ms(10)

        if FACING_EARTH == FACING_EARTH:
            sum_z *= -1

        self.accel_offset[0] = sum_x / samples
        self.accel_offset[1] = sum_y / samples
        self.accel_offset[2] = (sum_z / samples) - GRAVITY

        return tuple(self.accel_offset)

    def calibrate_gyroscope(self, samples):
        """Calibrate gyro, return (x, y, z) offsets in deg/s"""
        sum_x, sum_y, sum_z = 0.0, 0.0, 0.0

        for _ in range(samples):
            gx, gy, gz = self._raw_gyroscope_dps()
            sum_x += gx
            sum_y += gy
            sum_z += gz
            time.sleep_ms(10)

        self.gyro_offset[0] = sum_x / samples
        self.gyro_offset[1] = sum_y / samples
        self.gyro_offset[2] = sum_z / samples

        return tuple(self.gyro_offset)

    def get_calibration(self):
        """Return dict with 'accel_offsets' and 'gyro_offsets' keys"""
        return {
            "accel_offsets": self.accel_offset,
            "gyro_offsets": self.gyro_offset,
        }

    def set_calibration(self, accel_offsets, gyro_offsets):
        """Set calibration offsets from saved values"""
        if accel_offsets:
            self.accel_offset = list(accel_offsets)
        if gyro_offsets:
            self.gyro_offset = list(gyro_offsets)
