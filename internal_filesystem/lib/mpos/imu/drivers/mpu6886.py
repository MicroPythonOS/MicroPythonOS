from mpos.imu.constants import GRAVITY
from mpos.imu.drivers.base import IMUDriverBase


class MPU6886Driver(IMUDriverBase):
    """Wrapper for MPU6886 IMU (Waveshare board)."""

    def __init__(self, i2c_bus, address):
        super().__init__()
        from drivers.imu_sensor.mpu6886 import MPU6886

        self.sensor = MPU6886(i2c_bus, address=address)

    def _raw_acceleration_mps2(self):
        ax, ay, az = self.sensor.acceleration
        return (ax * GRAVITY, ay * GRAVITY, az * GRAVITY)

    def _raw_gyroscope_dps(self):
        gx, gy, gz = self.sensor.gyro
        return (gx, gy, gz)

    def read_temperature(self):
        return self.sensor.temperature

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
