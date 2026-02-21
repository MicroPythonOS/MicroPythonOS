from mpos.imu.constants import GRAVITY
from mpos.imu.drivers.base import IMUDriverBase


class QMI8658Driver(IMUDriverBase):
    """Wrapper for QMI8658 IMU (Waveshare board)."""

    def __init__(self, i2c_bus, address):
        super().__init__()
        from drivers.imu_sensor.qmi8658 import QMI8658

        _ACCELSCALE_RANGE_8G = 0b10
        _GYROSCALE_RANGE_256DPS = 0b100
        self.sensor = QMI8658(
            i2c_bus,
            address=address,
            accel_scale=_ACCELSCALE_RANGE_8G,
            gyro_scale=_GYROSCALE_RANGE_256DPS,
        )

    def _raw_acceleration_mps2(self):
        ax, ay, az = self.sensor.acceleration
        return (ax * GRAVITY, ay * GRAVITY, az * GRAVITY)

    def _raw_gyroscope_dps(self):
        gx, gy, gz = self.sensor.gyro
        return (gx, gy, gz)

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
        return self.sensor.temperature
