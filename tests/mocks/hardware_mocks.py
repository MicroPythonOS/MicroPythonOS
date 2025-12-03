# Hardware Mocks for Testing AudioFlinger and LightsManager
# Provides mock implementations of PWM, I2S, NeoPixel, and Pin classes


class MockPin:
    """Mock machine.Pin for testing."""

    IN = 0
    OUT = 1
    PULL_UP = 2

    def __init__(self, pin_number, mode=None, pull=None):
        self.pin_number = pin_number
        self.mode = mode
        self.pull = pull
        self._value = 0

    def value(self, val=None):
        if val is not None:
            self._value = val
        return self._value


class MockPWM:
    """Mock machine.PWM for testing buzzer."""

    def __init__(self, pin, freq=0, duty=0):
        self.pin = pin
        self.last_freq = freq
        self.last_duty = duty
        self.freq_history = []
        self.duty_history = []

    def freq(self, value=None):
        """Set or get frequency."""
        if value is not None:
            self.last_freq = value
            self.freq_history.append(value)
        return self.last_freq

    def duty_u16(self, value=None):
        """Set or get duty cycle (0-65535)."""
        if value is not None:
            self.last_duty = value
            self.duty_history.append(value)
        return self.last_duty


class MockI2S:
    """Mock machine.I2S for testing audio playback."""

    TX = 0
    MONO = 1
    STEREO = 2

    def __init__(self, id, sck, ws, sd, mode, bits, format, rate, ibuf):
        self.id = id
        self.sck = sck
        self.ws = ws
        self.sd = sd
        self.mode = mode
        self.bits = bits
        self.format = format
        self.rate = rate
        self.ibuf = ibuf
        self.written_bytes = []
        self.total_bytes_written = 0

    def write(self, buf):
        """Simulate writing to I2S hardware."""
        self.written_bytes.append(bytes(buf))
        self.total_bytes_written += len(buf)
        return len(buf)

    def deinit(self):
        """Deinitialize I2S."""
        pass


class MockNeoPixel:
    """Mock neopixel.NeoPixel for testing LEDs."""

    def __init__(self, pin, num_leds):
        self.pin = pin
        self.num_leds = num_leds
        self.pixels = [(0, 0, 0)] * num_leds
        self.write_count = 0

    def __setitem__(self, index, value):
        """Set LED color (R, G, B) tuple."""
        if 0 <= index < self.num_leds:
            self.pixels[index] = value

    def __getitem__(self, index):
        """Get LED color."""
        if 0 <= index < self.num_leds:
            return self.pixels[index]
        return (0, 0, 0)

    def write(self):
        """Update hardware (mock - just increment counter)."""
        self.write_count += 1
