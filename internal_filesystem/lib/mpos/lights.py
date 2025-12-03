# LightsManager - Simple LED Control Service for MicroPythonOS
# Provides one-shot LED control for NeoPixel RGB LEDs
# Apps implement custom animations using the update_frame() pattern

# Module-level state (singleton pattern)
_neopixel = None
_num_leds = 0


def init(neopixel_pin, num_leds=5):
    """
    Initialize NeoPixel LEDs.

    Args:
        neopixel_pin: GPIO pin number for NeoPixel data line
        num_leds: Number of LEDs in the strip (default 5 for Fri3d badge)
    """
    global _neopixel, _num_leds

    try:
        from machine import Pin
        from neopixel import NeoPixel

        _neopixel = NeoPixel(Pin(neopixel_pin, Pin.OUT), num_leds)
        _num_leds = num_leds

        # Clear all LEDs on initialization
        for i in range(num_leds):
            _neopixel[i] = (0, 0, 0)
        _neopixel.write()

        print(f"LightsManager initialized: {num_leds} LEDs on GPIO {neopixel_pin}")
    except Exception as e:
        print(f"LightsManager: Failed to initialize LEDs: {e}")
        print("  - LED functions will return False (no-op)")


def is_available():
    """
    Check if LED hardware is available.

    Returns:
        bool: True if LEDs are initialized and available
    """
    return _neopixel is not None


def get_led_count():
    """
    Get the number of LEDs.

    Returns:
        int: Number of LEDs, or 0 if not initialized
    """
    return _num_leds


def set_led(index, r, g, b):
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
    if not _neopixel:
        return False

    if index < 0 or index >= _num_leds:
        print(f"LightsManager: Invalid LED index {index} (valid range: 0-{_num_leds-1})")
        return False

    _neopixel[index] = (r, g, b)
    return True


def set_all(r, g, b):
    """
    Set all LEDs to the same color (buffered until write() is called).

    Args:
        r: Red value (0-255)
        g: Green value (0-255)
        b: Blue value (0-255)

    Returns:
        bool: True if successful, False if LEDs unavailable
    """
    if not _neopixel:
        return False

    for i in range(_num_leds):
        _neopixel[i] = (r, g, b)
    return True


def clear():
    """
    Clear all LEDs (set to black, buffered until write() is called).

    Returns:
        bool: True if successful, False if LEDs unavailable
    """
    return set_all(0, 0, 0)


def write():
    """
    Update hardware with buffered LED colors.
    Must be called after set_led(), set_all(), or clear() to make changes visible.

    Returns:
        bool: True if successful, False if LEDs unavailable
    """
    if not _neopixel:
        return False

    _neopixel.write()
    return True


def set_notification_color(color_name):
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
        print(f"LightsManager: Unknown color '{color_name}'")
        print(f"  - Available colors: {', '.join(colors.keys())}")
        return False

    return set_all(*color) and write()
