"""Android-inspired SensorManager for MicroPythonOS.

Provides unified access to IMU sensors (QMI8658, WSEN_ISDS) and other sensors.
Follows module-level singleton pattern (like AudioFlinger, LightsManager).

Example usage:
    import mpos.sensor_manager as SensorManager

    # In board init file:
    SensorManager.init(i2c_bus, address=0x6B)

    # In app:
    if SensorManager.is_available():
        accel = SensorManager.get_default_sensor(SensorManager.TYPE_ACCELEROMETER)
        ax, ay, az = SensorManager.read_sensor(accel)  # Returns m/s²

MIT License
Copyright (c) 2024 MicroPythonOS contributors
"""

import time
try:
    import _thread
    _lock = _thread.allocate_lock()
except ImportError:
    _lock = None

# Sensor type constants (matching Android SensorManager)
TYPE_ACCELEROMETER = 1      # Units: m/s² (meters per second squared)
TYPE_GYROSCOPE = 4          # Units: deg/s (degrees per second)
TYPE_TEMPERATURE = 13       # Units: °C (generic, returns first available - deprecated)
TYPE_IMU_TEMPERATURE = 14   # Units: °C (IMU chip temperature)
TYPE_SOC_TEMPERATURE = 15   # Units: °C (MCU/SoC internal temperature)

# Gravity constant for unit conversions
_GRAVITY = 9.80665  # m/s²

# Module state
_initialized = False
_imu_driver = None
_sensor_list = []
_i2c_bus = None
_i2c_address = None
_has_mcu_temperature = False


class Sensor:
    """Sensor metadata (lightweight data class, Android-inspired)."""

    def __init__(self, name, sensor_type, vendor, version, max_range, resolution, power_ma):
        """Initialize sensor metadata.

        Args:
            name: Human-readable sensor name
            sensor_type: Sensor type constant (TYPE_ACCELEROMETER, etc.)
            vendor: Sensor vendor/manufacturer
            version: Driver version
            max_range: Maximum measurement range (with units)
            resolution: Measurement resolution (with units)
            power_ma: Power consumption in mA (or 0 if unknown)
        """
        self.name = name
        self.type = sensor_type
        self.vendor = vendor
        self.version = version
        self.max_range = max_range
        self.resolution = resolution
        self.power = power_ma

    def __repr__(self):
        return f"Sensor({self.name}, type={self.type})"


def init(i2c_bus, address=0x6B):
    """Initialize SensorManager. MCU temperature initializes immediately, IMU initializes on first use.

    Args:
        i2c_bus: machine.I2C instance (can be None if only MCU temperature needed)
        address: I2C address (default 0x6B for both QMI8658 and WSEN_ISDS)

    Returns:
        bool: True if initialized successfully
    """
    global _i2c_bus, _i2c_address, _initialized, _has_mcu_temperature

    _i2c_bus = i2c_bus
    _i2c_address = address

    # Initialize MCU temperature sensor immediately (fast, no I2C needed)
    try:
        import esp32
        _ = esp32.mcu_temperature()
        _has_mcu_temperature = True
        _register_mcu_temperature_sensor()
    except:
        pass

    _initialized = True
    return True


def _ensure_imu_initialized():
    """Perform IMU initialization on first use (lazy initialization).

    Tries to detect QMI8658 (chip ID 0x05) or WSEN_ISDS (WHO_AM_I 0x6A).
    Loads calibration from SharedPreferences if available.

    Returns:
        bool: True if IMU detected and initialized successfully
    """
    global _imu_driver, _sensor_list

    if not _initialized or _imu_driver is not None:
        return _imu_driver is not None

    # Try QMI8658 first (Waveshare board)
    if _i2c_bus:
        try:
            from mpos.hardware.drivers.qmi8658 import QMI8658
            chip_id = _i2c_bus.readfrom_mem(_i2c_address, 0x00, 1)[0]  # PARTID register
            if chip_id == 0x05:  # QMI8685_PARTID
                _imu_driver = _QMI8658Driver(_i2c_bus, _i2c_address)
                _register_qmi8658_sensors()
                _load_calibration()
                return True
        except:
            pass

        # Try WSEN_ISDS (Fri3d badge)
        try:
            from mpos.hardware.drivers.wsen_isds import Wsen_Isds
            chip_id = _i2c_bus.readfrom_mem(_i2c_address, 0x0F, 1)[0]  # WHO_AM_I register
            if chip_id == 0x6A:  # WSEN_ISDS WHO_AM_I
                _imu_driver = _WsenISDSDriver(_i2c_bus, _i2c_address)
                _register_wsen_isds_sensors()
                _load_calibration()
                return True
        except:
            pass

    return False


def is_available():
    """Check if sensors are available.

    Does NOT trigger IMU initialization (to avoid boot-time initialization).
    Use get_default_sensor() or read_sensor() to lazily initialize IMU.

    Returns:
        bool: True if SensorManager is initialized (may only have MCU temp, not IMU)
    """
    return _initialized


def get_sensor_list():
    """Get list of all available sensors.

    Performs lazy IMU initialization on first call.

    Returns:
        list: List of Sensor objects
    """
    _ensure_imu_initialized()
    return _sensor_list.copy() if _sensor_list else []


def get_default_sensor(sensor_type):
    """Get default sensor of given type.

    Performs lazy IMU initialization on first call.

    Args:
        sensor_type: Sensor type constant (TYPE_ACCELEROMETER, etc.)

    Returns:
        Sensor object or None if not available
    """
    # Only initialize IMU if requesting IMU sensor types
    if sensor_type in (TYPE_ACCELEROMETER, TYPE_GYROSCOPE):
        _ensure_imu_initialized()

    for sensor in _sensor_list:
        if sensor.type == sensor_type:
            return sensor
    return None


def read_sensor(sensor):
    """Read sensor data synchronously.

    Performs lazy IMU initialization on first call for IMU sensors.

    Args:
        sensor: Sensor object from get_default_sensor()

    Returns:
        For motion sensors: tuple (x, y, z) in appropriate units
        For scalar sensors: single value
        None if sensor not available or error
    """
    if sensor is None:
        return None

    # Only initialize IMU if reading IMU sensor
    if sensor.type in (TYPE_ACCELEROMETER, TYPE_GYROSCOPE):
        _ensure_imu_initialized()

    if _lock:
        _lock.acquire()

    try:
        # Retry logic for "sensor data not ready" (WSEN_ISDS needs time after init)
        max_retries = 3
        retry_delay_ms = 20  # Wait 20ms between retries

        for attempt in range(max_retries):
            try:
                if sensor.type == TYPE_ACCELEROMETER:
                    if _imu_driver:
                        return _imu_driver.read_acceleration()
                elif sensor.type == TYPE_GYROSCOPE:
                    if _imu_driver:
                        return _imu_driver.read_gyroscope()
                elif sensor.type == TYPE_IMU_TEMPERATURE:
                    if _imu_driver:
                        return _imu_driver.read_temperature()
                elif sensor.type == TYPE_SOC_TEMPERATURE:
                    if _has_mcu_temperature:
                        import esp32
                        return esp32.mcu_temperature()
                elif sensor.type == TYPE_TEMPERATURE:
                    # Generic temperature - return first available (backward compatibility)
                    if _imu_driver:
                        temp = _imu_driver.read_temperature()
                        if temp is not None:
                            return temp
                    if _has_mcu_temperature:
                        import esp32
                        return esp32.mcu_temperature()
                return None
            except Exception as e:
                error_msg = str(e)
                # Retry if sensor data not ready, otherwise fail immediately
                if "data not ready" in error_msg and attempt < max_retries - 1:
                    import time
                    time.sleep_ms(retry_delay_ms)
                    continue
                else:
                    return None

        return None
    finally:
        if _lock:
            _lock.release()


def calibrate_sensor(sensor, samples=100):
    """Calibrate sensor and save to SharedPreferences.

    Performs lazy IMU initialization on first call.
    Device must be stationary for accelerometer/gyroscope calibration.

    Args:
        sensor: Sensor object to calibrate
        samples: Number of samples to average (default 100)

    Returns:
        tuple: Calibration offsets (x, y, z) or None if failed
    """
    _ensure_imu_initialized()
    if not is_available() or sensor is None:
        return None

    if _lock:
        _lock.acquire()

    try:
        if sensor.type == TYPE_ACCELEROMETER:
            offsets = _imu_driver.calibrate_accelerometer(samples)
        elif sensor.type == TYPE_GYROSCOPE:
            offsets = _imu_driver.calibrate_gyroscope(samples)
        else:
            return None

        if offsets:
            _save_calibration()

        return offsets
    except Exception as e:
        print(f"[SensorManager] Calibration error: {e}")
        return None
    finally:
        if _lock:
            _lock.release()


# Helper functions for calibration quality checking (module-level to avoid nested def issues)
def _calc_mean_variance(samples_list):
    """Calculate mean and variance for a list of samples."""
    if not samples_list:
        return 0.0, 0.0
    n = len(samples_list)
    mean = sum(samples_list) / n
    variance = sum((x - mean) ** 2 for x in samples_list) / n
    return mean, variance


def _calc_variance(samples_list):
    """Calculate variance for a list of samples."""
    if not samples_list:
        return 0.0
    n = len(samples_list)
    mean = sum(samples_list) / n
    return sum((x - mean) ** 2 for x in samples_list) / n


def check_calibration_quality(samples=50):
    """Check quality of current calibration.

    Performs lazy IMU initialization on first call.

    Args:
        samples: Number of samples to collect (default 50)

    Returns:
        dict with:
            - accel_mean: (x, y, z) mean values in m/s²
            - accel_variance: (x, y, z) variance values
            - gyro_mean: (x, y, z) mean values in deg/s
            - gyro_variance: (x, y, z) variance values
            - quality_score: float 0.0-1.0 (1.0 = perfect)
            - quality_rating: string ("Good", "Fair", "Poor")
            - issues: list of strings describing problems
        None if IMU not available
    """
    _ensure_imu_initialized()
    if not is_available():
        return None

    # Don't acquire lock here - let read_sensor() handle it per-read
    # (avoids deadlock since read_sensor also acquires the lock)
    try:
        accel = get_default_sensor(TYPE_ACCELEROMETER)
        gyro = get_default_sensor(TYPE_GYROSCOPE)

        # Collect samples
        accel_samples = [[], [], []]  # x, y, z lists
        gyro_samples = [[], [], []]

        for _ in range(samples):
            if accel:
                data = read_sensor(accel)
                if data:
                    ax, ay, az = data
                    accel_samples[0].append(ax)
                    accel_samples[1].append(ay)
                    accel_samples[2].append(az)
            if gyro:
                data = read_sensor(gyro)
                if data:
                    gx, gy, gz = data
                    gyro_samples[0].append(gx)
                    gyro_samples[1].append(gy)
                    gyro_samples[2].append(gz)
            time.sleep_ms(10)

        # Calculate statistics using module-level helper
        accel_stats = [_calc_mean_variance(s) for s in accel_samples]
        gyro_stats = [_calc_mean_variance(s) for s in gyro_samples]

        accel_mean = tuple(s[0] for s in accel_stats)
        accel_variance = tuple(s[1] for s in accel_stats)
        gyro_mean = tuple(s[0] for s in gyro_stats)
        gyro_variance = tuple(s[1] for s in gyro_stats)

        # Calculate quality score (0.0 - 1.0)
        issues = []
        scores = []

        # Check accelerometer
        if accel:
            # Variance check (lower is better)
            accel_max_variance = max(accel_variance)
            variance_score = max(0.0, 1.0 - (accel_max_variance / 1.0))  # 1.0 m/s² variance threshold
            scores.append(variance_score)
            if accel_max_variance > 0.5:
                issues.append(f"High accelerometer variance: {accel_max_variance:.3f} m/s²")

            # Expected values check (X≈0, Y≈0, Z≈9.8)
            ax, ay, az = accel_mean
            xy_error = (abs(ax) + abs(ay)) / 2.0
            z_error = abs(az - _GRAVITY)
            expected_score = max(0.0, 1.0 - ((xy_error + z_error) / 5.0))  # 5.0 m/s² error threshold
            scores.append(expected_score)
            if xy_error > 1.0:
                issues.append(f"Accel X/Y not near zero: X={ax:.2f}, Y={ay:.2f} m/s²")
            if z_error > 1.0:
                issues.append(f"Accel Z not near 9.8: Z={az:.2f} m/s²")

        # Check gyroscope
        if gyro:
            # Variance check
            gyro_max_variance = max(gyro_variance)
            variance_score = max(0.0, 1.0 - (gyro_max_variance / 10.0))  # 10 deg/s variance threshold
            scores.append(variance_score)
            if gyro_max_variance > 5.0:
                issues.append(f"High gyroscope variance: {gyro_max_variance:.3f} deg/s")

            # Expected values check (all ≈0)
            gx, gy, gz = gyro_mean
            error = (abs(gx) + abs(gy) + abs(gz)) / 3.0
            expected_score = max(0.0, 1.0 - (error / 10.0))  # 10 deg/s error threshold
            scores.append(expected_score)
            if error > 2.0:
                issues.append(f"Gyro not near zero: X={gx:.2f}, Y={gy:.2f}, Z={gz:.2f} deg/s")

        # Overall quality score
        quality_score = sum(scores) / len(scores) if scores else 0.0

        # Rating
        if quality_score >= 0.8:
            quality_rating = "Good"
        elif quality_score >= 0.5:
            quality_rating = "Fair"
        else:
            quality_rating = "Poor"

        return {
            'accel_mean': accel_mean,
            'accel_variance': accel_variance,
            'gyro_mean': gyro_mean,
            'gyro_variance': gyro_variance,
            'quality_score': quality_score,
            'quality_rating': quality_rating,
            'issues': issues
        }

    except Exception as e:
        print(f"[SensorManager] Error checking calibration quality: {e}")
        return None


def check_stationarity(samples=30, variance_threshold_accel=0.5, variance_threshold_gyro=5.0):
    """Check if device is stationary (required for calibration).

    Args:
        samples: Number of samples to collect (default 30)
        variance_threshold_accel: Max acceptable accel variance in m/s² (default 0.5)
        variance_threshold_gyro: Max acceptable gyro variance in deg/s (default 5.0)

    Returns:
        dict with:
            - is_stationary: bool
            - accel_variance: max variance across axes
            - gyro_variance: max variance across axes
            - message: string describing result
        None if IMU not available
    """
    _ensure_imu_initialized()
    if not is_available():
        return None

    # Don't acquire lock here - let read_sensor() handle it per-read
    # (avoids deadlock since read_sensor also acquires the lock)
    try:
        accel = get_default_sensor(TYPE_ACCELEROMETER)
        gyro = get_default_sensor(TYPE_GYROSCOPE)

        # Collect samples
        accel_samples = [[], [], []]
        gyro_samples = [[], [], []]

        for _ in range(samples):
            if accel:
                data = read_sensor(accel)
                if data:
                    ax, ay, az = data
                    accel_samples[0].append(ax)
                    accel_samples[1].append(ay)
                    accel_samples[2].append(az)
            if gyro:
                data = read_sensor(gyro)
                if data:
                    gx, gy, gz = data
                    gyro_samples[0].append(gx)
                    gyro_samples[1].append(gy)
                    gyro_samples[2].append(gz)
            time.sleep_ms(10)

        # Calculate variance using module-level helper
        accel_var = [_calc_variance(s) for s in accel_samples]
        gyro_var = [_calc_variance(s) for s in gyro_samples]

        max_accel_var = max(accel_var) if accel_var else 0.0
        max_gyro_var = max(gyro_var) if gyro_var else 0.0

        # Check thresholds
        accel_stationary = max_accel_var < variance_threshold_accel
        gyro_stationary = max_gyro_var < variance_threshold_gyro
        is_stationary = accel_stationary and gyro_stationary

        # Generate message
        if is_stationary:
            message = "Device is stationary - ready to calibrate"
        else:
            problems = []
            if not accel_stationary:
                problems.append(f"movement detected (accel variance: {max_accel_var:.3f})")
            if not gyro_stationary:
                problems.append(f"rotation detected (gyro variance: {max_gyro_var:.3f})")
            message = f"Device NOT stationary: {', '.join(problems)}"

        return {
            'is_stationary': is_stationary,
            'accel_variance': max_accel_var,
            'gyro_variance': max_gyro_var,
            'message': message
        }

    except Exception as e:
        print(f"[SensorManager] Error checking stationarity: {e}")
        return None


# ============================================================================
# Internal driver abstraction layer
# ============================================================================

class _IMUDriver:
    """Base class for IMU drivers (internal use only)."""

    def read_acceleration(self):
        """Returns (x, y, z) in m/s²"""
        raise NotImplementedError

    def read_gyroscope(self):
        """Returns (x, y, z) in deg/s"""
        raise NotImplementedError

    def read_temperature(self):
        """Returns temperature in °C"""
        raise NotImplementedError

    def calibrate_accelerometer(self, samples):
        """Calibrate accel, return (x, y, z) offsets in m/s²"""
        raise NotImplementedError

    def calibrate_gyroscope(self, samples):
        """Calibrate gyro, return (x, y, z) offsets in deg/s"""
        raise NotImplementedError

    def get_calibration(self):
        """Return dict with 'accel_offsets' and 'gyro_offsets' keys"""
        raise NotImplementedError

    def set_calibration(self, accel_offsets, gyro_offsets):
        """Set calibration offsets from saved values"""
        raise NotImplementedError


class _QMI8658Driver(_IMUDriver):
    """Wrapper for QMI8658 IMU (Waveshare board)."""

    def __init__(self, i2c_bus, address):
        from mpos.hardware.drivers.qmi8658 import QMI8658
        # QMI8658 scale constants (can't import const() values)
        _ACCELSCALE_RANGE_8G = 0b10
        _GYROSCALE_RANGE_256DPS = 0b100
        self.sensor = QMI8658(
            i2c_bus,
            address=address,
            accel_scale=_ACCELSCALE_RANGE_8G,
            gyro_scale=_GYROSCALE_RANGE_256DPS
        )
        # Software calibration offsets (QMI8658 has no built-in calibration)
        self.accel_offset = [0.0, 0.0, 0.0]
        self.gyro_offset = [0.0, 0.0, 0.0]

    def read_acceleration(self):
        """Read acceleration in m/s² (converts from G)."""
        ax, ay, az = self.sensor.acceleration
        # Convert G to m/s² and apply calibration
        return (
            (ax * _GRAVITY) - self.accel_offset[0],
            (ay * _GRAVITY) - self.accel_offset[1],
            (az * _GRAVITY) - self.accel_offset[2]
        )

    def read_gyroscope(self):
        """Read gyroscope in deg/s (already in correct units)."""
        gx, gy, gz = self.sensor.gyro
        # Apply calibration
        return (
            gx - self.gyro_offset[0],
            gy - self.gyro_offset[1],
            gz - self.gyro_offset[2]
        )

    def read_temperature(self):
        """Read temperature in °C."""
        return self.sensor.temperature

    def calibrate_accelerometer(self, samples):
        """Calibrate accelerometer (device must be stationary)."""
        sum_x, sum_y, sum_z = 0.0, 0.0, 0.0

        for _ in range(samples):
            ax, ay, az = self.sensor.acceleration
            sum_x += ax * _GRAVITY
            sum_y += ay * _GRAVITY
            sum_z += az * _GRAVITY
            time.sleep_ms(10)

        # Average offsets (assuming Z-axis should read +9.8 m/s²)
        self.accel_offset[0] = sum_x / samples
        self.accel_offset[1] = sum_y / samples
        self.accel_offset[2] = (sum_z / samples) - _GRAVITY

        return tuple(self.accel_offset)

    def calibrate_gyroscope(self, samples):
        """Calibrate gyroscope (device must be stationary)."""
        sum_x, sum_y, sum_z = 0.0, 0.0, 0.0

        for _ in range(samples):
            gx, gy, gz = self.sensor.gyro
            sum_x += gx
            sum_y += gy
            sum_z += gz
            time.sleep_ms(10)

        # Average offsets (should be 0 when stationary)
        self.gyro_offset[0] = sum_x / samples
        self.gyro_offset[1] = sum_y / samples
        self.gyro_offset[2] = sum_z / samples

        return tuple(self.gyro_offset)

    def get_calibration(self):
        """Get current calibration."""
        return {
            'accel_offsets': self.accel_offset,
            'gyro_offsets': self.gyro_offset
        }

    def set_calibration(self, accel_offsets, gyro_offsets):
        """Set calibration from saved values."""
        if accel_offsets:
            self.accel_offset = list(accel_offsets)
        if gyro_offsets:
            self.gyro_offset = list(gyro_offsets)


class _WsenISDSDriver(_IMUDriver):
    """Wrapper for WSEN_ISDS IMU (Fri3d badge)."""

    def __init__(self, i2c_bus, address):
        from mpos.hardware.drivers.wsen_isds import Wsen_Isds
        self.sensor = Wsen_Isds(
            i2c_bus,
            address=address,
            acc_range="8g",
            acc_data_rate="104Hz",
            gyro_range="500dps",
            gyro_data_rate="104Hz"
        )

    def read_acceleration(self):
        """Read acceleration in m/s² (converts from mg)."""
        ax, ay, az = self.sensor.read_accelerations()
        # Convert mg to m/s²: mg → g → m/s²
        return (
            (ax / 1000.0) * _GRAVITY,
            (ay / 1000.0) * _GRAVITY,
            (az / 1000.0) * _GRAVITY
        )

    def read_gyroscope(self):
        """Read gyroscope in deg/s (converts from mdps)."""
        gx, gy, gz = self.sensor.read_angular_velocities()
        # Convert mdps to deg/s
        return (
            gx / 1000.0,
            gy / 1000.0,
            gz / 1000.0
        )

    def read_temperature(self):
        """Read temperature in °C (not implemented in WSEN_ISDS driver)."""
        # WSEN_ISDS has temperature sensor but not exposed in current driver
        return None

    def calibrate_accelerometer(self, samples):
        """Calibrate accelerometer using hardware calibration."""
        self.sensor.acc_calibrate(samples)
        # Return offsets in m/s² (convert from raw offsets)
        return (
            (self.sensor.acc_offset_x * self.sensor.acc_sensitivity / 1000.0) * _GRAVITY,
            (self.sensor.acc_offset_y * self.sensor.acc_sensitivity / 1000.0) * _GRAVITY,
            (self.sensor.acc_offset_z * self.sensor.acc_sensitivity / 1000.0) * _GRAVITY
        )

    def calibrate_gyroscope(self, samples):
        """Calibrate gyroscope using hardware calibration."""
        self.sensor.gyro_calibrate(samples)
        # Return offsets in deg/s (convert from raw offsets)
        return (
            (self.sensor.gyro_offset_x * self.sensor.gyro_sensitivity) / 1000.0,
            (self.sensor.gyro_offset_y * self.sensor.gyro_sensitivity) / 1000.0,
            (self.sensor.gyro_offset_z * self.sensor.gyro_sensitivity) / 1000.0
        )

    def get_calibration(self):
        """Get current calibration (raw offsets from hardware)."""
        return {
            'accel_offsets': [
                self.sensor.acc_offset_x,
                self.sensor.acc_offset_y,
                self.sensor.acc_offset_z
            ],
            'gyro_offsets': [
                self.sensor.gyro_offset_x,
                self.sensor.gyro_offset_y,
                self.sensor.gyro_offset_z
            ]
        }

    def set_calibration(self, accel_offsets, gyro_offsets):
        """Set calibration from saved values (raw offsets)."""
        if accel_offsets:
            self.sensor.acc_offset_x = accel_offsets[0]
            self.sensor.acc_offset_y = accel_offsets[1]
            self.sensor.acc_offset_z = accel_offsets[2]
        if gyro_offsets:
            self.sensor.gyro_offset_x = gyro_offsets[0]
            self.sensor.gyro_offset_y = gyro_offsets[1]
            self.sensor.gyro_offset_z = gyro_offsets[2]


# ============================================================================
# Sensor registration (internal)
# ============================================================================

def _register_qmi8658_sensors():
    """Register QMI8658 sensors in sensor list."""
    global _sensor_list
    _sensor_list = [
        Sensor(
            name="QMI8658 Accelerometer",
            sensor_type=TYPE_ACCELEROMETER,
            vendor="QST Corporation",
            version=1,
            max_range="±8G (78.4 m/s²)",
            resolution="0.0024 m/s²",
            power_ma=0.2
        ),
        Sensor(
            name="QMI8658 Gyroscope",
            sensor_type=TYPE_GYROSCOPE,
            vendor="QST Corporation",
            version=1,
            max_range="±256 deg/s",
            resolution="0.002 deg/s",
            power_ma=0.7
        ),
        Sensor(
            name="QMI8658 Temperature",
            sensor_type=TYPE_IMU_TEMPERATURE,
            vendor="QST Corporation",
            version=1,
            max_range="-40°C to +85°C",
            resolution="0.004°C",
            power_ma=0
        )
    ]


def _register_wsen_isds_sensors():
    """Register WSEN_ISDS sensors in sensor list."""
    global _sensor_list
    _sensor_list = [
        Sensor(
            name="WSEN_ISDS Accelerometer",
            sensor_type=TYPE_ACCELEROMETER,
            vendor="Würth Elektronik",
            version=1,
            max_range="±8G (78.4 m/s²)",
            resolution="0.0024 m/s²",
            power_ma=0.2
        ),
        Sensor(
            name="WSEN_ISDS Gyroscope",
            sensor_type=TYPE_GYROSCOPE,
            vendor="Würth Elektronik",
            version=1,
            max_range="±500 deg/s",
            resolution="0.0175 deg/s",
            power_ma=0.65
        )
    ]


def _register_mcu_temperature_sensor():
    """Register MCU internal temperature sensor in sensor list."""
    global _sensor_list
    _sensor_list.append(
        Sensor(
            name="ESP32 MCU Temperature",
            sensor_type=TYPE_SOC_TEMPERATURE,
            vendor="Espressif",
            version=1,
            max_range="-40°C to +125°C",
            resolution="0.5°C",
            power_ma=0
        )
    )


# ============================================================================
# Calibration persistence (internal)
# ============================================================================

def _load_calibration():
    """Load calibration from SharedPreferences (with migration support)."""
    if not _imu_driver:
        return

    try:
        from mpos.config import SharedPreferences

        # Try NEW location first
        prefs_new = SharedPreferences("com.micropythonos.settings", filename="sensors.json")
        accel_offsets = prefs_new.get_list("accel_offsets")
        gyro_offsets = prefs_new.get_list("gyro_offsets")

        # If not found, try OLD location and migrate
        if not accel_offsets and not gyro_offsets:
            prefs_old = SharedPreferences("com.micropythonos.sensors")
            accel_offsets = prefs_old.get_list("accel_offsets")
            gyro_offsets = prefs_old.get_list("gyro_offsets")

            if accel_offsets or gyro_offsets:
                # Save to new location
                editor = prefs_new.edit()
                if accel_offsets:
                    editor.put_list("accel_offsets", accel_offsets)
                if gyro_offsets:
                    editor.put_list("gyro_offsets", gyro_offsets)
                editor.commit()

        if accel_offsets or gyro_offsets:
            _imu_driver.set_calibration(accel_offsets, gyro_offsets)
    except:
        pass


def _save_calibration():
    """Save calibration to SharedPreferences."""
    if not _imu_driver:
        return

    try:
        from mpos.config import SharedPreferences
        prefs = SharedPreferences("com.micropythonos.settings", filename="sensors.json")
        editor = prefs.edit()

        cal = _imu_driver.get_calibration()
        editor.put_list("accel_offsets", list(cal['accel_offsets']))
        editor.put_list("gyro_offsets", list(cal['gyro_offsets']))
        editor.commit()
    except:
        pass
