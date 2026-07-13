# LightsManager - Simple LED Control Service for MicroPythonOS
# Provides one-shot LED control for NeoPixel RGB LEDs
# Apps implement custom animations using the update_frame() pattern

import logging
logger = logging.getLogger(__name__)


class LightsManager:
    def __init__(self):
        self._neopixel = None
        self._neopixel_pin = None
        self._num_leds = 0

    def _init_neopixel(self, clear_on_init):
        if self._neopixel_pin is None or self._num_leds <= 0:
            self._neopixel = None
            return False

        try:
            from machine import Pin
            from neopixel import NeoPixel

            self._neopixel = NeoPixel(Pin(self._neopixel_pin, Pin.OUT), self._num_leds)

            if clear_on_init:
                for i in range(self._num_leds):
                    self._neopixel[i] = (0, 0, 0)
                self._neopixel.write()

            return True
        except Exception as e:
            logger.error("Failed to initialize LEDs: %s", e)
            if __debug__: logger.debug("  - LED functions will return False (no-op)")
            self._neopixel = None
            return False

    def init(self, neopixel_pin):
        """
        Initialize NeoPixel LED hardware.

        Args:
            neopixel_pin: GPIO pin number for NeoPixel data line
        """
        self._neopixel_pin = neopixel_pin

        if self._num_leds <= 0:
            self._neopixel = None
            if __debug__: logger.debug("Initialized: LED count not set yet (call set_led_num())")
            return

        if self._init_neopixel(clear_on_init=True):
            if __debug__: logger.debug("Initialized: %s LEDs on GPIO %s", self._num_leds, neopixel_pin)

    def is_available(self):
        """
        Check if LED hardware is available.

        Returns:
            bool: True if LEDs are initialized and available
        """
        return self._neopixel is not None

    def get_led_count(self):
        """
        Get the number of LEDs.

        Returns:
            int: Number of LEDs, or 0 if not initialized
        """
        return self._num_leds

    def set_led_num(self, num_leds):
        """
        Set the number of LEDs and (re)initialize the NeoPixel buffer.

        Args:
            num_leds: Number of LEDs in the strip

        Returns:
            bool: True if successful, False if invalid count or pin not set
        """
        if num_leds <= 0:
            logger.error("Invalid LED count %s", num_leds)
            return False

        self._num_leds = num_leds

        if self._neopixel_pin is None:
            self._neopixel = None
            logger.warning("LED pin not initialized (call init() first)")
            return False

        if self._init_neopixel(clear_on_init=False):
            if __debug__: logger.debug("LED count set to %s", self._num_leds)
            return True

        return False

    def set_led(self, index, r, g, b):
        """
        Set a single LED color (buffered until write() is called).

        Args:
            index: LED index (0 to num_leds-1)
            r: Red value (0-255)
            g: Green value (0-255)
            b: Blue value (0-255)

        Returns:
            bool: True if successful, False if LEDs unavailable or invalid index
        """
        if not self._neopixel:
            return False

        if index < 0 or index >= self._num_leds:
            logger.error("Invalid LED index %s (valid range: 0-%s)", index, self._num_leds - 1)
            return False

        self._neopixel[index] = (r, g, b)
        return True

    def set_all(self, r, g, b):
        """
        Set all LEDs to the same color (buffered until write() is called).

        Args:
            r: Red value (0-255)
            g: Green value (0-255)
            b: Blue value (0-255)

        Returns:
            bool: True if successful, False if LEDs unavailable
        """
        if not self._neopixel:
            return False

        for i in range(self._num_leds):
            self._neopixel[i] = (r, g, b)
        return True

    def clear(self):
        """
        Clear all LEDs (set to black, buffered until write() is called).

        Returns:
            bool: True if successful, False if LEDs unavailable
        """
        return self.set_all(0, 0, 0)

    def write(self):
        """
        Update hardware with buffered LED colors.
        Must be called after set_led(), set_all(), or clear() to make changes visible.

        Returns:
            bool: True if successful, False if LEDs unavailable
        """
        if not self._neopixel:
            return False

        self._neopixel.write()
        return True

    def set_notification_color(self, color_name):
        """
        Convenience method to set all LEDs to a common color and update immediately.

        Args:
            color_name: Color name (red, green, blue, yellow, orange, purple, white)

        Returns:
            bool: True if successful, False if LEDs unavailable or unknown color
        """
        colors = {
            "red": (255, 0, 0),
            "green": (0, 255, 0),
            "blue": (0, 0, 255),
            "yellow": (255, 255, 0),
            "orange": (255, 128, 0),
            "purple": (128, 0, 255),
            "white": (255, 255, 255),
        }

        color = colors.get(color_name.lower())
        if not color:
            logger.error("Unknown color '%s'", color_name)
            if __debug__: logger.debug("Available colors: %s", ', '.join(colors.keys()))
            return False

        return self.set_all(*color) and self.write()


LightsManager = LightsManager()
