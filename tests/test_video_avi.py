import io
import os
import sys
import unittest

sys.path.insert(0, "apps/com.micropythonos.video_player")

import video_avi


def chunk(chunk_id, payload):
    out = chunk_id + len(payload).to_bytes(4, "little") + bytes(payload)
    if len(payload) & 1:
        out += b"\x00"
    return out


def list_chunk(kind, payload):
    return chunk(b"LIST", kind + bytes(payload))


def avih(width, height, fps, frames, streams=2):
    out = bytearray(56)
    out[0:4] = (1000000 // fps).to_bytes(4, "little")
    out[16:20] = frames.to_bytes(4, "little")
    out[24:28] = streams.to_bytes(4, "little")
    out[32:36] = width.to_bytes(4, "little")
    out[36:40] = height.to_bytes(4, "little")
    return bytes(out)


def strh(kind, handler, scale, rate, length, block_align=0):
    out = bytearray(56)
    out[0:4] = kind
    out[4:8] = handler
    out[20:24] = scale.to_bytes(4, "little")
    out[24:28] = rate.to_bytes(4, "little")
    out[32:36] = length.to_bytes(4, "little")
    out[44:48] = block_align.to_bytes(4, "little")
    return bytes(out)


def bitmap_info(width, height, fourcc=b"MJPG"):
    out = bytearray(40)
    out[0:4] = (40).to_bytes(4, "little")
    out[4:8] = width.to_bytes(4, "little")
    out[8:12] = height.to_bytes(4, "little")
    out[12:14] = (1).to_bytes(2, "little")
    out[14:16] = (24).to_bytes(2, "little")
    out[16:20] = fourcc
    out[20:24] = (width * height * 3).to_bytes(4, "little")
    return bytes(out)


def wave_format(tag, channels, rate, bits, block_align=None, samples_per_block=0):
    block_align = block_align or channels * bits // 8
    out = bytearray(16)
    out[0:2] = tag.to_bytes(2, "little")
    out[2:4] = channels.to_bytes(2, "little")
    out[4:8] = rate.to_bytes(4, "little")
    out[8:12] = (rate * block_align).to_bytes(4, "little")
    out[12:14] = block_align.to_bytes(2, "little")
    out[14:16] = bits.to_bytes(2, "little")
    if tag != video_avi.WAVE_FORMAT_PCM:
        out = out + (2).to_bytes(2, "little") + samples_per_block.to_bytes(2, "little")
    return bytes(out)


def avi_bytes(frames, audio_chunks, width=32, height=24, fps=15,
              audio_tag=video_avi.WAVE_FORMAT_PCM, channels=1, rate=22050,
              bits=16, block_align=None, samples_per_block=0, fourcc=b"MJPG"):
    hdrl = chunk(b"avih", avih(width, height, fps, len(frames)))
    hdrl += list_chunk(b"strl", chunk(b"strh", strh(b"vids", fourcc, 1, fps, len(frames)))
                       + chunk(b"strf", bitmap_info(width, height, fourcc)))
    if audio_tag is not None:
        hdrl += list_chunk(b"strl", chunk(b"strh", strh(b"auds", b"\x00\x00\x00\x00", 1, rate, 0))
                           + chunk(b"strf", wave_format(audio_tag, channels, rate, bits,
                                                       block_align, samples_per_block)))
    movi = bytearray()
    for index, frame in enumerate(frames):
        movi += chunk(b"00dc", frame)
        if audio_chunks and index < len(audio_chunks):
            movi += chunk(b"01wb", audio_chunks[index])
    body = list_chunk(b"hdrl", hdrl) + list_chunk(b"movi", movi)
    return b"RIFF" + (4 + len(body)).to_bytes(4, "little") + b"AVI " + body


def jpeg(payload):
    return b"\xff\xd8" + bytes(payload) + b"\xff\xd9"


class TestAviReader(unittest.TestCase):
    def setUp(self):
        self.path = "data/test_video_avi.avi"
        try:
            os.mkdir("data")
        except OSError:
            pass

    def tearDown(self):
        try:
            os.remove(self.path)
        except OSError:
            pass

    def _write(self, data):
        with open(self.path, "wb") as handle:
            handle.write(data)
        return self.path

    def test_header_gives_size_rate_and_frames(self):
        frames = [jpeg(b"a" * 10), jpeg(b"b" * 12)]
        reader = video_avi.AviReader(self._write(avi_bytes(frames, [], audio_tag=None)))
        self.assertEqual(reader.fps, 15)
        self.assertEqual(reader.width, 32)
        self.assertEqual(reader.height, 24)
        self.assertEqual(reader.frame_count, 2)
        self.assertIsNone(reader.audio)
        reader.close()

    def test_reads_each_video_chunk_in_order(self):
        frames = [jpeg(b"one"), jpeg(b"three" * 4), jpeg(b"five" * 9)]
        reader = video_avi.AviReader(self._write(avi_bytes(frames, [], audio_tag=None)))
        got = []
        while True:
            frame = reader.next()
            if frame is None:
                break
            got.append(bytes(frame))
        self.assertEqual(got, frames)
        self.assertEqual(reader.frames, 3)
        reader.close()

    def test_skips_over_audio_chunks(self):
        frames = [jpeg(b"a"), jpeg(b"b")]
        audio = [bytes(4), bytes(4)]
        reader = video_avi.AviReader(self._write(avi_bytes(frames, audio)))
        self.assertEqual(bytes(reader.next()), frames[0])
        self.assertEqual(bytes(reader.next()), frames[1])
        self.assertIsNone(reader.next())
        reader.close()

    def test_skip_advances_video_only(self):
        frames = [jpeg(bytes([i]) * 8) for i in range(6)]
        reader = video_avi.AviReader(self._write(avi_bytes(frames, [], audio_tag=None)))
        reader.next()
        self.assertTrue(reader.skip(3))
        self.assertEqual(bytes(reader.next()), frames[4])
        self.assertEqual(reader.skipped, 3)
        reader.close()

    def test_skip_past_the_end_reports_failure(self):
        frames = [jpeg(b"a"), jpeg(b"b")]
        reader = video_avi.AviReader(self._write(avi_bytes(frames, [], audio_tag=None)))
        self.assertFalse(reader.skip(5))
        self.assertIsNone(reader.next())
        reader.close()

    def test_rewind_starts_over(self):
        frames = [jpeg(b"a"), jpeg(b"b")]
        reader = video_avi.AviReader(self._write(avi_bytes(frames, [], audio_tag=None)))
        first = bytes(reader.next())
        reader.next()
        self.assertTrue(reader.rewind())
        self.assertEqual(bytes(reader.next()), first)
        reader.close()

    def test_rejects_a_non_avi_file(self):
        with self.assertRaises(video_avi.UnsupportedFormat) as caught:
            video_avi.AviReader(self._write(b"\xff\xd8not riff\xff\xd9" * 4))
        self.assertIn("not an AVI", caught.exception.message)

    def test_rejects_a_video_codec_it_cannot_play(self):
        frames = [jpeg(b"a")]
        with self.assertRaises(video_avi.UnsupportedFormat) as caught:
            video_avi.AviReader(self._write(avi_bytes(frames, [], fourcc=b"H264")))
        self.assertIn("H264", caught.exception.message)
        self.assertIn("MJPEG", caught.exception.message)

    def test_an_unsupported_audio_codec_still_lets_video_play(self):
        frames = [jpeg(b"a"), jpeg(b"b")]
        audio = [bytes(8), bytes(8)]
        reader = video_avi.AviReader(self._write(avi_bytes(
            frames, audio, audio_tag=video_avi.WAVE_FORMAT_MP3, bits=0)))
        self.assertEqual(bytes(reader.next()), frames[0])
        with self.assertRaises(video_avi.UnsupportedFormat) as caught:
            reader.audio_source()
        self.assertIn("MP3", caught.exception.message)
        reader.close()


class TestAviAudioPcm(unittest.TestCase):
    def setUp(self):
        self.path = "data/test_video_avi_audio.avi"
        try:
            os.mkdir("data")
        except OSError:
            pass

    def tearDown(self):
        try:
            os.remove(self.path)
        except OSError:
            pass

    def _reader(self, frames, chunks, **kwargs):
        data = avi_bytes(frames, chunks, **kwargs)
        with open(self.path, "wb") as handle:
            handle.write(data)
        return video_avi.AviReader(self.path)

    def test_pcm_audio_is_the_concatenated_payload(self):
        chunks = [bytes([1, 0, 2, 0]), bytes([3, 0, 4, 0]), bytes([5, 0])]
        reader = self._reader([jpeg(b"a"), jpeg(b"b"), jpeg(b"c")], chunks)
        source = reader.audio_source()
        reader.prefill_audio(1000)
        self.assertEqual(source.format_name, "pcm16")
        self.assertEqual(source.channels, 1)
        self.assertEqual(source.playback_rate, 22050)
        self.assertEqual(source.byte_rate, 44100)
        out = bytearray(64)
        got = source.read_into(out, 0, 64)
        self.assertEqual(got, 10)
        self.assertEqual(out[0:10], bytes([1, 0, 2, 0, 3, 0, 4, 0, 5, 0]))
        self.assertEqual(source.read_into(out, 0, 64), 0)
        self.assertTrue(source.exhausted)
        source.close()
        reader.close()

    def test_pcm_audio_reads_in_pieces(self):
        chunks = [bytes(range(0, 20)), bytes(range(20, 40))]
        reader = self._reader([jpeg(b"a"), jpeg(b"b")], chunks)
        source = reader.audio_source()
        reader.prefill_audio(1000)
        out = bytearray(64)
        first = source.read_into(out, 0, 6)
        second = source.read_into(out, first, 6)
        self.assertEqual(first, 6)
        self.assertEqual(second, 6)
        self.assertEqual(out[0:12], bytes(range(0, 12)))
        source.close()
        reader.close()

    def test_sound_arrives_with_the_frames_read_ahead(self):
        chunks = [bytes(4)] * 3
        reader = self._reader([jpeg(b"a"), jpeg(b"b"), jpeg(b"c")], chunks)
        source = reader.audio_source()
        self.assertEqual(source.remaining_bytes > 0, True)
        reader.next()
        # The demuxer keeps frames read ahead, so the sound belonging to them
        # is queued before anything is presented. That queue is the lead.
        self.assertEqual(len(reader._pending), 2)
        self.assertEqual(reader.feed.buffered(), 12)

    def test_prefill_keeps_the_frames_it_passed(self):
        frames = [jpeg(bytes([i]) * 8) for i in range(4)]
        chunks = [bytes(6)] * 4
        reader = self._reader(frames, chunks)
        source = reader.audio_source()
        queued = reader.prefill_audio(1000)
        self.assertEqual(queued, 24)
        self.assertEqual(len(reader._pending), 4)
        got = []
        while True:
            frame = reader.next()
            if frame is None:
                break
            got.append(bytes(frame))
        self.assertEqual(got, frames)

    def test_rewind_empties_the_sound_feed(self):
        chunks = [bytes(4)] * 2
        reader = self._reader([jpeg(b"a"), jpeg(b"b")], chunks)
        source = reader.audio_source()
        reader.prefill_audio(1000)
        self.assertTrue(reader.feed.buffered() > 0)
        reader.rewind()
        self.assertEqual(reader.feed.buffered(), 0)

    def test_pcm_skip_advances_the_stream(self):
        chunks = [bytes(range(0, 20)), bytes(range(20, 40))]
        reader = self._reader([jpeg(b"a"), jpeg(b"b")], chunks)
        source = reader.audio_source()
        reader.prefill_audio(1000)
        self.assertEqual(source.skip_bytes(10), 10)
        out = bytearray(16)
        got = source.read_into(out, 0, 16)
        self.assertEqual(got, 16)
        self.assertEqual(out[0:4], bytes([10, 11, 12, 13]))
        source.close()
        reader.close()

    def test_8bit_pcm_is_widened_to_16bit(self):
        chunks = [bytes([0x00, 0x80, 0xFF])]
        reader = self._reader([jpeg(b"a")], chunks, bits=8)
        source = reader.audio_source()
        reader.prefill_audio(1000)
        self.assertEqual(source.format_name, "pcm8")
        out = bytearray(8)
        got = source.read_into(out, 0, 8)
        self.assertEqual(got, 6)
        # 0x00 -> -32768, 0x80 -> 0, 0xFF -> 32512, all little endian.
        self.assertEqual(out[0:6], bytes([0x00, 0x80, 0x00, 0x00, 0x00, 0x7F]))
        source.close()
        reader.close()


class TestAviAudioIma(unittest.TestCase):
    BLOCK = 1024
    SPB = 1 + (1024 - 4) * 2

    def setUp(self):
        self.path = "data/test_video_avi_ima.avi"
        try:
            os.mkdir("data")
        except OSError:
            pass

    def tearDown(self):
        try:
            os.remove(self.path)
        except OSError:
            pass

    def _block(self, nibbles):
        out = bytearray(self.BLOCK)
        out[0:2] = (1000).to_bytes(2, "little")
        out[2] = 20
        if nibbles:
            for i in range(4, self.BLOCK):
                out[i] = nibbles
        return bytes(out)

    def test_ima_blocks_decode_like_the_reference_decoder(self):
        from mpos.audio.adpcm_ima import decode_block_into

        blocks = [self._block(0x11), self._block(0x22)]
        data = avi_bytes([jpeg(b"a"), jpeg(b"b")], blocks,
                         audio_tag=video_avi.WAVE_FORMAT_IMA_ADPCM, bits=4,
                         block_align=self.BLOCK, samples_per_block=self.SPB)
        with open(self.path, "wb") as handle:
            handle.write(data)
        reader = video_avi.AviReader(self.path)
        source = reader.audio_source()
        reader.prefill_audio(1000)
        self.assertEqual(source.format_name, "ima")
        out = bytearray(self.SPB * 2 * 2 + 16)
        got = source.read_into(out, 0, len(out))
        self.assertEqual(got, self.SPB * 2 * 2)

        reference = bytearray(self.SPB * 2)
        decode_block_into(memoryview(blocks[0]), 1, self.BLOCK, reference, 0)
        self.assertEqual(out[0:self.SPB * 2], reference)
        decode_block_into(memoryview(blocks[1]), 1, self.BLOCK, reference, 0)
        self.assertEqual(out[self.SPB * 2:self.SPB * 4], reference)
        source.close()
        reader.close()

    def test_ima_skip_rounds_to_blocks(self):
        blocks = [self._block(0x11), self._block(0x22), self._block(0x33)]
        data = avi_bytes([jpeg(b"a"), jpeg(b"b"), jpeg(b"c")], blocks,
                         audio_tag=video_avi.WAVE_FORMAT_IMA_ADPCM, bits=4,
                         block_align=self.BLOCK, samples_per_block=self.SPB)
        with open(self.path, "wb") as handle:
            handle.write(data)
        reader = video_avi.AviReader(self.path)
        source = reader.audio_source()
        reader.prefill_audio(1000)
        per_block = self.SPB * 2
        self.assertEqual(source.skip_bytes(per_block + 7), per_block)
        out = bytearray(per_block * 2)
        got = source.read_into(out, 0, len(out))
        self.assertEqual(got, per_block * 2)
        source.close()
        reader.close()


if __name__ == "__main__":
    unittest.main()
