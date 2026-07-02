import time

from mpos.imu.constants import GRAVITY
from mpos.imu.drivers.base import IMUDriverBase


class BMA423Driver(IMUDriverBase):
    """Wrapper for BMA423 IMU (LilyGo T-Watch S3 Plus)."""

    def __init__(self, i2c_bus, address):
        super().__init__()
        from drivers.imu_sensor.bma423.bma423 import BMA423

        self.sensor = BMA423(i2c_bus, address=address, acc_range=2)
        time.sleep_ms(250)

    def _raw_acceleration_mps2(self):
        ax, ay, az = self.sensor.get_xyz()
        return (ax * GRAVITY, ay * GRAVITY, az * GRAVITY)

    def _raw_gyroscope_dps(self):
        return (0.0, 0.0, 0.0)

    def read_acceleration(self):
        ax, ay, az = self._raw_acceleration_mps2()
        return (
            ax - self.accel_offset[0],
            ay - self.accel_offset[1],
            az - self.accel_offset[2],
        )

    def read_gyroscope(self):
        gx, gy, gz = self._raw_gyroscope_dps()
        return (
            gx - self.gyro_offset[0],
            gy - self.gyro_offset[1],
            gz - self.gyro_offset[2],
        )

    def read_temperature(self):
        return self.sensor.get_temperature()
