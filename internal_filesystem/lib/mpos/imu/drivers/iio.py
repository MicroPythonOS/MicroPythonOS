import os

from mpos.imu.drivers.base import IMUDriverBase


class IIODriver(IMUDriverBase):
    """
    Read sensor data via Linux IIO sysfs.

    Typical base path:
        /sys/bus/iio/devices/iio:device0
    """

    accel_path: str
    mag_path: str

    def __init__(self):
        super().__init__()
        self.accel_path = self.find_iio_device_with_file("in_accel_x_raw")
        self.mag_path = self.find_iio_device_with_file("in_magn_x_raw")

    def _p(self, name: str):
        return self.accel_path + "/" + name

    def _exists(self, name):
        try:
            os.stat(name)
            return True
        except OSError:
            return False

    def _is_dir(self, path):
        # MicroPython: stat tuple, mode is [0]
        try:
            st = os.stat(path)
            mode = st[0]
            # directory bit (POSIX): 0o040000
            return (mode & 0o170000) == 0o040000
        except OSError:
            return False

    def find_iio_device_with_file(self, filename, base_dir="/sys/bus/iio/devices/"):
        """
        Returns full path to iio:deviceX that contains given filename,
        e.g. "/sys/bus/iio/devices/iio:device0"

        Returns None if not found.
        """

        print("Is dir? ", self._is_dir(base_dir), base_dir)
        try:
            entries = os.listdir(base_dir)
        except OSError:
            print("Error listing dir")
            return None

        for entry in entries:
            print("Entry:", entry)
            if not entry.startswith("iio:device"):
                continue

            dev_path = base_dir + "/" + entry
            if not self._is_dir(dev_path):
                continue

            if self._exists(dev_path + "/" + filename):
                return dev_path

        return None

    def _read_text(self, name: str) -> str:
        print("Read: ", name)
        f = open(name, "r")
        try:
            return f.readline().strip()
        finally:
            f.close()

    def _read_float(self, name: str) -> float:
        return float(self._read_text(name))

    def _read_int(self, name: str) -> int:
        return int(self._read_text(name), 10)

    def _read_raw_scaled(self, raw_name: str, scale_name: str) -> float:
        raw = self._read_int(raw_name)
        scale = self._read_float(scale_name)
        return raw * scale

    def read_temperature(self) -> float:
        """
        Tries common IIO patterns:
          - in_temp_input (already scaled, usually millidegree C)
          - in_temp_raw + in_temp_scale
        """
        if not self.accel_path:
            return None

        raw_path = self.accel_path + "/" + "in_temp_raw"
        scale_path = self.accel_path + "/" + "in_temp_scale"
        if not self._exists(raw_path) or not self._exists(scale_path):
            return None
        return self._read_raw_scaled(raw_path, scale_path)

    def _raw_acceleration_mps2(self):
        if not self.accel_path:
            return (0.0, 0.0, 0.0)
        scale_name = self.accel_path + "/" + "in_accel_scale"

        ax = self._read_raw_scaled(self.accel_path + "/" + "in_accel_x_raw", scale_name)
        ay = self._read_raw_scaled(self.accel_path + "/" + "in_accel_y_raw", scale_name)
        az = self._read_raw_scaled(self.accel_path + "/" + "in_accel_z_raw", scale_name)

        return (ax, ay, az)

    def _raw_gyroscope_dps(self):
        if not self.accel_path:
            return (0.0, 0.0, 0.0)
        scale_name = self.accel_path + "/" + "in_anglvel_scale"

        gx = self._read_raw_scaled(self.accel_path + "/" + "in_anglvel_x_raw", scale_name)
        gy = self._read_raw_scaled(self.accel_path + "/" + "in_anglvel_y_raw", scale_name)
        gz = self._read_raw_scaled(self.accel_path + "/" + "in_anglvel_z_raw", scale_name)

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

    def read_magnetometer(self) -> tuple[float, float, float]:
        gx = self._read_raw_scaled(self.mag_path + "/" + "in_magn_x_raw", self.mag_path + "/" + "in_magn_x_scale")
        gy = self._read_raw_scaled(self.mag_path + "/" + "in_magn_y_raw", self.mag_path + "/" + "in_magn_y_scale")
        gz = self._read_raw_scaled(self.mag_path + "/" + "in_magn_z_raw", self.mag_path + "/" + "in_magn_z_scale")        

        return (gx, gy, gz)
