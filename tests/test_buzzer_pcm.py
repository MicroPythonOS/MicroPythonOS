# Unit tests for the piezo buzzer PCM chain (mpos.audio.stream_buzzer).
#
# The ESP32 driver itself lives in c_mpos/src/buzzer.c and needs hardware, so
# these tests cover the part that runs everywhere: WAV/MP3 decoding through
# WAVStream, mono downmix, volume attenuation and repeat, using the emulated
# sink that renders exactly what the driver would have received.

import os
import sys
import unittest

sys.path.insert(0, "lib")

from mpos.testing import MockMachine, MockThread, inject_mocks
from mpos.testing.mocks import MockSharedPreferences, create_mock_module

# Mock hardware before anything imports AudioManager/WAVStream.
inject_mocks({
    "machine": MockMachine(),
    "_thread": MockThread,
    "mpos.shared_preferences": create_mock_module(
        "mpos.shared_preferences", SharedPreferences=MockSharedPreferences),
})

from mpos.audio import stream_buzzer
from mpos.audio import audiomanager as _audiomanager
from mpos.audio.audiomanager import AudioManager
from mpos.audio.stream_buzzer import (
    BuzzerMP3Stream,
    BuzzerStream,
    _EmulatedBuzzerSink,
)
from mpos.audio.stream_wav import WAVStream

# mpos/__init__.py imports AudioManager before the mocks above are installed,
# so audiomanager already holds a reference to the real _thread module. Point
# it at the mock so playback threads are recorded instead of started.
_audiomanager._thread = MockThread

TMP_DIR = "/tmp/mpos_buzzer_tests"
MP3_FIXTURES = "../tests/data/mp3"


def _ensure_tmp():
    try:
        os.mkdir(TMP_DIR)
    except OSError:
        pass


def _write_wav(path, values, rate=22050, channels=1, bits=16):
    """Write a WAV from a list of sample values (or a frame count for a sine)."""
    import math

    if isinstance(values, int):
        values = [int(20000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(values)]

    data = bytearray()
    for value in values:
        if bits == 8:
            data.append((value + 128) & 0xFF)
        elif bits == 16:
            data.extend((value & 0xFFFF).to_bytes(2, "little"))
        elif bits == 24:
            data.extend((value & 0xFFFFFF).to_bytes(3, "little"))
        elif bits == 32:
            data.extend((value & 0xFFFFFFFF).to_bytes(4, "little"))

    byte_rate = rate * channels * (bits // 8)
    with open(path, "wb") as f:
        f.write(b"RIFF\x00\x00\x00\x00WAVEfmt ")
        f.write((16).to_bytes(4, "little"))
        f.write((1).to_bytes(2, "little"))
        f.write(channels.to_bytes(2, "little"))
        f.write(rate.to_bytes(4, "little"))
        f.write(byte_rate.to_bytes(4, "little"))
        f.write((channels * bits // 8).to_bytes(2, "little"))
        f.write(bits.to_bytes(2, "little"))
        f.write(b"data\x00\x00\x00\x00")
        f.write(data)
        f.seek(4)
        f.write((len(data) + 36).to_bytes(4, "little"))
        f.seek(40)
        f.write(len(data).to_bytes(4, "little"))
    return path


def _read_pcm16(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise AssertionError("not a RIFF/WAVE file: %r" % data[0:12])
    size = int.from_bytes(data[40:44], "little")
    return data[44:44 + size]


def _sample_at(raw, index):
    value = raw[index] | (raw[index + 1] << 8)
    if value & 0x8000:
        value -= 0x10000
    return value


def _samples(raw):
    out = []
    for i in range(0, len(raw), 2):
        value = raw[i] | (raw[i + 1] << 8)
        if value & 0x8000:
            value -= 0x10000
        out.append(value)
    return out


class _CapturingStream(BuzzerStream):
    """BuzzerStream that keeps the emulated output instead of playing it."""

    def _play_emulated(self, sink):
        self.captured_rate = sink.rate
        self.captured_samples = sink.samples
        self.captured = _read_pcm16(sink.path)
        self._remove_emulated(sink)


class _CapturingMP3Stream(BuzzerMP3Stream):

    def _play_emulated(self, sink):
        self.captured_rate = sink.rate
        self.captured_samples = sink.samples
        self._remove_emulated(sink)


class TestEmulatedSink(unittest.TestCase):

    def setUp(self):
        _ensure_tmp()
        self.sink = _EmulatedBuzzerSink(22050, 1)

    def tearDown(self):
        try:
            os.remove(self.sink.path)
        except OSError:
            pass

    def test_mono_samples_are_written_unchanged(self):
        buf = bytearray((1000).to_bytes(2, "little") + (-1000 & 0xFFFF).to_bytes(2, "little"))
        self.assertEqual(self.sink.write(buf), 4)
        self.sink.deinit()
        self.assertEqual(_samples(_read_pcm16(self.sink.path)), [1000, -1000])

    def test_stereo_is_downmixed(self):
        sink = _EmulatedBuzzerSink(22050, 2)
        try:
            values = [1000, 3000, -1000, -3000, 32767, -32768]
            buf = bytearray()
            for value in values:
                buf.extend((value & 0xFFFF).to_bytes(2, "little"))
            self.assertEqual(sink.write(buf), len(buf))
        finally:
            sink.deinit()
        # (left + right) >> 1, so (32767, -32768) lands on -1
        self.assertEqual(_samples(_read_pcm16(sink.path)), [2000, -2000, -1])
        os.remove(sink.path)

    def test_attenuate_is_a_right_shift(self):
        buf = bytearray((1000 & 0xFFFF).to_bytes(2, "little") + (-1000 & 0xFFFF).to_bytes(2, "little"))
        self.sink.shift(buf=buf, bits=16, shift=-3)
        self.assertEqual(_sample_at(buf, 0), 125)
        self.assertEqual(_sample_at(buf, 2), -125)


class TestBuzzerStream(unittest.TestCase):

    def setUp(self):
        _ensure_tmp()
        self.completed = []
        self.wav = _write_wav(os.path.join(TMP_DIR, "mono16.wav"), 4410)

    def _stream(self, volume=100, **kwargs):
        path = kwargs.pop("file_path", self.wav)
        return _CapturingStream(
            file_path=path,
            stream_type=0,
            volume=volume,
            buzzer_pin=-1,
            on_complete=lambda message: self.completed.append(message),
            **kwargs
        )

    def test_mono_16bit_roundtrip(self):
        stream = self._stream()
        stream.play()
        self.assertEqual(stream.captured_rate, 22050)
        self.assertEqual(len(stream.captured), 4410 * 2)
        with open(self.wav, "rb") as f:
            expected = f.read()[44:]
        self.assertEqual(bytes(stream.captured), expected)
        self.assertEqual(len(self.completed), 1)

    def test_volume_is_applied(self):
        stream = self._stream(volume=50)
        stream.play()
        shift = WAVStream._volume_percent_to_shift(50)
        self.assertTrue(shift > 0)
        with open(self.wav, "rb") as f:
            expected = _samples(f.read()[44:])
        got = _samples(stream.captured)
        self.assertEqual(len(got), len(expected))
        for index in range(0, len(expected), 97):
            self.assertEqual(got[index], expected[index] >> shift)

    def test_stereo_wav_becomes_mono(self):
        path = os.path.join(TMP_DIR, "stereo16.wav")
        _write_wav(path, [1000] * 2204, channels=2)
        stream = self._stream(file_path=path)
        stream.play()
        self.assertEqual(stream.captured_rate, 22050)
        self.assertEqual(len(stream.captured), 1102 * 2)
        self.assertEqual(_samples(stream.captured)[:3], [1000, 1000, 1000])

    def test_8bit_wav_is_converted_to_16bit(self):
        path = os.path.join(TMP_DIR, "mono8.wav")
        _write_wav(path, [0, 64, 192], bits=8)
        stream = self._stream(file_path=path)
        stream.play()
        self.assertEqual(_samples(stream.captured), [0, 16384, -16384])

    def test_repeat_count_replays_the_file(self):
        stream = self._stream(repeat_count=2)
        stream.play()
        self.assertEqual(len(stream.captured), 4410 * 2 * 2)

    def test_stop_before_playback(self):
        # Stopping a stream that never opened a sink must not raise. This used
        # to fail with "'super' object has no attribute 'stop'" on the device.
        stream = self._stream()
        stream.stop()
        self.assertFalse(stream._keep_running)

    def test_mp3_stop_does_not_raise(self):
        stream = _CapturingMP3Stream(
            file_path=self.wav,
            stream_type=0,
            volume=100,
            buzzer_pin=-1,
            on_complete=None,
        )
        stream.stop()

    def test_mp3_decodes_to_mono(self):
        path = os.path.join(MP3_FIXTURES, "tone_a4a5a6_44100_stereo_128cbr.mp3")
        if not os.path.exists(path):
            self.skipTest("mp3 fixture missing")
        stream = _CapturingMP3Stream(
            file_path=path,
            stream_type=0,
            volume=100,
            buzzer_pin=-1,
            on_complete=None,
        )
        stream.play()
        self.assertEqual(stream.captured_rate, 44100)
        # 176256 stereo frames in the fixture become 176256 mono samples.
        self.assertEqual(stream.captured_samples, 176256)


class TestAudioManagerRouting(unittest.TestCase):

    def setUp(self):
        _ensure_tmp()
        self.AudioManager = AudioManager
        AudioManager._instance = None
        MockSharedPreferences.reset_all()
        AudioManager()
        self.buzzer = AudioManager.add(
            AudioManager.Output("buzzer", "buzzer", buzzer_pin=46))
        self.wav = _write_wav(os.path.join(TMP_DIR, "route.wav"), 2205)
        MockThread._started_threads = []

    def tearDown(self):
        self.AudioManager.stop()

    def test_wav_file_is_routed_to_buzzer_stream(self):
        played = []
        self.buzzer.buzzer_gain = 600

        class FakeStream:
            def __init__(self, **kwargs):
                played.append(kwargs)

            def play(self):
                pass

        original = stream_buzzer.BuzzerStream
        stream_buzzer.BuzzerStream = FakeStream
        try:
            player = self.AudioManager.player(file_path=self.wav, output=self.buzzer)
            player.start()
            self.assertEqual(len(MockThread._started_threads), 1)
            MockThread._started_threads[0][0]()
        finally:
            stream_buzzer.BuzzerStream = original

        self.assertEqual(len(played), 1)
        self.assertEqual(played[0]["buzzer_pin"], 46)
        self.assertEqual(played[0]["buzzer_gain"], 600)
        self.assertEqual(played[0]["file_path"], self.wav)

    def test_buzzer_without_source_is_rejected(self):
        with self.assertRaises(ValueError):
            self.AudioManager.player(output=self.buzzer).start()
