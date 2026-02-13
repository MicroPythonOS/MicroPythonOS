# Unit tests for SensorManager service
import unittest
import sys


# Mock hardware before importing SensorManager
class MockI2C:
    """Mock I2C bus for testing."""
    def __init__(self, bus_id, sda=None, scl=None):
        self.bus_id = bus_id
        self.sda = sda
        self.scl = scl
        self.memory = {}  # addr -> {reg -> value}

    def readfrom_mem(self, addr, reg, nbytes):
        """Read from memory (simulates I2C read)."""
        if addr not in self.memory:
            raise OSError("I2C device not found")
        if reg not in self.memory[addr]:
            return bytes([0] * nbytes)
        return bytes(self.memory[addr][reg])

    def writeto_mem(self, addr, reg, data):
        """Write to memory (simulates I2C write)."""
        if addr not in self.memory:
            self.memory[addr] = {}
        self.memory[addr][reg] = list(data)


class MockQMI8658:
    """Mock QMI8658 IMU sensor."""
    def __init__(self, i2c_bus, address=0x6B, accel_scale=0b10, gyro_scale=0b100):
        self.i2c = i2c_bus
        self.address = address
        self.accel_scale = accel_scale
        self.gyro_scale = gyro_scale

    @property
    def temperature(self):
        """Return mock temperature."""
        return 25.5  # Mock temperature in °C

    @property
    def acceleration(self):
        """Return mock acceleration (in G)."""
        return (0.0, 0.0, 1.0)  # At rest, Z-axis = 1G

    @property
    def gyro(self):
        """Return mock gyroscope (in deg/s)."""
        return (0.0, 0.0, 0.0)  # Stationary


class MockWsenIsds:
    """Mock WSEN_ISDS IMU sensor."""
    def __init__(self, i2c, address=0x6B, acc_range="8g", acc_data_rate="104Hz",
                 gyro_range="500dps", gyro_data_rate="104Hz"):
        self.i2c = i2c
        self.address = address
        self.acc_range = acc_range
        self.gyro_range = gyro_range
        self.acc_sensitivity = 0.244  # mg/digit for 8g
        self.gyro_sensitivity = 17.5  # mdps/digit for 500dps
        self.acc_offset_x = 0
        self.acc_offset_y = 0
        self.acc_offset_z = 0
        self.gyro_offset_x = 0
        self.gyro_offset_y = 0
        self.gyro_offset_z = 0

    def get_chip_id(self):
        """Return WHO_AM_I value."""
        return 0x6A

    def _read_raw_accelerations(self):
        """Return mock acceleration (in mg)."""
        return (0.0, 0.0, 1000.0)  # At rest, Z-axis = 1000 mg

    def read_angular_velocities(self):
        """Return mock gyroscope (in mdps)."""
        return (0.0, 0.0, 0.0)

    def acc_calibrate(self, samples=None):
        """Mock calibration."""
        pass

    def gyro_calibrate(self, samples=None):
        """Mock calibration."""
        pass


# Mock constants from drivers
_QMI8685_PARTID = 0x05
_REG_PARTID = 0x00
_ACCELSCALE_RANGE_8G = 0b10
_GYROSCALE_RANGE_256DPS = 0b100


# Mock SharedPreferences to prevent loading real calibration
class MockSharedPreferences:
    """Mock SharedPreferences for testing."""
    def __init__(self, package, filename=None):
        self.package = package
        self.filename = filename
        self.data = {}
    
    def get_list(self, key):
        """Get list value."""
        return self.data.get(key)
    
    def edit(self):
        """Return editor."""
        return MockEditor(self.data)

class MockEditor:
    """Mock SharedPreferences editor."""
    def __init__(self, data):
        self.data = data
    
    def put_list(self, key, value):
        """Put list value."""
        self.data[key] = value
        return self
    
    def commit(self):
        """Commit changes."""
        pass

mock_config = type('module', (), {
    'SharedPreferences': MockSharedPreferences
})()

# Create mock modules
mock_machine = type('module', (), {
    'I2C': MockI2C,
    'Pin': type('Pin', (), {})
})()

mock_qmi8658 = type('module', (), {
    'QMI8658': MockQMI8658,
    '_QMI8685_PARTID': _QMI8685_PARTID,
    '_REG_PARTID': _REG_PARTID,
    '_ACCELSCALE_RANGE_8G': _ACCELSCALE_RANGE_8G,
    '_GYROSCALE_RANGE_256DPS': _GYROSCALE_RANGE_256DPS
})()

mock_wsen_isds = type('module', (), {
    'Wsen_Isds': MockWsenIsds
})()

# Mock esp32 module
def _mock_mcu_temperature(*args, **kwargs):
    """Mock MCU temperature sensor."""
    return 42.0

mock_esp32 = type('module', (), {
    'mcu_temperature': _mock_mcu_temperature
})()

# Inject mocks into sys.modules
sys.modules['machine'] = mock_machine

# Mock parent packages for driver imports
# These need to exist for the import path to work
sys.modules['drivers'] = type('module', (), {})()
sys.modules['drivers.imu_sensor'] = type('module', (), {})()

sys.modules['drivers.imu_sensor.qmi8658'] = mock_qmi8658
sys.modules['drivers.imu_sensor.wsen_isds'] = mock_wsen_isds
sys.modules['esp32'] = mock_esp32
sys.modules['mpos.config'] = mock_config

# Mock _thread for thread safety testing
try:
    import _thread
except ImportError:
    mock_thread = type('module', (), {
        'allocate_lock': lambda: type('lock', (), {
            'acquire': lambda self: None,
            'release': lambda self: None
        })()
    })()
    sys.modules['_thread'] = mock_thread

# Now import the module to test
from mpos import SensorManager


class TestSensorManagerQMI8658(unittest.TestCase):
    """Test cases for SensorManager with QMI8658 IMU."""

    def setUp(self):
        """Set up test fixtures before each test."""
        # Reset SensorManager singleton instance
        SensorManager._instance = None
        
        # Reset SensorManager class state
        SensorManager._initialized = False
        SensorManager._imu_driver = None
        SensorManager._sensor_list = []
        SensorManager._has_mcu_temperature = False
        SensorManager._i2c_bus = None
        SensorManager._i2c_address = None

        # Create mock I2C bus with QMI8658
        self.i2c_bus = MockI2C(0, sda=48, scl=47)
        # Set QMI8658 chip ID
        self.i2c_bus.memory[0x6B] = {_REG_PARTID: [_QMI8685_PARTID]}

    def test_initialization_qmi8658(self):
        """Test that SensorManager initializes with QMI8658."""
        result = SensorManager.init(self.i2c_bus, address=0x6B)
        self.assertTrue(result)
        self.assertTrue(SensorManager.is_available())

    def test_sensor_list_qmi8658(self):
        """Test getting sensor list for QMI8658."""
        SensorManager.init(self.i2c_bus, address=0x6B)
        sensors = SensorManager.get_sensor_list()

        # QMI8658 provides: Accelerometer, Gyroscope, IMU Temperature, MCU Temperature
        self.assertGreaterEqual(len(sensors), 3)

        # Check sensor types present
        sensor_types = [s.type for s in sensors]
        self.assertIn(SensorManager.TYPE_ACCELEROMETER, sensor_types)
        self.assertIn(SensorManager.TYPE_GYROSCOPE, sensor_types)
        self.assertIn(SensorManager.TYPE_IMU_TEMPERATURE, sensor_types)

    def test_get_default_sensor(self):
        """Test getting default sensor by type."""
        SensorManager.init(self.i2c_bus, address=0x6B)

        accel = SensorManager.get_default_sensor(SensorManager.TYPE_ACCELEROMETER)
        self.assertIsNotNone(accel)
        self.assertEqual(accel.type, SensorManager.TYPE_ACCELEROMETER)

        gyro = SensorManager.get_default_sensor(SensorManager.TYPE_GYROSCOPE)
        self.assertIsNotNone(gyro)
        self.assertEqual(gyro.type, SensorManager.TYPE_GYROSCOPE)

    def test_get_nonexistent_sensor(self):
        """Test getting a sensor type that doesn't exist."""
        SensorManager.init(self.i2c_bus, address=0x6B)

        # Type 999 doesn't exist
        sensor = SensorManager.get_default_sensor(999)
        self.assertIsNone(sensor)

    def test_read_accelerometer(self):
        """Test reading accelerometer data."""
        SensorManager.init(self.i2c_bus, address=0x6B)
        accel = SensorManager.get_default_sensor(SensorManager.TYPE_ACCELEROMETER)

        data = SensorManager.read_sensor(accel)
        self.assertTrue(data is not None, f"read_sensor returned None, expected tuple")
        self.assertEqual(len(data), 3)  # (x, y, z)

        ax, ay, az = data
        # At rest, Z should be ~9.8 m/s² (1G converted to m/s²)
        self.assertAlmostEqual(az, 9.80665, places=2)

    def test_read_gyroscope(self):
        """Test reading gyroscope data."""
        SensorManager.init(self.i2c_bus, address=0x6B)
        gyro = SensorManager.get_default_sensor(SensorManager.TYPE_GYROSCOPE)

        data = SensorManager.read_sensor(gyro)
        self.assertTrue(data is not None, f"read_sensor returned None, expected tuple")
        self.assertEqual(len(data), 3)  # (x, y, z)

        gx, gy, gz = data
        # Stationary, all should be ~0 deg/s
        self.assertAlmostEqual(gx, 0.0, places=1)
        self.assertAlmostEqual(gy, 0.0, places=1)
        self.assertAlmostEqual(gz, 0.0, places=1)

    def test_read_temperature(self):
        """Test reading temperature data."""
        SensorManager.init(self.i2c_bus, address=0x6B)

        # Try IMU temperature
        imu_temp = SensorManager.get_default_sensor(SensorManager.TYPE_IMU_TEMPERATURE)
        if imu_temp:
            temp = SensorManager.read_sensor(imu_temp)
            self.assertIsNotNone(temp)
            self.assertIsInstance(temp, (int, float))

        # Try MCU temperature
        mcu_temp = SensorManager.get_default_sensor(SensorManager.TYPE_SOC_TEMPERATURE)
        if mcu_temp:
            temp = SensorManager.read_sensor(mcu_temp)
            self.assertIsNotNone(temp)
            self.assertEqual(temp, 42.0)  # Mock value

    def test_read_sensor_without_init(self):
        """Test reading sensor without initialization."""
        accel = SensorManager.get_default_sensor(SensorManager.TYPE_ACCELEROMETER)
        self.assertIsNone(accel)

    def test_is_available_before_init(self):
        """Test is_available before initialization."""
        self.assertFalse(SensorManager.is_available())


class TestSensorManagerWsenIsds(unittest.TestCase):
    """Test cases for SensorManager with WSEN_ISDS IMU."""

    def setUp(self):
        """Set up test fixtures before each test."""
        # Reset SensorManager singleton instance
        SensorManager._instance = None
        
        # Reset SensorManager class state
        SensorManager._initialized = False
        SensorManager._imu_driver = None
        SensorManager._sensor_list = []
        SensorManager._has_mcu_temperature = False
        SensorManager._i2c_bus = None
        SensorManager._i2c_address = None

        # Create mock I2C bus with WSEN_ISDS
        self.i2c_bus = MockI2C(0, sda=9, scl=18)
        # Set WSEN_ISDS WHO_AM_I
        self.i2c_bus.memory[0x6B] = {0x0F: [0x6A]}

    def test_initialization_wsen_isds(self):
        """Test that SensorManager initializes with WSEN_ISDS."""
        result = SensorManager.init(self.i2c_bus, address=0x6B)
        self.assertTrue(result)
        self.assertTrue(SensorManager.is_available())

    def test_sensor_list_wsen_isds(self):
        """Test getting sensor list for WSEN_ISDS."""
        SensorManager.init(self.i2c_bus, address=0x6B)
        sensors = SensorManager.get_sensor_list()

        # WSEN_ISDS provides: Accelerometer, Gyroscope, MCU Temperature
        # (no IMU temperature)
        self.assertGreaterEqual(len(sensors), 2)

        # Check sensor types
        sensor_types = [s.type for s in sensors]
        self.assertIn(SensorManager.TYPE_ACCELEROMETER, sensor_types)
        self.assertIn(SensorManager.TYPE_GYROSCOPE, sensor_types)

    def test_read_accelerometer_wsen_isds(self):
        """Test reading accelerometer from WSEN_ISDS."""
        SensorManager.init(self.i2c_bus, address=0x6B)
        accel = SensorManager.get_default_sensor(SensorManager.TYPE_ACCELEROMETER)

        data = SensorManager.read_sensor(accel)
        self.assertTrue(data is not None, f"read_sensor returned None, expected tuple")
        self.assertEqual(len(data), 3)

        ax, ay, az = data
        # WSEN_ISDS mock returns 1000mg = 1G = 9.80665 m/s²
        self.assertAlmostEqual(az, 9.80665, places=2)


class TestSensorManagerNoHardware(unittest.TestCase):
    """Test cases for SensorManager without hardware (desktop mode)."""

    def setUp(self):
        """Set up test fixtures before each test."""
        # Reset SensorManager singleton instance
        SensorManager._instance = None
        
        # Reset SensorManager class state
        SensorManager._initialized = False
        SensorManager._imu_driver = None
        SensorManager._sensor_list = []
        SensorManager._has_mcu_temperature = False
        SensorManager._i2c_bus = None
        SensorManager._i2c_address = None

        # Create mock I2C bus with no devices
        self.i2c_bus = MockI2C(0, sda=48, scl=47)
        # No chip ID registered - simulates no hardware

    def test_no_imu_detected(self):
        """Test behavior when no IMU is present."""
        result = SensorManager.init(self.i2c_bus, address=0x6B)
        # Returns True if MCU temp is available (even without IMU)
        self.assertTrue(result)

    def test_graceful_degradation(self):
        """Test graceful degradation when no sensors available."""
        SensorManager.init(self.i2c_bus, address=0x6B)

        # Should have at least MCU temperature
        sensors = SensorManager.get_sensor_list()
        self.assertGreaterEqual(len(sensors), 0)

        # Reading non-existent sensor should return None
        accel = SensorManager.get_default_sensor(SensorManager.TYPE_ACCELEROMETER)
        if accel is None:
            # Expected when no IMU
            pass
        else:
            # If somehow initialized, reading should handle gracefully
            data = SensorManager.read_sensor(accel)
            # Should either work or return None, not crash
            self.assertTrue(data is None or len(data) == 3)


class TestSensorManagerMultipleInit(unittest.TestCase):
    """Test cases for multiple initialization calls."""

    def setUp(self):
        """Set up test fixtures before each test."""
        # Reset SensorManager singleton instance
        SensorManager._instance = None
        
        # Reset SensorManager class state
        SensorManager._initialized = False
        SensorManager._imu_driver = None
        SensorManager._sensor_list = []
        SensorManager._has_mcu_temperature = False
        SensorManager._i2c_bus = None
        SensorManager._i2c_address = None

        # Create mock I2C bus with QMI8658
        self.i2c_bus = MockI2C(0, sda=48, scl=47)
        self.i2c_bus.memory[0x6B] = {_REG_PARTID: [_QMI8685_PARTID]}

    def test_multiple_init_calls(self):
        """Test that multiple init calls are handled gracefully."""
        result1 = SensorManager.init(self.i2c_bus, address=0x6B)
        self.assertTrue(result1)

        # Second init should return True but not re-initialize
        result2 = SensorManager.init(self.i2c_bus, address=0x6B)
        self.assertTrue(result2)

        # Should still work normally
        self.assertTrue(SensorManager.is_available())
