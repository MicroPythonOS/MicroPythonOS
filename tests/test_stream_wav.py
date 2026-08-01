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
