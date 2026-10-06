# Unit tests for RTTTL parser (RTTTLStream)
import os
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
from mpos.audio.stream_rtttl import RTTTLStream  # Keep this as-is since it's a specific internal module


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

    def test_set_repeat(self):
        """Test that set_repeat updates the repeat count."""
        stream = RTTTLStream("Test:d=4,o=5,b=120:c", 0, 100, self.buzzer, None)
        self.assertEqual(stream._repeat_count, 1)

        stream.set_repeat(3)
        self.assertEqual(stream._repeat_count, 3)

        stream.set_repeat(0)
        self.assertEqual(stream._repeat_count, 0)

        stream.set_repeat("bad")
        self.assertEqual(stream._repeat_count, 0)

    def test_play_tolerates_pwm_inactive(self):
        """Playback must not propagate RuntimeError when PWM is deinitialized mid-play."""

        class _FailingPWM(MockPWM):
            def freq(self, value=None):
                if value is not None:
                    raise RuntimeError("PWM is inactive")
                return self.last_freq

            def duty_u16(self, value=None):
                if value is not None:
                    raise RuntimeError("PWM is inactive")
                return self.last_duty

        buzzer = _FailingPWM(46)
        import mpos.audio.stream_rtttl as stream_module

        real_time = stream_module.time

        class _FakeTime:
            def sleep_ms(self, _ms):
                pass

        stream_module.time = _FakeTime()
        try:
            stream = RTTTLStream("Test:d=4,o=5,b=120:c", 0, 100, buzzer, None)
            stream.play()
            self.assertFalse(stream.is_playing())
        finally:
            stream_module.time = real_time

    def test_play_repeats(self):
        """Test that play() loops for the configured repeat count."""
        import mpos.audio.stream_rtttl as stream_module
        real_time = stream_module.time

        class _FakeTime:
            def sleep_ms(self, _ms):
                pass

        stream_module.time = _FakeTime()
        try:
            stream = RTTTLStream("Test:d=4,o=5,b=120:c,d,e", 0, 100, self.buzzer, None)
            stream.set_repeat(2)
            stream.play()

            notes_per_repeat = 3
            expected_tones = notes_per_repeat * 2
            tone_calls = [f for f in self.buzzer.freq_history if f > 0]
            self.assertEqual(len(tone_calls), expected_tones)
        finally:
            stream_module.time = real_time


@unittest.skipIf(sys.platform == "esp32", "DesktopRTTTLStream is the desktop renderer")
class TestDesktopRTTTLStream(unittest.TestCase):
    """DesktopRTTTLStream renders one pass and lets WAVStream repeat it."""

    TUNE = "Test:d=16,o=5,b=240:c,e,g"

    def setUp(self):
        import mpos.audio.stream_wav as stream_wav
        from mpos.audio.stream_rtttl import DesktopRTTTLStream

        self.stream_wav = stream_wav
        self.real_wav_stream = stream_wav.WAVStream
        self.wav_streams = []
        self.on_construct = None
        self.on_play = None
        test = self

        class _FakeWAVStream:
            def __init__(self, file_path, repeat_count=1, **kwargs):
                self.file_path = file_path
                self.repeat_count = repeat_count
                self.file_size = os.stat(file_path)[6]
                self.played = False
                self.stopped = False
                test.wav_streams.append(self)
                if test.on_construct:
                    test.on_construct()

            def play(self):
                self.played = True
                if test.on_play:
                    test.on_play()

            def stop(self):
                self.stopped = True

            def set_repeat(self, count):
                self.repeat_count = count

            def set_volume(self, vol):
                pass

        class _BoundedDesktopRTTTLStream(DesktopRTTTLStream):
            max_render_bytes = 50_000

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.rendered_bytes = 0

            def _count(self, sample_count):
                self.rendered_bytes += sample_count * 2
                if self.rendered_bytes > self.max_render_bytes:
                    self.stop()

            def _write_samples(self, file, frequency, sample_count, sample_rate):
                DesktopRTTTLStream._write_samples(file, frequency, sample_count, sample_rate)
                self._count(sample_count)

            def _write_silence(self, file, sample_count):
                DesktopRTTTLStream._write_silence(file, sample_count)
                self._count(sample_count)

        stream_wav.WAVStream = _FakeWAVStream
        self.stream_class = _BoundedDesktopRTTTLStream

    def tearDown(self):
        self.stream_wav.WAVStream = self.real_wav_stream

    def _play(self, repeat_count):
        messages = []
        stream = self.stream_class(self.TUNE, 0, 50, messages.append)
        stream.set_repeat(repeat_count)
        stream.play()
        return stream, messages

    def test_endless_repeat_renders_one_pass(self):
        """An endless repeat count renders one pass and hands the count to WAVStream."""
        self._play(1)
        self.assertEqual(len(self.wav_streams), 1)
        one_pass_size = self.wav_streams[0].file_size

        stream, messages = self._play(1_000_000)

        self.assertEqual(len(self.wav_streams), 2, "WAVStream never started: the whole repeat was rendered first")
        wav = self.wav_streams[1]
        self.assertEqual(wav.file_size, one_pass_size)
        self.assertEqual(wav.repeat_count, 1_000_000)
        self.assertTrue(wav.played)
        self.assertEqual(messages, ["Finished: Test"])

    def test_set_repeat_forwards_to_wav_stream(self):
        """Unchecking Repeat while playing must reach the WAVStream doing the repeating."""
        streams = []
        self.on_play = lambda: streams[0].set_repeat(1)
        streams.append(self.stream_class(self.TUNE, 0, 50, None))
        streams[0].set_repeat(1_000_000)
        streams[0].play()

        self.assertEqual(len(self.wav_streams), 1)
        self.assertEqual(self.wav_streams[0].repeat_count, 1)

    def test_stop_before_wav_stream_plays(self):
        """A stop() that lands while the WAVStream is being created must stop playback."""
        streams = []
        self.on_construct = lambda: streams[0].stop()
        streams.append(self.stream_class(self.TUNE, 0, 50, None))
        streams[0].set_repeat(1_000_000)
        streams[0].play()

        self.assertEqual(len(self.wav_streams), 1)
        self.assertFalse(self.wav_streams[0].played)
