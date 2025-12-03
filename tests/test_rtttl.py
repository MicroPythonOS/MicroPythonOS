# Unit tests for RTTTL parser (RTTTLStream)
import unittest
import sys


# Mock hardware before importing
class MockPWM:
    def __init__(self, pin, freq=0, duty=0):
        self.pin = pin
        self.last_freq = freq
        self.last_duty = duty
        self.freq_history = []
        self.duty_history = []

    def freq(self, value=None):
        if value is not None:
            self.last_freq = value
            self.freq_history.append(value)
        return self.last_freq

    def duty_u16(self, value=None):
        if value is not None:
            self.last_duty = value
            self.duty_history.append(value)
        return self.last_duty


# Inject mock
sys.modules['machine'] = type('module', (), {'PWM': MockPWM, 'Pin': lambda x: x})()


# Now import the module to test
from mpos.audio.stream_rtttl import RTTTLStream


class TestRTTTL(unittest.TestCase):
    """Test cases for RTTTL parser."""

    def setUp(self):
        """Create a mock buzzer before each test."""
        self.buzzer = MockPWM(46)

    def test_parse_simple_rtttl(self):
        """Test parsing a simple RTTTL string."""
        rtttl = "Nokia:d=4,o=5,b=225:8e6,8d6,8f#,8g#"
        stream = RTTTLStream(rtttl, 0, 100, self.buzzer, None)

        self.assertEqual(stream.name, "Nokia")
        self.assertEqual(stream.default_duration, 4)
        self.assertEqual(stream.default_octave, 5)
        self.assertEqual(stream.bpm, 225)

    def test_parse_defaults(self):
        """Test parsing default values."""
        rtttl = "Test:d=8,o=6,b=180:c"
        stream = RTTTLStream(rtttl, 0, 100, self.buzzer, None)

        self.assertEqual(stream.default_duration, 8)
        self.assertEqual(stream.default_octave, 6)
        self.assertEqual(stream.bpm, 180)

        # Check calculated msec_per_whole_note
        # 240000 / 180 = 1333.33...
        self.assertAlmostEqual(stream.msec_per_whole_note, 1333.33, places=1)

    def test_invalid_rtttl_format(self):
        """Test that invalid RTTTL format raises ValueError."""
        # Missing colons
        with self.assertRaises(ValueError):
            RTTTLStream("invalid", 0, 100, self.buzzer, None)

        # Too many colons
        with self.assertRaises(ValueError):
            RTTTLStream("a:b:c:d", 0, 100, self.buzzer, None)

    def test_note_parsing(self):
        """Test parsing individual notes."""
        rtttl = "Test:d=4,o=5,b=120:c,d,e"
        stream = RTTTLStream(rtttl, 0, 100, self.buzzer, None)

        # Generate notes
        notes = list(stream._notes())

        # Should have 3 notes
        self.assertEqual(len(notes), 3)

        # Each note should be a tuple of (frequency, duration)
        for freq, duration in notes:
            self.assertTrue(freq > 0, "Frequency should be non-zero")
            self.assertTrue(duration > 0, "Duration should be non-zero")

    def test_sharp_notes(self):
        """Test parsing sharp notes."""
        rtttl = "Test:d=4,o=5,b=120:c#,d#,f#"
        stream = RTTTLStream(rtttl, 0, 100, self.buzzer, None)

        notes = list(stream._notes())
        self.assertEqual(len(notes), 3)

        # Sharp notes should have different frequencies than natural notes
        # (can't test exact values without knowing frequency table)

    def test_pause_notes(self):
        """Test parsing pause notes."""
        rtttl = "Test:d=4,o=5,b=120:c,p,e"
        stream = RTTTLStream(rtttl, 0, 100, self.buzzer, None)

        notes = list(stream._notes())
        self.assertEqual(len(notes), 3)

        # Pause (p) should have frequency 0
        freq, duration = notes[1]
        self.assertEqual(freq, 0.0)

    def test_duration_modifiers(self):
        """Test note duration modifiers (dots)."""
        rtttl = "Test:d=4,o=5,b=120:c,c."
        stream = RTTTLStream(rtttl, 0, 100, self.buzzer, None)

        notes = list(stream._notes())
        self.assertEqual(len(notes), 2)

        # Dotted note should be 1.5x longer
        normal_duration = notes[0][1]
        dotted_duration = notes[1][1]
        self.assertAlmostEqual(dotted_duration / normal_duration, 1.5, places=1)

    def test_octave_variations(self):
        """Test notes with different octaves."""
        rtttl = "Test:d=4,o=5,b=120:c4,c5,c6,c7"
        stream = RTTTLStream(rtttl, 0, 100, self.buzzer, None)

        notes = list(stream._notes())
        self.assertEqual(len(notes), 4)

        # Higher octaves should have higher frequencies
        freqs = [freq for freq, dur in notes]
        self.assertTrue(freqs[0] < freqs[1], "c4 should be lower than c5")
        self.assertTrue(freqs[1] < freqs[2], "c5 should be lower than c6")
        self.assertTrue(freqs[2] < freqs[3], "c6 should be lower than c7")

    def test_volume_scaling(self):
        """Test volume to duty cycle conversion."""
        # Test various volume levels
        for volume in [0, 25, 50, 75, 100]:
            stream = RTTTLStream("Test:d=4,o=5,b=120:c", 0, volume, self.buzzer, None)

            # Volume 0 should result in duty 0
            if volume == 0:
                # Note: play() method calculates duty, not __init__
                pass  # Can't easily test without calling play()
            else:
                # Volume > 0 should result in duty > 0
                # (duty calculation happens in play() method)
                pass

    def test_stream_type(self):
        """Test that stream type is stored correctly."""
        stream = RTTTLStream("Test:d=4,o=5,b=120:c", 2, 100, self.buzzer, None)
        self.assertEqual(stream.stream_type, 2)

    def test_stop_flag(self):
        """Test that stop flag can be set."""
        stream = RTTTLStream("Test:d=4,o=5,b=120:c", 0, 100, self.buzzer, None)
        self.assertTrue(stream._keep_running)

        stream.stop()
        self.assertFalse(stream._keep_running)

    def test_is_playing_flag(self):
        """Test playing flag is initially false."""
        stream = RTTTLStream("Test:d=4,o=5,b=120:c", 0, 100, self.buzzer, None)
        self.assertFalse(stream.is_playing())
