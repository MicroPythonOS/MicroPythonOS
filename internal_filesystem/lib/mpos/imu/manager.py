import time

from mpos.imu.constants import (
    TYPE_ACCELEROMETER,
    TYPE_GYROSCOPE,
    TYPE_IMU_TEMPERATURE,
    TYPE_SOC_TEMPERATURE,
    TYPE_TEMPERATURE,
    FACING_EARTH,
    FACING_SKY,
    GRAVITY,
    IMU_CALIBRATION_FILENAME,
)
from mpos.imu.sensor import Sensor
from mpos.imu.drivers.iio import IIODriver
from mpos.imu.drivers.qmi8658 import QMI8658Driver
from mpos.imu.drivers.wsen_isds import WsenISDSDriver
from mpos.imu.drivers.mpu6886 import MPU6886Driver


class ImuManager:
    """Internal IMU manager (for SensorManager delegation)."""

    def __init__(self):
        self._initialized = False
        self._imu_driver = None
        self._sensor_list = []
        self._i2c_bus = None
        self._i2c_address = None
        self._mounted_position = FACING_SKY
        self._has_mcu_temperature = False

    def init(self, i2c_bus, address=0x6B, mounted_position=FACING_SKY):
        self._i2c_bus = i2c_bus
        self._i2c_address = address
        self._mounted_position = mounted_position

        try:
            import esp32

            _ = esp32.mcu_temperature()
            self._has_mcu_temperature = True
            self._register_mcu_temperature_sensor()
        except:
            pass

        self._initialized = True
        return True

    def init_iio(self):
        self._imu_driver = IIODriver()
        self._sensor_list = [
            Sensor(
                name="Accelerometer",
                sensor_type=TYPE_ACCELEROMETER,
                vendor="Linux IIO",
                version=1,
                max_range="?",
                resolution="?",
                power_ma=10,
            ),
            Sensor(
                name="Gyroscope",
                sensor_type=TYPE_GYROSCOPE,
                vendor="Linux IIO",
                version=1,
                max_range="?",
                resolution="?",
                power_ma=10,
            ),
            Sensor(
                name="Temperature",
                sensor_type=TYPE_IMU_TEMPERATURE,
                vendor="Linux IIO",
                version=1,
                max_range="?",
                resolution="?",
                power_ma=10,
            ),
        ]

        self._load_calibration()

        self._initialized = True
        return True

    def _ensure_imu_initialized(self):
        if not self._initialized or self._imu_driver is not None:
            return self._imu_driver is not None

        if self._i2c_bus:
            try:
                print("Try QMI8658 first (Waveshare board)")
                chip_id = self._i2c_bus.readfrom_mem(self._i2c_address, 0x00, 1)[0]
                print(f"{chip_id=:#04x}")
                if chip_id == 0x05:
                    self._imu_driver = QMI8658Driver(self._i2c_bus, self._i2c_address)
                    self._register_qmi8658_sensors()
                    self._load_calibration()
                    print("Use QMI8658, ok")
                    return True
            except Exception as exc:
                print("No QMI8658:", exc)

            try:
                print("Try WSEN_ISDS (fri3d_2024) or LSM6DSO (fri3d_2026)")
                chip_id = self._i2c_bus.readfrom_mem(self._i2c_address, 0x0F, 1)[0]
                print(f"{chip_id=:#04x}")
                if chip_id == 0x6A or chip_id == 0x6C:
                    self._imu_driver = WsenISDSDriver(self._i2c_bus, self._i2c_address)
                    self._register_wsen_isds_sensors()
                    self._load_calibration()
                    print("Use WSEN_ISDS/LSM6DSO, ok")
                    return True
            except Exception as exc:
                print("No WSEN_ISDS or LSM6DSO:", exc)

            try:
                print("Try MPU6886 (M5Stack FIRE)")
                chip_id = self._i2c_bus.readfrom_mem(self._i2c_address, 0x75, 1)[0]
                print(f"{chip_id=:#04x}")
                if chip_id == 0x19:
                    self._imu_driver = MPU6886Driver(self._i2c_bus, self._i2c_address)
                    self._register_mpu6886_sensors()
                    self._load_calibration()
                    print("Use MPU6886, ok")
                    return True
            except Exception as exc:
                print("No MPU6886:", exc)

        return False

    def is_available(self):
        return self._initialized

    def get_sensor_list(self):
        self._ensure_imu_initialized()
        return self._sensor_list.copy() if self._sensor_list else []

    def get_default_sensor(self, sensor_type):
        if self._initialized and sensor_type in (TYPE_ACCELEROMETER, TYPE_GYROSCOPE):
            self._ensure_imu_initialized()

        for sensor in self._sensor_list:
            if sensor.type == sensor_type:
                return sensor
        return None

    def read_sensor_once(self, sensor):
        if sensor.type == TYPE_ACCELEROMETER:
            if self._imu_driver:
                ax, ay, az = self._imu_driver.read_acceleration()
                if self._mounted_position == FACING_EARTH:
                    az *= -1
                return (ax, ay, az)
        elif sensor.type == TYPE_GYROSCOPE:
            if self._imu_driver:
                return self._imu_driver.read_gyroscope()
        elif sensor.type == TYPE_IMU_TEMPERATURE:
            if self._imu_driver:
                return self._imu_driver.read_temperature()
        elif sensor.type == TYPE_SOC_TEMPERATURE:
            if self._has_mcu_temperature:
                import esp32

                return esp32.mcu_temperature()
        elif sensor.type == TYPE_TEMPERATURE:
            if self._imu_driver:
                temp = self._imu_driver.read_temperature()
                if temp is not None:
                    return temp
            if self._has_mcu_temperature:
                import esp32

                return esp32.mcu_temperature()
        return None

    def read_sensor(self, sensor):
        if sensor is None:
            return None

        if sensor.type in (TYPE_ACCELEROMETER, TYPE_GYROSCOPE):
            self._ensure_imu_initialized()

        max_retries = 3
        retry_delay_ms = 20

        for attempt in range(max_retries):
            try:
                return self.read_sensor_once(sensor)
            except Exception as exc:
                import sys

                sys.print_exception(exc)
                error_msg = str(exc)
                if "data not ready" in error_msg and attempt < max_retries - 1:
                    time.sleep_ms(retry_delay_ms)
                    continue
                print("Exception reading sensor:", error_msg)
                return None

        return None

    def calibrate_sensor(self, sensor, samples=100):
        self._ensure_imu_initialized()
        if not self.is_available() or sensor is None:
            return None

        if sensor.type == TYPE_ACCELEROMETER:
            offsets = self._imu_driver.calibrate_accelerometer(samples)
        elif sensor.type == TYPE_GYROSCOPE:
            offsets = self._imu_driver.calibrate_gyroscope(samples)
        else:
            return None

        if offsets:
            self._save_calibration()

        return offsets

    def check_calibration_quality(self, samples=50):
        self._ensure_imu_initialized()
        if not self.is_available():
            return None

        try:
            accel = self.get_default_sensor(TYPE_ACCELEROMETER)
            gyro = self.get_default_sensor(TYPE_GYROSCOPE)

            accel_samples = [[], [], []]
            gyro_samples = [[], [], []]

            for _ in range(samples):
                if accel:
                    data = self.read_sensor(accel)
                    if data:
                        ax, ay, az = data
                        accel_samples[0].append(ax)
                        accel_samples[1].append(ay)
                        accel_samples[2].append(az)
                if gyro:
                    data = self.read_sensor(gyro)
                    if data:
                        gx, gy, gz = data
                        gyro_samples[0].append(gx)
                        gyro_samples[1].append(gy)
                        gyro_samples[2].append(gz)
                time.sleep_ms(10)

            accel_stats = [_calc_mean_variance(s) for s in accel_samples]
            gyro_stats = [_calc_mean_variance(s) for s in gyro_samples]

            accel_mean = tuple(s[0] for s in accel_stats)
            accel_variance = tuple(s[1] for s in accel_stats)
            gyro_mean = tuple(s[0] for s in gyro_stats)
            gyro_variance = tuple(s[1] for s in gyro_stats)

            issues = []
            scores = []

            if accel:
                accel_max_variance = max(accel_variance)
                variance_score = max(0.0, 1.0 - (accel_max_variance / 1.0))
                scores.append(variance_score)
                if accel_max_variance > 0.5:
                    issues.append(
                        f"High accelerometer variance: {accel_max_variance:.3f} m/s²"
                    )

                ax, ay, az = accel_mean
                xy_error = (abs(ax) + abs(ay)) / 2.0
                z_error = abs(az - GRAVITY)
                expected_score = max(0.0, 1.0 - ((xy_error + z_error) / 5.0))
                scores.append(expected_score)
                if xy_error > 1.0:
                    issues.append(
                        f"Accel X/Y not near zero: X={ax:.2f}, Y={ay:.2f} m/s²"
                    )
                if z_error > 1.0:
                    issues.append(f"Accel Z not near 9.8: Z={az:.2f} m/s²")

            if gyro:
                gyro_max_variance = max(gyro_variance)
                variance_score = max(0.0, 1.0 - (gyro_max_variance / 10.0))
                scores.append(variance_score)
                if gyro_max_variance > 5.0:
                    issues.append(
                        f"High gyroscope variance: {gyro_max_variance:.3f} deg/s"
                    )

                gx, gy, gz = gyro_mean
                error = (abs(gx) + abs(gy) + abs(gz)) / 3.0
                expected_score = max(0.0, 1.0 - (error / 10.0))
                scores.append(expected_score)
                if error > 2.0:
                    issues.append(
                        f"Gyro not near zero: X={gx:.2f}, Y={gy:.2f}, Z={gz:.2f} deg/s"
                    )

            quality_score = sum(scores) / len(scores) if scores else 0.0

            if quality_score >= 0.8:
                quality_rating = "Good"
            elif quality_score >= 0.5:
                quality_rating = "Fair"
            else:
                quality_rating = "Poor"

            return {
                "accel_mean": accel_mean,
                "accel_variance": accel_variance,
                "gyro_mean": gyro_mean,
                "gyro_variance": gyro_variance,
                "quality_score": quality_score,
                "quality_rating": quality_rating,
                "issues": issues,
            }

        except Exception as exc:
            print(f"[SensorManager] Error checking calibration quality: {exc}")
            return None

    def check_stationarity(
        self,
        samples=30,
        variance_threshold_accel=0.5,
        variance_threshold_gyro=5.0,
    ):
        self._ensure_imu_initialized()
        if not self.is_available():
            return None

        try:
            accel = self.get_default_sensor(TYPE_ACCELEROMETER)
            gyro = self.get_default_sensor(TYPE_GYROSCOPE)

            accel_samples = [[], [], []]
            gyro_samples = [[], [], []]

            for _ in range(samples):
                if accel:
                    data = self.read_sensor(accel)
                    if data:
                        ax, ay, az = data
                        accel_samples[0].append(ax)
                        accel_samples[1].append(ay)
                        accel_samples[2].append(az)
                if gyro:
                    data = self.read_sensor(gyro)
                    if data:
                        gx, gy, gz = data
                        gyro_samples[0].append(gx)
                        gyro_samples[1].append(gy)
                        gyro_samples[2].append(gz)
                time.sleep_ms(10)

            accel_var = [_calc_variance(s) for s in accel_samples]
            gyro_var = [_calc_variance(s) for s in gyro_samples]

            max_accel_var = max(accel_var) if accel_var else 0.0
            max_gyro_var = max(gyro_var) if gyro_var else 0.0

            accel_stationary = max_accel_var < variance_threshold_accel
            gyro_stationary = max_gyro_var < variance_threshold_gyro
            is_stationary = accel_stationary and gyro_stationary

            if is_stationary:
                message = "Device is stationary - ready to calibrate"
            else:
                problems = []
                if not accel_stationary:
                    problems.append(
                        f"movement detected (accel variance: {max_accel_var:.3f})"
                    )
                if not gyro_stationary:
                    problems.append(
                        f"rotation detected (gyro variance: {max_gyro_var:.3f})"
                    )
                message = f"Device NOT stationary: {', '.join(problems)}"

            return {
                "is_stationary": is_stationary,
                "accel_variance": max_accel_var,
                "gyro_variance": max_gyro_var,
                "message": message,
            }

        except Exception as exc:
            print(f"[SensorManager] Error checking stationarity: {exc}")
            return None

    def _register_qmi8658_sensors(self):
        self._sensor_list = [
            Sensor(
                name="QMI8658 Accelerometer",
                sensor_type=TYPE_ACCELEROMETER,
                vendor="QST Corporation",
                version=1,
                max_range="±8G (78.4 m/s²)",
                resolution="0.0024 m/s²",
                power_ma=0.2,
            ),
            Sensor(
                name="QMI8658 Gyroscope",
                sensor_type=TYPE_GYROSCOPE,
                vendor="QST Corporation",
                version=1,
                max_range="±256 deg/s",
                resolution="0.002 deg/s",
                power_ma=0.7,
            ),
            Sensor(
                name="QMI8658 Temperature",
                sensor_type=TYPE_IMU_TEMPERATURE,
                vendor="QST Corporation",
                version=1,
                max_range="-40°C to +85°C",
                resolution="0.004°C",
                power_ma=0,
            ),
        ]

    def _register_mpu6886_sensors(self):
        self._sensor_list = [
            Sensor(
                name="MPU6886 Accelerometer",
                sensor_type=TYPE_ACCELEROMETER,
                vendor="InvenSense",
                version=1,
                max_range="±16g",
                resolution="0.0024 m/s²",
                power_ma=0.2,
            ),
            Sensor(
                name="MPU6886 Gyroscope",
                sensor_type=TYPE_GYROSCOPE,
                vendor="InvenSense",
                version=1,
                max_range="±256 deg/s",
                resolution="0.002 deg/s",
                power_ma=0.7,
            ),
            Sensor(
                name="MPU6886 Temperature",
                sensor_type=TYPE_IMU_TEMPERATURE,
                vendor="InvenSense",
                version=1,
                max_range="-40°C to +85°C",
                resolution="0.05°C",
                power_ma=0,
            ),
        ]

    def _register_wsen_isds_sensors(self):
        self._sensor_list = [
            Sensor(
                name="WSEN_ISDS Accelerometer",
                sensor_type=TYPE_ACCELEROMETER,
                vendor="Würth Elektronik",
                version=1,
                max_range="±8G (78.4 m/s²)",
                resolution="0.0024 m/s²",
                power_ma=0.2,
            ),
            Sensor(
                name="WSEN_ISDS Gyroscope",
                sensor_type=TYPE_GYROSCOPE,
                vendor="Würth Elektronik",
                version=1,
                max_range="±500 deg/s",
                resolution="0.0175 deg/s",
                power_ma=0.65,
            ),
            Sensor(
                name="WSEN_ISDS Temperature",
                sensor_type=TYPE_IMU_TEMPERATURE,
                vendor="Würth Elektronik",
                version=1,
                max_range="-40°C to +85°C",
                resolution="0.004°C",
                power_ma=0,
            ),
        ]

    def _register_mcu_temperature_sensor(self):
        self._sensor_list.append(
            Sensor(
                name="ESP32 MCU Temperature",
                sensor_type=TYPE_SOC_TEMPERATURE,
                vendor="Espressif",
                version=1,
                max_range="-40°C to +125°C",
                resolution="0.5°C",
                power_ma=0,
            )
        )

    def _load_calibration(self):
        if not self._imu_driver:
            return

        try:
            from mpos.config import SharedPreferences

            prefs_new = SharedPreferences(
                "com.micropythonos.settings", filename=IMU_CALIBRATION_FILENAME
            )
            accel_offsets = prefs_new.get_list("accel_offsets")
            gyro_offsets = prefs_new.get_list("gyro_offsets")

            if accel_offsets or gyro_offsets:
                self._imu_driver.set_calibration(accel_offsets, gyro_offsets)
        except:
            pass

    def _save_calibration(self):
        if not self._imu_driver:
            return

        try:
            from mpos.config import SharedPreferences

            prefs = SharedPreferences(
                "com.micropythonos.settings", filename=IMU_CALIBRATION_FILENAME
            )
            editor = prefs.edit()

            cal = self._imu_driver.get_calibration()
            editor.put_list("accel_offsets", list(cal["accel_offsets"]))
            editor.put_list("gyro_offsets", list(cal["gyro_offsets"]))
            editor.commit()
        except:
            pass


def _calc_mean_variance(samples_list):
    if not samples_list:
        return 0.0, 0.0
    n = len(samples_list)
    mean = sum(samples_list) / n
    variance = sum((x - mean) ** 2 for x in samples_list) / n
    return mean, variance


def _calc_variance(samples_list):
    if not samples_list:
        return 0.0
    n = len(samples_list)
    mean = sum(samples_list) / n
    return sum((x - mean) ** 2 for x in samples_list) / n
