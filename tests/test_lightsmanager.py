# Unit tests for LightsManager service
import unittest
import sys


# Mock hardware before importing LightsManager
class MockPin:
    IN = 0
    OUT = 1

    def __init__(self, pin_number, mode=None):
        self.pin_number = pin_number
        self.mode = mode


class MockNeoPixel:
    def __init__(self, pin, num_leds):
        self.pin = pin
        self.num_leds = num_leds
        self.pixels = [(0, 0, 0)] * num_leds
        self.write_count = 0

    def __setitem__(self, index, value):
        if 0 <= index < self.num_leds:
            self.pixels[index] = value

    def __getitem__(self, index):
        if 0 <= index < self.num_leds:
            return self.pixels[index]
        return (0, 0, 0)

    def write(self):
        self.write_count += 1


# Inject mocks
sys.modules['machine'] = type('module', (), {'Pin': MockPin})()
sys.modules['neopixel'] = type('module', (), {'NeoPixel': MockNeoPixel})()


# Now import the module to test
import mpos.lights as LightsManager


class TestLightsManager(unittest.TestCase):
    """Test cases for LightsManager service."""

    def setUp(self):
        """Initialize LightsManager before each test."""
        LightsManager.init(neopixel_pin=12, num_leds=5)

    def test_initialization(self):
        """Test that LightsManager initializes correctly."""
        self.assertTrue(LightsManager.is_available())
        self.assertEqual(LightsManager.get_led_count(), 5)

    def test_set_single_led(self):
        """Test setting a single LED color."""
        result = LightsManager.set_led(0, 255, 0, 0)
        self.assertTrue(result)

        # Verify color was set (via internal _neopixel mock)
        neopixel = LightsManager._neopixel
        self.assertEqual(neopixel[0], (255, 0, 0))

    def test_set_led_invalid_index(self):
        """Test that invalid LED indices are rejected."""
        # Negative index
        result = LightsManager.set_led(-1, 255, 0, 0)
        self.assertFalse(result)

        # Index too large
        result = LightsManager.set_led(10, 255, 0, 0)
        self.assertFalse(result)

    def test_set_all_leds(self):
        """Test setting all LEDs to same color."""
        result = LightsManager.set_all(0, 255, 0)
        self.assertTrue(result)

        # Verify all LEDs were set
        neopixel = LightsManager._neopixel
        for i in range(5):
            self.assertEqual(neopixel[i], (0, 255, 0))

    def test_clear(self):
        """Test clearing all LEDs."""
        # First set some colors
        LightsManager.set_all(255, 255, 255)

        # Then clear
        result = LightsManager.clear()
        self.assertTrue(result)

        # Verify all LEDs are black
        neopixel = LightsManager._neopixel
        for i in range(5):
            self.assertEqual(neopixel[i], (0, 0, 0))

    def test_write(self):
        """Test that write() updates hardware."""
        neopixel = LightsManager._neopixel
        initial_count = neopixel.write_count

        result = LightsManager.write()
        self.assertTrue(result)

        # Verify write was called
        self.assertEqual(neopixel.write_count, initial_count + 1)

    def test_notification_colors(self):
        """Test convenience notification color method."""
        # Valid colors
        self.assertTrue(LightsManager.set_notification_color("red"))
        self.assertTrue(LightsManager.set_notification_color("green"))
        self.assertTrue(LightsManager.set_notification_color("blue"))

        # Invalid color
        result = LightsManager.set_notification_color("invalid_color")
        self.assertFalse(result)

    def test_case_insensitive_colors(self):
        """Test that color names are case-insensitive."""
        self.assertTrue(LightsManager.set_notification_color("RED"))
        self.assertTrue(LightsManager.set_notification_color("Green"))
        self.assertTrue(LightsManager.set_notification_color("BLUE"))
