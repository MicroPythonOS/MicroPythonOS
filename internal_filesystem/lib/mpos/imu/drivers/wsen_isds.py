from mpos.imu.constants import GRAVITY
from mpos.imu.drivers.base import IMUDriverBase


class WsenISDSDriver(IMUDriverBase):
    """Wrapper for WSEN_ISDS IMU (Fri3d badge)."""

    def __init__(self, i2c_bus, address):
        super().__init__()
        from drivers.imu_sensor.wsen_isds import Wsen_Isds

        self.sensor = Wsen_Isds(
            i2c_bus,
            address=address,
            acc_range="8g",
            acc_data_rate="104Hz",
            gyro_range="500dps",
            gyro_data_rate="104Hz",
        )

    def _raw_acceleration_mps2(self):
        ax, ay, az = self.sensor._read_raw_accelerations()
        return ((ax / 1000) * GRAVITY, (ay / 1000) * GRAVITY, (az / 1000) * GRAVITY)

    def _raw_gyroscope_dps(self):
        gx, gy, gz = self.sensor.read_angular_velocities()
        return (gx / 1000.0, gy / 1000.0, gz / 1000.0)

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
