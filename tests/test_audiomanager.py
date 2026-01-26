# Unit tests for AudioManager service
import unittest
import sys

# Import centralized mocks
from mpos.testing import (
    MockMachine,
    MockPWM,
    MockPin,
    MockThread,
    inject_mocks,
)

# Inject mocks before importing AudioManager
inject_mocks({
    'machine': MockMachine(),
    '_thread': MockThread,
})

# Now import the module to test
from mpos.audio.audiomanager import AudioManager


class TestAudioManager(unittest.TestCase):
    """Test cases for AudioManager service."""

    def setUp(self):
        """Initialize AudioManager before each test."""
        self.buzzer = MockPWM(MockPin(46))
        self.i2s_pins = {'sck': 2, 'ws': 47, 'sd': 16}

        # Reset singleton instance for each test
        AudioManager._instance = None

        AudioManager(
            i2s_pins=self.i2s_pins,
            buzzer_instance=self.buzzer
        )
        
        # Reset volume to default after creating instance
        AudioManager.set_volume(70)

    def tearDown(self):
        """Clean up after each test."""
        AudioManager.stop()

    def test_initialization(self):
        """Test that AudioManager initializes correctly."""
        am = AudioManager.get()
        self.assertEqual(am._i2s_pins, self.i2s_pins)
        self.assertEqual(am._buzzer_instance, self.buzzer)

    def test_has_i2s(self):
        """Test has_i2s() returns correct value."""
        # With I2S configured
        AudioManager._instance = None
        AudioManager(i2s_pins=self.i2s_pins, buzzer_instance=None)
        self.assertTrue(AudioManager.has_i2s())
        
        # Without I2S configured
        AudioManager._instance = None
        AudioManager(i2s_pins=None, buzzer_instance=self.buzzer)
        self.assertFalse(AudioManager.has_i2s())

    def test_has_buzzer(self):
        """Test has_buzzer() returns correct value."""
        # With buzzer configured
        AudioManager._instance = None
        AudioManager(i2s_pins=None, buzzer_instance=self.buzzer)
        self.assertTrue(AudioManager.has_buzzer())
        
        # Without buzzer configured
        AudioManager._instance = None
        AudioManager(i2s_pins=self.i2s_pins, buzzer_instance=None)
        self.assertFalse(AudioManager.has_buzzer())

    def test_stream_types(self):
        """Test stream type constants and priority order."""
        self.assertEqual(AudioManager.STREAM_MUSIC, 0)
        self.assertEqual(AudioManager.STREAM_NOTIFICATION, 1)
        self.assertEqual(AudioManager.STREAM_ALARM, 2)

        # Higher number = higher priority
        self.assertTrue(AudioManager.STREAM_MUSIC < AudioManager.STREAM_NOTIFICATION)
        self.assertTrue(AudioManager.STREAM_NOTIFICATION < AudioManager.STREAM_ALARM)

    def test_volume_control(self):
        """Test volume get/set operations."""
        # Set volume
        AudioManager.set_volume(50)
        self.assertEqual(AudioManager.get_volume(), 50)

        # Test clamping to 0-100 range
        AudioManager.set_volume(150)
        self.assertEqual(AudioManager.get_volume(), 100)

        AudioManager.set_volume(-10)
        self.assertEqual(AudioManager.get_volume(), 0)

    def test_no_hardware_rejects_playback(self):
        """Test that no hardware rejects all playback requests."""
        # Re-initialize with no hardware
        AudioManager._instance = None
        AudioManager(i2s_pins=None, buzzer_instance=None)

        # WAV should be rejected (no I2S)
        result = AudioManager.play_wav("test.wav")
        self.assertFalse(result)

        # RTTTL should be rejected (no buzzer)
        result = AudioManager.play_rtttl("Test:d=4,o=5,b=120:c")
        self.assertFalse(result)

    def test_i2s_only_rejects_rtttl(self):
        """Test that I2S-only config rejects buzzer playback."""
        # Re-initialize with I2S only
        AudioManager._instance = None
        AudioManager(i2s_pins=self.i2s_pins, buzzer_instance=None)

        # RTTTL should be rejected (no buzzer)
        result = AudioManager.play_rtttl("Test:d=4,o=5,b=120:c")
        self.assertFalse(result)

    def test_buzzer_only_rejects_wav(self):
        """Test that buzzer-only config rejects I2S playback."""
        # Re-initialize with buzzer only
        AudioManager._instance = None
        AudioManager(i2s_pins=None, buzzer_instance=self.buzzer)

        # WAV should be rejected (no I2S)
        result = AudioManager.play_wav("test.wav")
        self.assertFalse(result)

    def test_is_playing_initially_false(self):
        """Test that is_playing() returns False initially."""
        # Reset to ensure clean state
        AudioManager._instance = None
        AudioManager(i2s_pins=self.i2s_pins, buzzer_instance=self.buzzer)
        self.assertFalse(AudioManager.is_playing())

    def test_stop_with_no_playback(self):
        """Test that stop() can be called when nothing is playing."""
        # Should not raise exception
        AudioManager.stop()
        self.assertFalse(AudioManager.is_playing())

    def test_audio_focus_check_no_current_stream(self):
        """Test audio focus allows playback when no stream is active."""
        am = AudioManager.get()
        result = am._check_audio_focus(AudioManager.STREAM_MUSIC)
        self.assertTrue(result)

    def test_volume_default_value(self):
        """Test that default volume is reasonable."""
        # After init, volume should be at default (70)
        AudioManager(i2s_pins=None, buzzer_instance=None)
        self.assertEqual(AudioManager.get_volume(), 70)


class TestAudioManagerRecording(unittest.TestCase):
    """Test cases for AudioManager recording functionality."""

    def setUp(self):
        """Initialize AudioManager with microphone before each test."""
        self.buzzer = MockPWM(MockPin(46))
        # I2S pins with microphone input
        self.i2s_pins_with_mic = {'sck': 2, 'ws': 47, 'sd': 16, 'sd_in': 15}
        # I2S pins without microphone input
        self.i2s_pins_no_mic = {'sck': 2, 'ws': 47, 'sd': 16}

        # Reset singleton instance for each test
        AudioManager._instance = None

        AudioManager(
            i2s_pins=self.i2s_pins_with_mic,
            buzzer_instance=self.buzzer
        )
        
        # Reset volume to default after creating instance
        AudioManager.set_volume(70)

    def tearDown(self):
        """Clean up after each test."""
        AudioManager.stop()

    def test_has_microphone_with_sd_in(self):
        """Test has_microphone() returns True when sd_in pin is configured."""
        AudioManager._instance = None
        AudioManager(i2s_pins=self.i2s_pins_with_mic, buzzer_instance=None)
        self.assertTrue(AudioManager.has_microphone())

    def test_has_microphone_without_sd_in(self):
        """Test has_microphone() returns False when sd_in pin is not configured."""
        AudioManager._instance = None
        AudioManager(i2s_pins=self.i2s_pins_no_mic, buzzer_instance=None)
        self.assertFalse(AudioManager.has_microphone())

    def test_has_microphone_no_i2s(self):
        """Test has_microphone() returns False when no I2S is configured."""
        AudioManager._instance = None
        AudioManager(i2s_pins=None, buzzer_instance=self.buzzer)
        self.assertFalse(AudioManager.has_microphone())

    def test_is_recording_initially_false(self):
        """Test that is_recording() returns False initially."""
        self.assertFalse(AudioManager.is_recording())

    def test_record_wav_no_microphone(self):
        """Test that record_wav() fails when no microphone is configured."""
        AudioManager._instance = None
        AudioManager(i2s_pins=self.i2s_pins_no_mic, buzzer_instance=None)
        result = AudioManager.record_wav("test.wav")
        self.assertFalse(result, "record_wav() fails when no microphone is configured")

    def test_record_wav_no_i2s(self):
        AudioManager._instance = None
        AudioManager(i2s_pins=None, buzzer_instance=self.buzzer)
        result = AudioManager.record_wav("test.wav")
        self.assertFalse(result, "record_wav() should fail when no I2S is configured")

    def test_stop_with_no_recording(self):
        """Test that stop() can be called when nothing is recording."""
        # Should not raise exception
        AudioManager.stop()
        self.assertFalse(AudioManager.is_recording())
