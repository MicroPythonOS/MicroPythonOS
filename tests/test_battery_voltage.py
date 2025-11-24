"""
Unit tests for mpos.battery_voltage module.

Tests ADC1/ADC2 detection, caching, WiFi coordination, and voltage calculations.
"""

import unittest
import sys

# Add parent directory to path for imports
sys.path.insert(0, '../internal_filesystem')

# Mock modules before importing battery_voltage
class MockADC:
    """Mock ADC for testing."""
    ATTN_11DB = 3

    def __init__(self, pin):
        self.pin = pin
        self._atten = None
        self._read_value = 2048  # Default mid-range value

    def atten(self, value):
        self._atten = value

    def read(self):
        return self._read_value

    def set_read_value(self, value):
        """Test helper to set ADC reading."""
        self._read_value = value


class MockPin:
    """Mock Pin for testing."""
    def __init__(self, pin_num):
        self.pin_num = pin_num


class MockMachine:
    """Mock machine module."""
    ADC = MockADC
    Pin = MockPin


class MockWifiService:
    """Mock WifiService for testing."""
    wifi_busy = False
    _connected = False
    _temporarily_disabled = False

    @classmethod
    def is_connected(cls):
        return cls._connected

    @classmethod
    def disconnect(cls):
        cls._connected = False

    @classmethod
    def temporarily_disable(cls):
        """Temporarily disable WiFi and return whether it was connected."""
        if cls.wifi_busy:
            raise RuntimeError("Cannot disable WiFi: WifiService is already busy")
        was_connected = cls._connected
        cls.wifi_busy = True
        cls._connected = False
        cls._temporarily_disabled = True
        return was_connected

    @classmethod
    def temporarily_enable(cls, was_connected):
        """Re-enable WiFi and reconnect if it was connected before."""
        cls.wifi_busy = False
        cls._temporarily_disabled = False
        if was_connected:
            cls._connected = True  # Simulate reconnection

    @classmethod
    def reset(cls):
        """Test helper to reset state."""
        cls.wifi_busy = False
        cls._connected = False
        cls._temporarily_disabled = False


# Inject mocks
sys.modules['machine'] = MockMachine
sys.modules['mpos.net.wifi_service'] = type('module', (), {'WifiService': MockWifiService})()

# Now import battery_voltage
import mpos.battery_voltage as bv


class TestADC2Detection(unittest.TestCase):
    """Test ADC1 vs ADC2 pin detection."""

    def test_adc1_pins_detected(self):
        """Test that ADC1 pins (GPIO1-10) are detected correctly."""
        for pin in range(1, 11):
            self.assertFalse(bv._is_adc2_pin(pin), f"GPIO{pin} should be ADC1")

    def test_adc2_pins_detected(self):
        """Test that ADC2 pins (GPIO11-20) are detected correctly."""
        for pin in range(11, 21):
            self.assertTrue(bv._is_adc2_pin(pin), f"GPIO{pin} should be ADC2")

    def test_out_of_range_pins(self):
        """Test pins outside ADC range."""
        self.assertFalse(bv._is_adc2_pin(0))
        self.assertFalse(bv._is_adc2_pin(21))
        self.assertFalse(bv._is_adc2_pin(30))
        self.assertFalse(bv._is_adc2_pin(100))


class TestInitADC(unittest.TestCase):
    """Test ADC initialization."""

    def setUp(self):
        """Reset module state."""
        bv.adc = None
        bv.conversion_func = None
        bv.adc_pin = None

    def test_init_adc1_pin(self):
        """Test initializing with ADC1 pin."""
        def adc_to_voltage(adc_value):
            return adc_value * 0.00161

        bv.init_adc(5, adc_to_voltage)

        self.assertIsNotNone(bv.adc)
        self.assertEqual(bv.conversion_func, adc_to_voltage)
        self.assertEqual(bv.adc_pin, 5)
        self.assertEqual(bv.adc._atten, MockADC.ATTN_11DB)

    def test_init_adc2_pin(self):
        """Test initializing with ADC2 pin (should warn but work)."""
        def adc_to_voltage(adc_value):
            return adc_value * 0.00197

        bv.init_adc(13, adc_to_voltage)

        self.assertIsNotNone(bv.adc)
        self.assertIsNotNone(bv.conversion_func)
        self.assertEqual(bv.adc_pin, 13)

    def test_conversion_func_stored(self):
        """Test that conversion function is stored correctly."""
        def my_conversion(adc_value):
            return adc_value * 0.12345

        bv.init_adc(5, my_conversion)
        self.assertEqual(bv.conversion_func, my_conversion)


class TestCaching(unittest.TestCase):
    """Test caching mechanism."""

    def setUp(self):
        """Reset module state."""
        bv.clear_cache()
        def adc_to_voltage(adc_value):
            return adc_value * 0.00161
        bv.init_adc(5, adc_to_voltage)  # Use ADC1 to avoid WiFi complexity
        MockWifiService.reset()

    def tearDown(self):
        """Clean up."""
        bv.clear_cache()

    def test_cache_hit_on_first_read(self):
        """Test that first read already has a cache (because of read during init) """
        self.assertIsNotNone(bv._cached_raw_adc)
        raw = bv.read_raw_adc()
        self.assertIsNotNone(bv._cached_raw_adc)
        self.assertEqual(raw, bv._cached_raw_adc)

    def test_cache_hit_within_duration(self):
        """Test that subsequent reads use cache within duration."""
        raw1 = bv.read_raw_adc()

        # Change ADC value but should still get cached value
        bv.adc.set_read_value(3000)
        raw2 = bv.read_raw_adc()

        self.assertEqual(raw1, raw2, "Should return cached value")

    def test_force_refresh_bypasses_cache(self):
        """Test that force_refresh bypasses cache."""
        bv.adc.set_read_value(2000)
        raw1 = bv.read_raw_adc()

        # Change value and force refresh
        bv.adc.set_read_value(3000)
        raw2 = bv.read_raw_adc(force_refresh=True)

        self.assertNotEqual(raw1, raw2, "force_refresh should bypass cache")
        self.assertEqual(raw2, 3000.0)

    def test_clear_cache_works(self):
        """Test that clear_cache() clears the cache."""
        bv.read_raw_adc()
        self.assertIsNotNone(bv._cached_raw_adc)

        bv.clear_cache()
        self.assertIsNone(bv._cached_raw_adc)
        self.assertEqual(bv._last_read_time, 0)


class TestADC1Reading(unittest.TestCase):
    """Test ADC reading with ADC1 (no WiFi interference)."""

    def setUp(self):
        """Reset module state."""
        bv.clear_cache()
        def adc_to_voltage(adc_value):
            return adc_value * 0.00161
        bv.init_adc(5, adc_to_voltage)  # GPIO5 is ADC1
        MockWifiService.reset()
        MockWifiService._connected = True

    def tearDown(self):
        """Clean up."""
        bv.clear_cache()
        MockWifiService.reset()

    def test_adc1_doesnt_disable_wifi(self):
        """Test that ADC1 reading doesn't disable WiFi."""
        MockWifiService._connected = True

        bv.read_raw_adc(force_refresh=True)

        # WiFi should still be connected
        self.assertTrue(MockWifiService.is_connected())
        self.assertFalse(MockWifiService.wifi_busy)

    def test_adc1_ignores_wifi_busy(self):
        """Test that ADC1 reading works even if WiFi is busy."""
        MockWifiService.wifi_busy = True

        # Should not raise error
        try:
            raw = bv.read_raw_adc(force_refresh=True)
            self.assertIsNotNone(raw)
        except RuntimeError:
            self.fail("ADC1 should not raise error when WiFi is busy")


class TestADC2Reading(unittest.TestCase):
    """Test ADC reading with ADC2 (requires WiFi disable)."""

    def setUp(self):
        """Reset module state."""
        bv.clear_cache()
        def adc_to_voltage(adc_value):
            return adc_value * 0.00197
        bv.init_adc(13, adc_to_voltage)  # GPIO13 is ADC2
        MockWifiService.reset()

    def tearDown(self):
        """Clean up."""
        bv.clear_cache()
        MockWifiService.reset()

    def test_adc2_disables_wifi_when_connected(self):
        """Test that ADC2 reading disables WiFi when connected."""
        MockWifiService._connected = True

        bv.read_raw_adc(force_refresh=True)

        # WiFi should be reconnected after reading (if it was connected before)
        self.assertTrue(MockWifiService.is_connected())

    def test_adc2_sets_wifi_busy_flag(self):
        """Test that ADC2 reading sets wifi_busy flag."""
        MockWifiService._connected = False

        # wifi_busy should be False before
        self.assertFalse(MockWifiService.wifi_busy)

        bv.read_raw_adc(force_refresh=True)

        # wifi_busy should be False after (cleared in finally)
        self.assertFalse(MockWifiService.wifi_busy)

    def test_adc2_raises_error_if_wifi_busy(self):
        """Test that ADC2 reading raises error if WiFi is busy."""
        MockWifiService.wifi_busy = True

        with self.assertRaises(RuntimeError) as ctx:
            bv.read_raw_adc(force_refresh=True)

        self.assertIn("WifiService is already busy", str(ctx.exception))

    def test_adc2_uses_cache_when_wifi_busy(self):
        """Test that ADC2 uses cache even when WiFi is busy."""
        # First read to populate cache
        MockWifiService.wifi_busy = False
        raw1 = bv.read_raw_adc(force_refresh=True)

        # Now set WiFi busy
        MockWifiService.wifi_busy = True

        # Should return cached value without error
        raw2 = bv.read_raw_adc()
        self.assertEqual(raw1, raw2)

    def test_adc2_only_reconnects_if_was_connected(self):
        """Test that ADC2 only reconnects WiFi if it was connected before."""
        # WiFi is NOT connected
        MockWifiService._connected = False

        bv.read_raw_adc(force_refresh=True)

        # WiFi should still be disconnected (no unwanted reconnection)
        self.assertFalse(MockWifiService.is_connected())


class TestVoltageCalculations(unittest.TestCase):
    """Test voltage and percentage calculations."""

    def setUp(self):
        """Reset module state."""
        bv.clear_cache()
        def adc_to_voltage(adc_value):
            return adc_value * 0.00161
        bv.init_adc(5, adc_to_voltage)  # ADC1 pin, scale factor for 2:1 divider
        bv.adc.set_read_value(2048)  # Mid-range

    def tearDown(self):
        """Clean up."""
        bv.clear_cache()

    def test_read_battery_voltage_applies_scale_factor(self):
        """Test that voltage is calculated correctly."""
        bv.adc.set_read_value(2048)  # Mid-range
        bv.clear_cache()

        voltage = bv.read_battery_voltage(force_refresh=True)
        expected = 2048 * 0.00161
        self.assertAlmostEqual(voltage, expected, places=4)

    def test_voltage_clamped_to_max(self):
        """Test that voltage is clamped to MAX_VOLTAGE."""
        bv.adc.set_read_value(4095)  # Maximum ADC
        bv.clear_cache()

        voltage = bv.read_battery_voltage(force_refresh=True)
        self.assertLessEqual(voltage, bv.MAX_VOLTAGE)

    def test_voltage_clamped_to_zero(self):
        """Test that negative voltage is clamped to 0."""
        bv.adc.set_read_value(0)
        bv.clear_cache()

        voltage = bv.read_battery_voltage(force_refresh=True)
        self.assertGreaterEqual(voltage, 0.0)

    def test_get_battery_percentage_calculation(self):
        """Test percentage calculation."""
        # Set voltage to mid-range between MIN and MAX
        mid_voltage = (bv.MIN_VOLTAGE + bv.MAX_VOLTAGE) / 2
        # Inverse of conversion function: if voltage = adc * 0.00161, then adc = voltage / 0.00161
        raw_adc = mid_voltage / 0.00161
        bv.adc.set_read_value(int(raw_adc))
        bv.clear_cache()

        percentage = bv.get_battery_percentage()
        self.assertAlmostEqual(percentage, 50.0, places=0)

    def test_percentage_clamped_to_0_100(self):
        """Test that percentage is clamped to 0-100 range."""
        # Test minimum
        bv.adc.set_read_value(0)
        bv.clear_cache()
        percentage = bv.get_battery_percentage()
        self.assertGreaterEqual(percentage, 0.0)
        self.assertLessEqual(percentage, 100.0)

        # Test maximum
        bv.adc.set_read_value(4095)
        bv.clear_cache()
        percentage = bv.get_battery_percentage()
        self.assertGreaterEqual(percentage, 0.0)
        self.assertLessEqual(percentage, 100.0)


class TestAveragingLogic(unittest.TestCase):
    """Test that ADC readings are averaged."""

    def setUp(self):
        """Reset module state."""
        bv.clear_cache()
        def adc_to_voltage(adc_value):
            return adc_value * 0.00161
        bv.init_adc(5, adc_to_voltage)

    def tearDown(self):
        """Clean up."""
        bv.clear_cache()

    def test_adc_read_averages_10_samples(self):
        """Test that 10 samples are averaged."""
        bv.adc.set_read_value(2000)
        bv.clear_cache()

        raw = bv.read_raw_adc(force_refresh=True)

        # Should be average of 10 reads
        self.assertEqual(raw, 2000.0)


class TestDesktopMode(unittest.TestCase):
    """Test behavior when ADC is not available (desktop mode)."""

    def setUp(self):
        """Disable ADC."""
        bv.adc = None
        def adc_to_voltage(adc_value):
            return adc_value * 0.00161
        bv.conversion_func = adc_to_voltage

    def test_read_raw_adc_returns_random_value(self):
        """Test that desktop mode returns random ADC value."""
        raw = bv.read_raw_adc()
        self.assertIsNotNone(raw)
        self.assertTrue(raw > 0, f"Expected raw > 0, got {raw}")
        self.assertTrue(raw < 4096, f"Expected raw < 4096, got {raw}")

    def test_read_battery_voltage_works_without_adc(self):
        """Test that voltage reading works in desktop mode."""
        voltage = bv.read_battery_voltage()
        self.assertIsNotNone(voltage)
        self.assertTrue(voltage > 0, f"Expected voltage > 0, got {voltage}")

    def test_get_battery_percentage_works_without_adc(self):
        """Test that percentage reading works in desktop mode."""
        percentage = bv.get_battery_percentage()
        self.assertIsNotNone(percentage)
        self.assertGreaterEqual(percentage, 0)
        self.assertLessEqual(percentage, 100)


if __name__ == '__main__':
    unittest.main()
