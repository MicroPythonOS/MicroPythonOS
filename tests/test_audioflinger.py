# Unit tests for AudioFlinger service
import unittest
import sys

# Import centralized mocks
from mpos.testing import (
    MockMachine,
    MockPWM,
    MockPin,
    MockTaskManager,
    create_mock_module,
    inject_mocks,
)

# Inject mocks before importing AudioFlinger
inject_mocks({
    'machine': MockMachine(),
    'mpos.task_manager': create_mock_module('mpos.task_manager', TaskManager=MockTaskManager),
})

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
            i2s_pins=self.i2s_pins,
            buzzer_instance=self.buzzer
        )

    def tearDown(self):
        """Clean up after each test."""
        AudioFlinger.stop()

    def test_initialization(self):
        """Test that AudioFlinger initializes correctly."""
        self.assertEqual(AudioFlinger._i2s_pins, self.i2s_pins)
        self.assertEqual(AudioFlinger._buzzer_instance, self.buzzer)

    def test_has_i2s(self):
        """Test has_i2s() returns correct value."""
        # With I2S configured
        AudioFlinger.init(i2s_pins=self.i2s_pins, buzzer_instance=None)
        self.assertTrue(AudioFlinger.has_i2s())
        
        # Without I2S configured
        AudioFlinger.init(i2s_pins=None, buzzer_instance=self.buzzer)
        self.assertFalse(AudioFlinger.has_i2s())

    def test_has_buzzer(self):
        """Test has_buzzer() returns correct value."""
        # With buzzer configured
        AudioFlinger.init(i2s_pins=None, buzzer_instance=self.buzzer)
        self.assertTrue(AudioFlinger.has_buzzer())
        
        # Without buzzer configured
        AudioFlinger.init(i2s_pins=self.i2s_pins, buzzer_instance=None)
        self.assertFalse(AudioFlinger.has_buzzer())

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

    def test_no_hardware_rejects_playback(self):
        """Test that no hardware rejects all playback requests."""
        # Re-initialize with no hardware
        AudioFlinger.init(i2s_pins=None, buzzer_instance=None)

        # WAV should be rejected (no I2S)
        result = AudioFlinger.play_wav("test.wav")
        self.assertFalse(result)

        # RTTTL should be rejected (no buzzer)
        result = AudioFlinger.play_rtttl("Test:d=4,o=5,b=120:c")
        self.assertFalse(result)

    def test_i2s_only_rejects_rtttl(self):
        """Test that I2S-only config rejects buzzer playback."""
        # Re-initialize with I2S only
        AudioFlinger.init(i2s_pins=self.i2s_pins, buzzer_instance=None)

        # RTTTL should be rejected (no buzzer)
        result = AudioFlinger.play_rtttl("Test:d=4,o=5,b=120:c")
        self.assertFalse(result)

    def test_buzzer_only_rejects_wav(self):
        """Test that buzzer-only config rejects I2S playback."""
        # Re-initialize with buzzer only
        AudioFlinger.init(i2s_pins=None, buzzer_instance=self.buzzer)

        # WAV should be rejected (no I2S)
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

    def test_audio_focus_check_no_current_stream(self):
        """Test audio focus allows playback when no stream is active."""
        result = AudioFlinger._check_audio_focus(AudioFlinger.STREAM_MUSIC)
        self.assertTrue(result)

    def test_volume_default_value(self):
        """Test that default volume is reasonable."""
        # After init, volume should be at default (70)
        AudioFlinger.init(i2s_pins=None, buzzer_instance=None)
        self.assertEqual(AudioFlinger.get_volume(), 70)
