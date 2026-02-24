# Unit tests for AudioManager service
import unittest
import sys

# Import centralized mocks
from mpos.testing import (
    MockMachine,
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
        self.buzzer_pin = 46
        self.i2s_pins = {'sck': 2, 'ws': 47, 'sd': 16}

        # Reset singleton instance for each test
        AudioManager._instance = None

        AudioManager()
        AudioManager.add(AudioManager.Output("speaker", "i2s", i2s_pins=self.i2s_pins))
        AudioManager.add(AudioManager.Output("buzzer", "buzzer", buzzer_pin=self.buzzer_pin))

        # Reset volume to default after creating instance
        AudioManager.set_volume(70)

    def tearDown(self):
        """Clean up after each test."""
        AudioManager.stop()

    def test_initialization(self):
        """Test that AudioManager initializes correctly."""
        am = AudioManager.get()
        self.assertEqual(len(am._outputs), 2)
        self.assertEqual(am._outputs[0].i2s_pins, self.i2s_pins)
        self.assertEqual(am._outputs[1].buzzer_pin, self.buzzer_pin)

    def test_get_outputs(self):
        """Test that get_outputs() returns configured outputs."""
        outputs = AudioManager.get_outputs()
        self.assertEqual(len(outputs), 2)
        self.assertEqual(outputs[0].kind, "i2s")
        self.assertEqual(outputs[1].kind, "buzzer")

    def test_default_output(self):
        """Test default output selection."""
        default_output = AudioManager.get_default_output()
        self.assertIsNotNone(default_output)
        self.assertEqual(default_output.kind, "i2s")

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
        AudioManager()

        with self.assertRaises(ValueError):
            AudioManager.player(file_path="test.wav").start()

        with self.assertRaises(ValueError):
            AudioManager.player(rtttl="Test:d=4,o=5,b=120:c").start()

    def test_i2s_only_rejects_rtttl(self):
        """Test that I2S-only config rejects buzzer playback."""
        # Re-initialize with I2S only
        AudioManager._instance = None
        AudioManager()
        AudioManager.add(AudioManager.Output("speaker", "i2s", i2s_pins=self.i2s_pins))

        with self.assertRaises(ValueError):
            AudioManager.player(rtttl="Test:d=4,o=5,b=120:c").start()

    def test_buzzer_only_rejects_wav(self):
        """Test that buzzer-only config rejects I2S playback."""
        # Re-initialize with buzzer only
        AudioManager._instance = None
        AudioManager()
        AudioManager.add(AudioManager.Output("buzzer", "buzzer", buzzer_pin=self.buzzer_pin))

        with self.assertRaises(ValueError):
            AudioManager.player(file_path="test.wav").start()

    def test_is_playing_initially_false(self):
        """Test that is_playing() returns False initially."""
        # Reset to ensure clean state
        AudioManager._instance = None
        AudioManager()
        AudioManager.add(AudioManager.Output("speaker", "i2s", i2s_pins=self.i2s_pins))
        self.assertFalse(AudioManager.player(file_path="test.wav").is_playing())

    def test_stop_with_no_playback(self):
        """Test that stop() can be called when nothing is playing."""
        # Should not raise exception
        AudioManager.stop()

    def test_volume_default_value(self):
        """Test that default volume is reasonable."""
        # After init, volume should be at default (50)
        AudioManager._instance = None
        AudioManager()
        self.assertEqual(AudioManager.get_volume(), 50)


class TestAudioManagerRecording(unittest.TestCase):
    """Test cases for AudioManager recording functionality."""

    def setUp(self):
        """Initialize AudioManager with microphone before each test."""
        # I2S pins with microphone input
        self.i2s_pins_with_mic = {'sck': 2, 'ws': 47, 'sd_in': 15}

        # Reset singleton instance for each test
        AudioManager._instance = None

        AudioManager()
        AudioManager.add(AudioManager.Input("mic", "i2s", i2s_pins=self.i2s_pins_with_mic))

        # Reset volume to default after creating instance
        AudioManager.set_volume(70)

    def tearDown(self):
        """Clean up after each test."""
        AudioManager.stop()

    def test_get_inputs(self):
        """Test get_inputs() returns configured inputs."""
        inputs = AudioManager.get_inputs()
        self.assertEqual(len(inputs), 1)
        self.assertEqual(inputs[0].kind, "i2s")

    def test_default_input(self):
        """Test default input selection."""
        default_input = AudioManager.get_default_input()
        self.assertIsNotNone(default_input)
        self.assertEqual(default_input.kind, "i2s")

    def test_is_recording_initially_false(self):
        """Test that is_recording() returns False initially."""
        recorder = AudioManager.recorder(file_path="test.wav")
        self.assertFalse(recorder.is_recording())

    def test_record_wav_no_microphone(self):
        """Test that recorder() fails when no microphone is configured."""
        AudioManager._instance = None
        AudioManager()
        with self.assertRaises(ValueError):
            AudioManager.recorder(file_path="test.wav").start()

    def test_record_wav_no_i2s(self):
        AudioManager._instance = None
        AudioManager()
        AudioManager.add(AudioManager.Input("mic", "adc", adc_mic_pin=4))
        recorder = AudioManager.recorder(file_path="test.wav")
        self.assertFalse(recorder.is_recording())

    def test_stop_with_no_recording(self):
        """Test that stop() can be called when nothing is recording."""
        # Should not raise exception
        AudioManager.stop()
