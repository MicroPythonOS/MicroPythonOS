# Unit tests for WAVStream — chunk decode and static helpers
import unittest
import sys
from io import BytesIO

sys.path.insert(0, "lib")
from mpos.audio.stream_wav import WAVStream


class TestReadDecodeChunk(unittest.TestCase):

    def setUp(self):
        self.stream = WAVStream("dummy.wav", 0, 70, {}, lambda m: None)

    def _set_pcm_16bit_mono(self):
        s = self.stream
        s._format_tag = WAVStream.WAVE_FORMAT_PCM
        s._data_size = 10000
        s._channels = 1
        s._bits_per_sample = 16
        s._original_rate = 22050
        s._bytes_per_sample = 2
        s._upsample_factor = 1

    def _set_pcm_8bit_mono(self):
        self._set_pcm_16bit_mono()
        self.stream._bits_per_sample = 8
        self.stream._bytes_per_sample = 1

    def _set_pcm_24bit_mono(self):
        self._set_pcm_16bit_mono()
        self.stream._bits_per_sample = 24
        self.stream._bytes_per_sample = 3

    def _set_pcm_32bit_mono(self):
        self._set_pcm_16bit_mono()
        self.stream._bits_per_sample = 32
        self.stream._bytes_per_sample = 4

    def test_decode_16bit_pcm_mono(self):
        self._set_pcm_16bit_mono()
        data = bytearray([0x00, 0x00] * 12)
        f = BytesIO(data)
        chunk, to_read = self.stream._read_decode_chunk(f, 0)
        self.assertEqual(len(chunk), 24)
        self.assertEqual(chunk, data)
        self.assertTrue(to_read > 0)

    def test_decode_8bit_pcm_mono_converts_to_16bit(self):
        self._set_pcm_8bit_mono()
        data = bytearray([0x80] * 10)
        f = BytesIO(data)
        chunk, to_read = self.stream._read_decode_chunk(f, 0)
        self.assertEqual(len(chunk), 20)
        self.assertEqual(list(chunk), [0x00, 0x00] * 10)

    def test_decode_24bit_pcm_mono_converts_to_16bit(self):
        self._set_pcm_24bit_mono()
        data = bytearray([0x00, 0x00, 0x00] * 10)
        f = BytesIO(data)
        chunk, to_read = self.stream._read_decode_chunk(f, 0)
        self.assertEqual(len(chunk), 20)

    def test_decode_32bit_pcm_mono_converts_to_16bit(self):
        self._set_pcm_32bit_mono()
        data = bytearray([0x00, 0x00, 0x00, 0x00] * 10)
        f = BytesIO(data)
        chunk, to_read = self.stream._read_decode_chunk(f, 0)
        self.assertEqual(len(chunk), 20)

    def test_upsample_factor_2_doubles_output(self):
        self._set_pcm_16bit_mono()
        self.stream._upsample_factor = 2
        data = bytearray([0x00, 0x00] * 5)
        f = BytesIO(data)
        chunk, to_read = self.stream._read_decode_chunk(f, 0)
        self.assertEqual(len(chunk), 20)

    def test_return_none_when_no_data(self):
        self._set_pcm_16bit_mono()
        f = BytesIO(bytearray(0))
        chunk, to_read = self.stream._read_decode_chunk(f, 0)
        self.assertIsNone(chunk)
        self.assertEqual(to_read, 0)

    def test_return_none_when_total_orig_exceeds_data_size(self):
        self._set_pcm_16bit_mono()
        f = BytesIO(bytearray(100))
        self.stream._data_size = 2  # smaller than bytes_per_sample
        chunk, to_read = self.stream._read_decode_chunk(f, 2)
        self.assertIsNone(chunk)
        self.assertEqual(to_read, 0)

    def test_stereo_16bit_pcm(self):
        self._set_pcm_16bit_mono()
        self.stream._channels = 2
        self.stream._bytes_per_sample = 4
        data = bytearray([0x00, 0x00, 0x00, 0x00] * 5)
        f = BytesIO(data)
        chunk, to_read = self.stream._read_decode_chunk(f, 0)
        self.assertEqual(len(chunk), 20)


class TestVolumeToShift(unittest.TestCase):

    def test_volume_0_is_shift_16(self):
        self.assertEqual(WAVStream._volume_percent_to_shift(0), 16)

    def test_volume_100_is_shift_0(self):
        self.assertEqual(WAVStream._volume_percent_to_shift(100), 0)

    def test_volume_50_is_shift_1(self):
        self.assertEqual(WAVStream._volume_percent_to_shift(50), 1)

    def test_volume_negative_gets_shift_16(self):
        self.assertEqual(WAVStream._volume_percent_to_shift(-1), 16)

    def test_volume_over_100_gets_shift_0(self):
        self.assertEqual(WAVStream._volume_percent_to_shift(150), 0)


class TestComputePlaybackRate(unittest.TestCase):

    def test_high_rate_unchanged(self):
        rate, factor = WAVStream.compute_playback_rate(44100, None)
        self.assertEqual(rate, 44100)
        self.assertEqual(factor, 1)

    def test_low_rate_upsampled_to_8000(self):
        rate, factor = WAVStream.compute_playback_rate(4000, None)
        self.assertGreaterEqual(rate, 8000)
        self.assertEqual(factor, 2)

    def test_requested_rate_higher(self):
        rate, factor = WAVStream.compute_playback_rate(8000, 44100)
        self.assertEqual(rate, 48000)  # 8000 * ceil(44100/8000) = 8000 * 6 = 48000
        self.assertEqual(factor, 6)

    def test_requested_rate_lower_returns_original(self):
        rate, factor = WAVStream.compute_playback_rate(44100, 8000)
        self.assertEqual(rate, 44100)
        self.assertEqual(factor, 1)


class TestComputeDrainMs(unittest.TestCase):

    def test_wall_clock_behind_audio_waits_for_the_difference(self):
        self.assertEqual(WAVStream.compute_drain_ms(3000, 2900), 100)

    def test_wall_clock_caught_up_means_no_wait(self):
        self.assertEqual(WAVStream.compute_drain_ms(3000, 3000), 0)

    def test_wall_clock_ahead_of_audio_means_no_wait(self):
        # e.g. playback stalled and ran long: never sleep a negative amount
        self.assertEqual(WAVStream.compute_drain_ms(2000, 4171), 0)

class TestDesktopRepeat(unittest.TestCase):
    """Desktop playback must honor repeat_count like the I2S path does.

    Uses the no-player timing-simulation branch of _play_desktop() (headless)
    by forcing _detect_desktop_player() to find nothing.
    """

    WAV_PATH = "tmp_test_stream_wav_repeat.wav"
    SAMPLE_RATE = 8000
    DURATION_MS = 300

    def setUp(self):
        import mpos.audio.stream_wav as stream_wav_module

        self._module = stream_wav_module
        self._orig_detect = stream_wav_module._detect_desktop_player
        stream_wav_module._detect_desktop_player = lambda: None
        self._write_wav()
        self.completions = []

    def tearDown(self):
        self._module._detect_desktop_player = self._orig_detect
        try:
            import os
            os.remove(self.WAV_PATH)
        except OSError:
            pass

    def _write_wav(self):
        # Minimal 16-bit PCM mono WAV of silence.
        num_samples = self.SAMPLE_RATE * self.DURATION_MS // 1000
        data_size = num_samples * 2
        header = bytearray(44)
        header[0:4] = b"RIFF"
        header[4:8] = (36 + data_size).to_bytes(4, "little")
        header[8:12] = b"WAVE"
        header[12:16] = b"fmt "
        header[16:20] = (16).to_bytes(4, "little")
        header[20:22] = (1).to_bytes(2, "little")
        header[22:24] = (1).to_bytes(2, "little")
        header[24:28] = self.SAMPLE_RATE.to_bytes(4, "little")
        header[28:32] = (self.SAMPLE_RATE * 2).to_bytes(4, "little")
        header[32:34] = (2).to_bytes(2, "little")
        header[34:36] = (16).to_bytes(2, "little")
        header[36:40] = b"data"
        header[40:44] = data_size.to_bytes(4, "little")
        with open(self.WAV_PATH, "wb") as f:
            f.write(header)
            f.write(bytes(data_size))

    def _make_stream(self):
        return WAVStream(
            self.WAV_PATH, 0, 70, {}, lambda m: self.completions.append(m)
        )

    def test_single_play_completes_once(self):
        import time

        stream = self._make_stream()
        start = time.ticks_ms()
        stream.play()
        elapsed = time.ticks_diff(time.ticks_ms(), start)
        self.assertEqual(stream._repeat_played, 1)
        self.assertEqual(len(self.completions), 1)
        self.assertTrue(elapsed < 2 * self.DURATION_MS,
                        "single play took %s ms" % elapsed)

    def test_repeat_plays_all_passes(self):
        import time

        stream = self._make_stream()
        stream.set_repeat(3)
        start = time.ticks_ms()
        stream.play()
        elapsed = time.ticks_diff(time.ticks_ms(), start)
        self.assertEqual(stream._repeat_played, 3)
        # on_complete fires once, after the final pass.
        self.assertEqual(len(self.completions), 1)
        self.assertTrue(elapsed >= int(2.5 * self.DURATION_MS),
                        "3 passes took only %s ms" % elapsed)

    def test_stop_breaks_endless_repeat(self):
        import _thread
        import time

        stream = self._make_stream()
        stream.set_repeat(1_000_000)
        _thread.start_new_thread(stream.play, ())
        time.sleep_ms(2 * self.DURATION_MS)
        stream.stop()
        for _ in range(50):
            if not stream.is_playing():
                break
            time.sleep_ms(100)
        self.assertFalse(stream.is_playing())
        self.assertEqual(len(self.completions), 1)
        # Far fewer passes than requested: stop() ended the loop.
        self.assertTrue(stream._repeat_played < 100)
