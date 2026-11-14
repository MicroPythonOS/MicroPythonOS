"""Unit tests for the pause/seek support added to the audio streams."""

import unittest
from io import BytesIO

from mpos.audio.audiomanager import Player
from mpos.audio.mp3 import frame_offset_for_ms, get_info
from mpos.audio.stream_wav import WAVStream

MP3_DIR = "../tests/data/mp3"
CBR = MP3_DIR + "/tone_a4a5a6_44100_stereo_128cbr.mp3"
VBR = MP3_DIR + "/tone_a4a5a6_44100_stereo_vbr.mp3"
MONO = MP3_DIR + "/tone_a4_22050_mono_64cbr.mp3"


class _FakeStream:
    def __init__(self, seekable=True):
        self.paused = False
        self.seek_ms = None
        self.seekable = seekable

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def seek(self, position_ms):
        if not self.seekable:
            return False
        self.seek_ms = position_ms
        return True


class TestWavSeek(unittest.TestCase):

    def setUp(self):
        self.stream = WAVStream("dummy.wav", 0, 70, {}, None)
        self.stream._original_rate = 1000
        self.stream._format_tag = WAVStream.WAVE_FORMAT_PCM
        self.stream._channels = 1
        self.stream._bits_per_sample = 16
        self.stream._spb = 0

    def test_seek_moves_to_the_requested_pcm_frame(self):
        data = b"x" * 4000
        handle = BytesIO(data)
        self.assertTrue(self.stream.seek(500))
        offset = self.stream._apply_seek(
            handle, 0, len(data), 2, WAVStream.WAVE_FORMAT_PCM, 0)
        self.assertEqual(offset, 1000)
        self.assertEqual(handle.tell(), 1000)
        self.assertEqual(self.stream._progress_samples, 500)
        self.assertIsNone(self.stream._seek_ms)

    def test_seek_is_clamped_to_the_data_chunk(self):
        data = b"x" * 4000
        handle = BytesIO(data)
        self.stream.seek(999999)
        offset = self.stream._apply_seek(
            handle, 0, len(data), 2, WAVStream.WAVE_FORMAT_PCM, 0)
        self.assertEqual(offset, 4000)
        self.assertEqual(handle.tell(), 4000)
        self.assertEqual(self.stream._progress_samples, 2000)

    def test_seek_rounds_to_whole_adpcm_blocks(self):
        data = b"x" * 800
        handle = BytesIO(data)
        self.stream._format_tag = WAVStream.WAVE_FORMAT_ADPCM
        self.stream._spb = 100
        self.stream.seek(500)
        offset = self.stream._apply_seek(
            handle, 0, len(data), 0, WAVStream.WAVE_FORMAT_ADPCM, 200)
        # 500 samples is block 5, but there are only 4 blocks in the chunk.
        self.assertEqual(offset, 800)
        self.assertEqual(handle.tell(), 800)
        self.assertEqual(self.stream._progress_samples, 400)

    def test_pause_and_resume_only_flip_the_flag(self):
        self.assertFalse(self.stream.is_paused())
        self.stream.pause()
        self.assertTrue(self.stream.is_paused())
        self.stream.resume()
        self.assertFalse(self.stream.is_paused())


class TestMp3Seek(unittest.TestCase):

    def _check(self, path):
        info = get_info(path)
        with open(path, "rb") as handle:
            offset, samples = frame_offset_for_ms(handle, 0, info)
            self.assertEqual(offset, info["audio_offset"])
            self.assertEqual(samples, 0)
            self.assertEqual(handle.tell(), info["audio_offset"])

            target = info["duration_ms"] // 2
            offset, samples = frame_offset_for_ms(handle, target, info)
            self.assertEqual(handle.tell(), offset)
            self.assertTrue(offset > info["audio_offset"])
            self.assertTrue(offset < info["file_size"])
            # One frame of error at most: the seek lands on a frame boundary.
            one_frame = info["samples_per_frame"]
            self.assertTrue(
                abs(samples - info["total_samples"] // 2) <= one_frame,
                "samples=%d total=%d" % (samples, info["total_samples"]))
            # The offset must be a real frame header.
            handle.seek(offset)
            from mpos.audio.mp3 import _parse_header
            header = _parse_header(handle.read(4), 0)
            self.assertIsNotNone(header)

    def test_cbr_seek(self):
        self._check(CBR)

    def test_vbr_seek(self):
        self._check(VBR)

    def test_low_rate_mono_seek(self):
        self._check(MONO)

    def test_seek_past_the_end_returns_the_end(self):
        info = get_info(CBR)
        with open(CBR, "rb") as handle:
            offset, samples = frame_offset_for_ms(
                handle, info["duration_ms"] + 60000, info)
            self.assertEqual(handle.tell(), offset)
            self.assertTrue(offset >= info["file_size"] - 1)


class TestPlayerDelegation(unittest.TestCase):

    def test_seek_is_forwarded_to_the_stream(self):
        player = Player(manager=None, file_path="/music/a.wav")
        stream = _FakeStream()
        player._stream = stream
        self.assertTrue(player.seek(1234))
        self.assertEqual(stream.seek_ms, 1234)

    def test_seek_is_refused_without_stream_support(self):
        player = Player(manager=None, file_path="/music/a.rtttl")
        player._stream = _FakeStream(seekable=False)
        self.assertFalse(player.seek(1234))

    def test_pause_and_resume_reach_the_stream(self):
        player = Player(manager=None, file_path="/music/a.wav")
        stream = _FakeStream()
        player._stream = stream
        player.pause()
        self.assertTrue(stream.paused)
        player.resume()
        self.assertFalse(stream.paused)


if __name__ == "__main__":
    unittest.main()
