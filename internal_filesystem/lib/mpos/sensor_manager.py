"""Android-inspired SensorManager for MicroPythonOS.

Provides unified access to IMU sensors (QMI8658, WSEN_ISDS) and other sensors.
Follows singleton pattern with class method delegation.

Example usage:
    from mpos import SensorManager

    # In board init file:
    SensorManager.init(i2c_bus, address=0x6B)

    # In app:
    if SensorManager.is_available():
        accel = SensorManager.get_default_sensor(SensorManager.TYPE_ACCELEROMETER)
        ax, ay, az = SensorManager.read_sensor(accel)  # Returns m/s²

MIT License
Copyright (c) 2024 MicroPythonOS contributors
"""

try:
    import _thread

    _lock = _thread.allocate_lock()
except ImportError:
    _lock = None

from mpos.imu.constants import (
    TYPE_ACCELEROMETER,
    TYPE_MAGNETIC_FIELD,
    TYPE_GYROSCOPE,
    TYPE_TEMPERATURE,
    TYPE_IMU_TEMPERATURE,
    TYPE_SOC_TEMPERATURE,
    FACING_EARTH,
    FACING_SKY,
)
from mpos.imu.manager import ImuManager
from mpos.imu.sensor import Sensor


class SensorManager:
    """
    Centralized sensor management service.
    Implements singleton pattern for unified sensor access.
    
    Usage:
        from mpos import SensorManager
        
        # Initialize
        SensorManager.init(i2c_bus, address=0x6B)
        
        # Get sensor
        accel = SensorManager.get_default_sensor(SensorManager.TYPE_ACCELEROMETER)
        
        # Read sensor
        ax, ay, az = SensorManager.read_sensor(accel)
    """
    
    _instance = None

    # Class-level state variables (for testing and singleton pattern)
    _initialized = False
    _imu_manager = None
    
    # Class-level constants
    TYPE_ACCELEROMETER = TYPE_ACCELEROMETER
    TYPE_MAGNETIC_FIELD = TYPE_MAGNETIC_FIELD
    TYPE_GYROSCOPE = TYPE_GYROSCOPE
    TYPE_TEMPERATURE = TYPE_TEMPERATURE
    TYPE_IMU_TEMPERATURE = TYPE_IMU_TEMPERATURE
    TYPE_SOC_TEMPERATURE = TYPE_SOC_TEMPERATURE
    FACING_EARTH = FACING_EARTH
    FACING_SKY = FACING_SKY
    
    def __init__(self):
        """Initialize SensorManager singleton instance."""
        if SensorManager._instance:
            return
        SensorManager._instance = self
    
    @classmethod
    def get(cls):
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def init(self, i2c_bus, address=0x6B, mounted_position=FACING_SKY):
        """Initialize SensorManager. MCU temperature initializes immediately, IMU initializes on first use.

        Args:
            i2c_bus: machine.I2C instance (can be None if only MCU temperature needed)
            address: I2C address (default 0x6B for both QMI8658 and WSEN_ISDS)

        Returns:
            bool: True if initialized successfully
        """
        self._ensure_imu_manager()
        self._initialized = self._imu_manager.init(
            i2c_bus,
            address=address,
            mounted_position=mounted_position,
        )
        return self._initialized

    def init_iio(self):
        self._ensure_imu_manager()
        self._initialized = self._imu_manager.init_iio()
        return self._initialized

    def _ensure_imu_manager(self):
        if self._imu_manager is None:
            self._imu_manager = ImuManager()
    
    def is_available(self):
        """Check if sensors are available.

        Does NOT trigger IMU initialization (to avoid boot-time initialization).
        Use get_default_sensor() or read_sensor() to lazily initialize IMU.

        Returns:
            bool: True if SensorManager is initialized (may only have MCU temp, not IMU)
        """
        return self._initialized

    def get_sensor_list(self):
        """Get list of all available sensors.

        Performs lazy IMU initialization on first call.

        Returns:
            list: List of Sensor objects
        """
        if not self._imu_manager:
            return []
        return self._imu_manager.get_sensor_list()

    def get_default_sensor(self, sensor_type):
        """Get default sensor of given type.

        Performs lazy IMU initialization on first call.

        Args:
            sensor_type: Sensor type constant (TYPE_ACCELEROMETER, etc.)

        Returns:
            Sensor object or None if not available
        """
        if not self._imu_manager:
            return None
        return self._imu_manager.get_default_sensor(sensor_type)

    def read_sensor_once(self, sensor):
        if not self._imu_manager:
            return None
        return self._imu_manager.read_sensor_once(sensor)

    def read_sensor(self, sensor):
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

        if _lock:
            _lock.acquire()

        try:
            return self._imu_manager.read_sensor(sensor) if self._imu_manager else None
        finally:
            if _lock:
                _lock.release()
    
    def calibrate_sensor(self, sensor, samples=100):
        """Calibrate sensor and save to SharedPreferences.

        Performs lazy IMU initialization on first call.
        Device must be stationary for accelerometer/gyroscope calibration.

        Args:
            sensor: Sensor object to calibrate
            samples: Number of samples to average (default 100)

        Returns:
            tuple: Calibration offsets (x, y, z) or None if failed
        """
        if not self._imu_manager:
            return None

        if _lock:
            _lock.acquire()

        try:
            return self._imu_manager.calibrate_sensor(sensor, samples=samples)
        except Exception as e:
            import sys

            sys.print_exception(e)
            print(f"[SensorManager] Calibration error: {e}")
            return None
        finally:
            if _lock:
                _lock.release()

    def check_calibration_quality(self, samples=50):
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
        if not self._imu_manager:
            return None
        return self._imu_manager.check_calibration_quality(samples=samples)

    def check_stationarity(
        self, samples=30, variance_threshold_accel=0.5, variance_threshold_gyro=5.0
    ):
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
        if not self._imu_manager:
            return None
        return self._imu_manager.check_stationarity(
            samples=samples,
            variance_threshold_accel=variance_threshold_accel,
            variance_threshold_gyro=variance_threshold_gyro,
        )


# ============================================================================
# Class method delegation (at module level)
# ============================================================================

_original_methods = {}
_methods_to_delegate = [
    'init', 'init_iio', 'is_available', 'get_sensor_list', 'get_default_sensor',
    'read_sensor', 'read_sensor_once', 'calibrate_sensor', 'check_calibration_quality',
    'check_stationarity'
]

for method_name in _methods_to_delegate:
    _original_methods[method_name] = getattr(SensorManager, method_name)

def _make_class_method(method_name):
    """Create a class method that delegates to the singleton instance."""
    original_method = _original_methods[method_name]
    
    @classmethod
    def class_method(cls, *args, **kwargs):
        instance = cls.get()
        return original_method(instance, *args, **kwargs)
    
    return class_method

for method_name in _methods_to_delegate:
    setattr(SensorManager, method_name, _make_class_method(method_name))
