# Unit tests for AudioFlinger service
import unittest
import sys


# Mock hardware before importing
class MockPWM:
    def __init__(self, pin, freq=0, duty=0):
        self.pin = pin
        self.last_freq = freq
        self.last_duty = duty

    def freq(self, value=None):
        if value is not None:
            self.last_freq = value
        return self.last_freq

    def duty_u16(self, value=None):
        if value is not None:
            self.last_duty = value
        return self.last_duty


class MockPin:
    IN = 0
    OUT = 1

    def __init__(self, pin_number, mode=None):
        self.pin_number = pin_number
        self.mode = mode


# Inject mocks
class MockMachine:
    PWM = MockPWM
    Pin = MockPin
sys.modules['machine'] = MockMachine()

class MockLock:
    def acquire(self):
        pass
    def release(self):
        pass

class MockThread:
    @staticmethod
    def allocate_lock():
        return MockLock()
    @staticmethod
    def start_new_thread(func, args, **kwargs):
        pass  # No-op for testing
    @staticmethod
    def stack_size(size=None):
        return 16384 if size is None else None

sys.modules['_thread'] = MockThread()

class MockMposApps:
    @staticmethod
    def good_stack_size():
        return 16384

sys.modules['mpos.apps'] = MockMposApps()


# Now import the module to test
import mpos.audio.audioflinger as AudioFlinger


class TestAudioFlinger(unittest.TestCase):
    """Test cases for AudioFlinger service."""

    def setUp(self):
        """Initialize AudioFlinger before each test."""
        self.buzzer = MockPWM(MockPin(46))
        self.i2s_pins = {'sck': 2, 'ws': 47, 'sd': 16}

        # Reset volume to default before each test
        AudioFlinger.set_volume(70)

        AudioFlinger.init(
            device_type=AudioFlinger.DEVICE_BOTH,
            i2s_pins=self.i2s_pins,
            buzzer_instance=self.buzzer
        )

    def tearDown(self):
        """Clean up after each test."""
        AudioFlinger.stop()

    def test_initialization(self):
        """Test that AudioFlinger initializes correctly."""
        self.assertEqual(AudioFlinger.get_device_type(), AudioFlinger.DEVICE_BOTH)
        self.assertEqual(AudioFlinger._i2s_pins, self.i2s_pins)
        self.assertEqual(AudioFlinger._buzzer_instance, self.buzzer)

    def test_device_types(self):
        """Test device type constants."""
        self.assertEqual(AudioFlinger.DEVICE_NULL, 0)
        self.assertEqual(AudioFlinger.DEVICE_I2S, 1)
        self.assertEqual(AudioFlinger.DEVICE_BUZZER, 2)
        self.assertEqual(AudioFlinger.DEVICE_BOTH, 3)

    def test_stream_types(self):
        """Test stream type constants and priority order."""
        self.assertEqual(AudioFlinger.STREAM_MUSIC, 0)
        self.assertEqual(AudioFlinger.STREAM_NOTIFICATION, 1)
        self.assertEqual(AudioFlinger.STREAM_ALARM, 2)

        # Higher number = higher priority
        self.assertTrue(AudioFlinger.STREAM_MUSIC < AudioFlinger.STREAM_NOTIFICATION)
        self.assertTrue(AudioFlinger.STREAM_NOTIFICATION < AudioFlinger.STREAM_ALARM)

    def test_volume_control(self):
        """Test volume get/set operations."""
        # Set volume
        AudioFlinger.set_volume(50)
        self.assertEqual(AudioFlinger.get_volume(), 50)

        # Test clamping to 0-100 range
        AudioFlinger.set_volume(150)
        self.assertEqual(AudioFlinger.get_volume(), 100)

        AudioFlinger.set_volume(-10)
        self.assertEqual(AudioFlinger.get_volume(), 0)

    def test_device_null_rejects_playback(self):
        """Test that DEVICE_NULL rejects all playback requests."""
        # Re-initialize with no device
        AudioFlinger.init(
            device_type=AudioFlinger.DEVICE_NULL,
            i2s_pins=None,
            buzzer_instance=None
        )

        # WAV should be rejected
        result = AudioFlinger.play_wav("test.wav")
        self.assertFalse(result)

        # RTTTL should be rejected
        result = AudioFlinger.play_rtttl("Test:d=4,o=5,b=120:c")
        self.assertFalse(result)

    def test_device_i2s_only_rejects_rtttl(self):
        """Test that DEVICE_I2S rejects buzzer playback."""
        # Re-initialize with I2S only
        AudioFlinger.init(
            device_type=AudioFlinger.DEVICE_I2S,
            i2s_pins=self.i2s_pins,
            buzzer_instance=None
        )

        # RTTTL should be rejected (no buzzer)
        result = AudioFlinger.play_rtttl("Test:d=4,o=5,b=120:c")
        self.assertFalse(result)

    def test_device_buzzer_only_rejects_wav(self):
        """Test that DEVICE_BUZZER rejects I2S playback."""
        # Re-initialize with buzzer only
        AudioFlinger.init(
            device_type=AudioFlinger.DEVICE_BUZZER,
            i2s_pins=None,
            buzzer_instance=self.buzzer
        )

        # WAV should be rejected (no I2S)
        result = AudioFlinger.play_wav("test.wav")
        self.assertFalse(result)

    def test_missing_i2s_pins_rejects_wav(self):
        """Test that missing I2S pins rejects WAV playback."""
        # Re-initialize with I2S device but no pins
        AudioFlinger.init(
            device_type=AudioFlinger.DEVICE_I2S,
            i2s_pins=None,
            buzzer_instance=None
        )

        result = AudioFlinger.play_wav("test.wav")
        self.assertFalse(result)

    def test_is_playing_initially_false(self):
        """Test that is_playing() returns False initially."""
        self.assertFalse(AudioFlinger.is_playing())

    def test_stop_with_no_playback(self):
        """Test that stop() can be called when nothing is playing."""
        # Should not raise exception
        AudioFlinger.stop()
        self.assertFalse(AudioFlinger.is_playing())

    def test_get_device_type(self):
        """Test that get_device_type() returns correct value."""
        # Test DEVICE_BOTH
        AudioFlinger.init(
            device_type=AudioFlinger.DEVICE_BOTH,
            i2s_pins=self.i2s_pins,
            buzzer_instance=self.buzzer
        )
        self.assertEqual(AudioFlinger.get_device_type(), AudioFlinger.DEVICE_BOTH)

        # Test DEVICE_I2S
        AudioFlinger.init(
            device_type=AudioFlinger.DEVICE_I2S,
            i2s_pins=self.i2s_pins,
            buzzer_instance=None
        )
        self.assertEqual(AudioFlinger.get_device_type(), AudioFlinger.DEVICE_I2S)

        # Test DEVICE_BUZZER
        AudioFlinger.init(
            device_type=AudioFlinger.DEVICE_BUZZER,
            i2s_pins=None,
            buzzer_instance=self.buzzer
        )
        self.assertEqual(AudioFlinger.get_device_type(), AudioFlinger.DEVICE_BUZZER)

        # Test DEVICE_NULL
        AudioFlinger.init(
            device_type=AudioFlinger.DEVICE_NULL,
            i2s_pins=None,
            buzzer_instance=None
        )
        self.assertEqual(AudioFlinger.get_device_type(), AudioFlinger.DEVICE_NULL)

    def test_audio_focus_check_no_current_stream(self):
        """Test audio focus allows playback when no stream is active."""
        result = AudioFlinger._check_audio_focus(AudioFlinger.STREAM_MUSIC)
        self.assertTrue(result)

    def test_init_creates_lock(self):
        """Test that initialization creates a stream lock."""
        self.assertIsNotNone(AudioFlinger._stream_lock)

    def test_volume_default_value(self):
        """Test that default volume is reasonable."""
        # After init, volume should be at default (70)
        AudioFlinger.init(
            device_type=AudioFlinger.DEVICE_NULL,
            i2s_pins=None,
            buzzer_instance=None
        )
        self.assertEqual(AudioFlinger.get_volume(), 70)
