"""Test for calibration check bug after calibrating.

Reproduces issue where check_calibration_quality() returns None after calibration.
"""
import unittest
import sys

# Mock hardware before importing SensorManager
class MockI2C:
    def __init__(self, bus_id, sda=None, scl=None):
        self.bus_id = bus_id
        self.sda = sda
        self.scl = scl
        self.memory = {}

    def readfrom_mem(self, addr, reg, nbytes):
        if addr not in self.memory:
            raise OSError("I2C device not found")
        if reg not in self.memory[addr]:
            return bytes([0] * nbytes)
        return bytes(self.memory[addr][reg])

    def writeto_mem(self, addr, reg, data):
        if addr not in self.memory:
            self.memory[addr] = {}
        self.memory[addr][reg] = list(data)


class MockQMI8658:
    def __init__(self, i2c_bus, address=0x6B, accel_scale=0b10, gyro_scale=0b100):
        self.i2c = i2c_bus
        self.address = address
        self.accel_scale = accel_scale
        self.gyro_scale = gyro_scale

    @property
    def temperature(self):
        return 25.5

    @property
    def acceleration(self):
        return (0.0, 0.0, 1.0)  # At rest, Z-axis = 1G

    @property
    def gyro(self):
        return (0.0, 0.0, 0.0)  # Stationary


# Mock constants
_QMI8685_PARTID = 0x05
_REG_PARTID = 0x00
_ACCELSCALE_RANGE_8G = 0b10
_GYROSCALE_RANGE_256DPS = 0b100

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

def _mock_mcu_temperature(*args, **kwargs):
    return 42.0

mock_esp32 = type('module', (), {
    'mcu_temperature': _mock_mcu_temperature
})()

# Inject mocks
sys.modules['machine'] = mock_machine
sys.modules['mpos.hardware.drivers.qmi8658'] = mock_qmi8658
sys.modules['esp32'] = mock_esp32

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
import mpos.sensor_manager as SensorManager


class TestCalibrationCheckBug(unittest.TestCase):
    """Test case for calibration check bug."""

    def setUp(self):
        """Set up test fixtures before each test."""
        # Reset SensorManager state
        SensorManager._initialized = False
        SensorManager._imu_driver = None
        SensorManager._sensor_list = []
        SensorManager._has_mcu_temperature = False

        # Create mock I2C bus with QMI8658
        self.i2c_bus = MockI2C(0, sda=48, scl=47)
        self.i2c_bus.memory[0x6B] = {_REG_PARTID: [_QMI8685_PARTID]}

    def test_check_quality_after_calibration(self):
        """Test that check_calibration_quality() works after calibration.

        This reproduces the bug where check_calibration_quality() returns
        None or shows "--" after performing calibration.
        """
        # Initialize
        SensorManager.init(self.i2c_bus, address=0x6B)

        # Step 1: Check calibration quality BEFORE calibration (should work)
        print("\n=== Step 1: Check quality BEFORE calibration ===")
        quality_before = SensorManager.check_calibration_quality(samples=10)
        self.assertIsNotNone(quality_before, "Quality check BEFORE calibration should return data")
        self.assertIn('quality_score', quality_before)
        print(f"Quality before: {quality_before['quality_rating']} ({quality_before['quality_score']:.2f})")

        # Step 2: Calibrate sensors
        print("\n=== Step 2: Calibrate sensors ===")
        accel = SensorManager.get_default_sensor(SensorManager.TYPE_ACCELEROMETER)
        gyro = SensorManager.get_default_sensor(SensorManager.TYPE_GYROSCOPE)

        self.assertIsNotNone(accel, "Accelerometer should be available")
        self.assertIsNotNone(gyro, "Gyroscope should be available")

        accel_offsets = SensorManager.calibrate_sensor(accel, samples=10)
        print(f"Accel offsets: {accel_offsets}")
        self.assertIsNotNone(accel_offsets, "Accelerometer calibration should succeed")

        gyro_offsets = SensorManager.calibrate_sensor(gyro, samples=10)
        print(f"Gyro offsets: {gyro_offsets}")
        self.assertIsNotNone(gyro_offsets, "Gyroscope calibration should succeed")

        # Step 3: Check calibration quality AFTER calibration (BUG: returns None)
        print("\n=== Step 3: Check quality AFTER calibration ===")
        quality_after = SensorManager.check_calibration_quality(samples=10)
        self.assertIsNotNone(quality_after, "Quality check AFTER calibration should return data (BUG: returns None)")
        self.assertIn('quality_score', quality_after)
        print(f"Quality after: {quality_after['quality_rating']} ({quality_after['quality_score']:.2f})")

        # Verify sensor reads still work
        print("\n=== Step 4: Verify sensor reads still work ===")
        accel_data = SensorManager.read_sensor(accel)
        self.assertIsNotNone(accel_data, "Accelerometer should still be readable")
        print(f"Accel data: {accel_data}")

        gyro_data = SensorManager.read_sensor(gyro)
        self.assertIsNotNone(gyro_data, "Gyroscope should still be readable")
        print(f"Gyro data: {gyro_data}")


if __name__ == '__main__':
    unittest.main()
