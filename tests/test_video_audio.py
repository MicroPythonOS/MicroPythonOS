import io
import os
import sys
import unittest

sys.path.insert(0, "apps/com.micropythonos.video_player")

import video_audio


def wav_bytes(tag=1, channels=1, rate=22050, bits=16, block_align=0, data=b"", fact=0):
    fmt = bytearray(16)
    fmt[0:2] = tag.to_bytes(2, "little")
    fmt[2:4] = channels.to_bytes(2, "little")
    fmt[4:8] = rate.to_bytes(4, "little")
    frame_bytes = max(1, channels * bits // 8)
    fmt[12:14] = (block_align or frame_bytes).to_bytes(2, "little")
    fmt[14:16] = bits.to_bytes(2, "little")

    body = bytearray()
    body += b"fmt " + len(fmt).to_bytes(4, "little") + fmt
    if fact:
        body += b"fact" + (4).to_bytes(4, "little") + fact.to_bytes(4, "little")
    body += b"data" + len(data).to_bytes(4, "little") + data

    out = bytearray(b"RIFF")
    out += (4 + len(body)).to_bytes(4, "little")
    out += b"WAVE"
    out += body
    return bytes(out)


def s16(buf, off=0):
    value = buf[off] | (buf[off + 1] << 8)
    return value - 0x10000 if value & 0x8000 else value


def pcm16(samples):
    out = bytearray()
    for value in samples:
        out += (value & 0xFFFF).to_bytes(2, "little")
    return bytes(out)


def ima_block(block_align=1024, channels=1, predictor=0, index=0, nibbles=0):
    """One IMA block: header + nibbles. nibbles=0 repeats the predictor."""
    out = bytearray(block_align)
    out[0:2] = (predictor & 0xFFFF).to_bytes(2, "little")
    out[2] = index
    out[3] = 0
    if nibbles:
        for i in range(4, block_align):
            out[i] = nibbles
    return bytes(out)


class TestWavSourcePcm(unittest.TestCase):
    def test_header_and_duration(self):
        data = pcm16([1, 2, 3, 4])
        source = video_audio.WavSource(io.BytesIO(wav_bytes(data=data)))
        self.assertEqual(source.rate, 22050)
        self.assertEqual(source.channels, 1)
        self.assertEqual(source.format_name, "pcm16")
        self.assertEqual(source.total_frames, 4)
        self.assertEqual(source.duration_ms, 0)
        self.assertEqual(source.byte_rate, 44100)

    def test_reads_sequential_chunks(self):
        data = pcm16(list(range(100)))
        source = video_audio.WavSource(io.BytesIO(wav_bytes(data=data)))
        first = source.read_pcm(40)
        self.assertEqual(len(first), 40)
        self.assertEqual(first[0:4], data[0:4])
        second = source.read_pcm(40)
        self.assertEqual(len(second), 40)
        self.assertEqual(second[0:2], data[40:42])
        rest = b""
        while True:
            chunk = source.read_pcm(40)
            if chunk is None:
                break
            rest += chunk
        self.assertEqual(len(rest), 120)
        self.assertEqual(rest[0:2], data[80:82])

    def test_aligns_to_whole_frames(self):
        data = pcm16(list(range(20)))
        source = video_audio.WavSource(io.BytesIO(wav_bytes(data=data)))
        # Odd limits round down to a whole 16-bit sample.
        self.assertEqual(len(source.read_pcm(41)), 40)

    def test_stereo_byte_rate(self):
        data = pcm16([0] * 20)
        source = video_audio.WavSource(io.BytesIO(wav_bytes(channels=2, data=data)))
        self.assertEqual(source.channels, 2)
        self.assertEqual(source.byte_rate, 88200)
        self.assertEqual(source.total_frames, 10)

    def test_8_bit_expands_to_16(self):
        source = video_audio.WavSource(io.BytesIO(wav_bytes(bits=8, data=bytes([0, 128, 255]))))
        out = source.read_pcm(6)
        self.assertEqual(len(out), 6)
        self.assertEqual(s16(out, 0), -32768)
        self.assertEqual(s16(out, 2), 0)
        self.assertEqual(s16(out, 4), 32512)

    def test_24_bit_keeps_top_half(self):
        data = bytes([0x00, 0x00, 0x40, 0x00, 0x00, 0xC0])
        source = video_audio.WavSource(io.BytesIO(wav_bytes(bits=24, data=data)))
        out = source.read_pcm(6)
        self.assertEqual(s16(out, 0), 0x4000)
        self.assertEqual(s16(out, 2), -0x4000)

    def test_32_bit_keeps_top_half(self):
        data = bytes([0, 0, 0x00, 0x40, 0, 0, 0x00, 0xC0])
        source = video_audio.WavSource(io.BytesIO(wav_bytes(bits=32, data=data)))
        out = source.read_pcm(8)
        self.assertEqual(s16(out, 0), 0x4000)
        self.assertEqual(s16(out, 2), -0x4000)

    def test_read_into_matches_read_pcm(self):
        data = pcm16([(i * 37) & 0x7FFF for i in range(200)])
        source = video_audio.WavSource(io.BytesIO(wav_bytes(data=data)))
        reference = source.read_pcm(64)
        source.rewind()
        out = bytearray(64)
        n = source.read_into(out, 0, 64)
        self.assertEqual(n, len(reference))
        self.assertEqual(out[0:n], reference)

    def test_read_into_writes_at_offset(self):
        data = pcm16([1, 2, 3, 4])
        source = video_audio.WavSource(io.BytesIO(wav_bytes(data=data)))
        out = bytearray(16)
        n = source.read_into(out, 4, 8)
        self.assertEqual(n, 8)
        self.assertEqual(len(out), 16)
        self.assertEqual(out[0:4], b"\x00\x00\x00\x00")
        self.assertEqual(out[4:12], data)

    def test_read_into_reports_end(self):
        data = pcm16([1, 2])
        source = video_audio.WavSource(io.BytesIO(wav_bytes(data=data)))
        out = bytearray(8)
        self.assertEqual(source.read_into(out, 0, 8), 4)
        self.assertEqual(source.read_into(out, 0, 8), 0)

    def test_rejects_ms_adpcm(self):
        with self.assertRaises(ValueError):
            video_audio.WavSource(io.BytesIO(wav_bytes(tag=2, bits=4, block_align=1024, data=bytes(2048))))

    def test_rejects_non_riff(self):
        with self.assertRaises(ValueError):
            video_audio.WavSource(io.BytesIO(b"not a wave file at all"))

    def test_preferred_rate_upsamples(self):
        data = pcm16([1000, 2000])
        # A preferred rate below the file's own rate is not a downgrade.
        source = video_audio.WavSource(io.BytesIO(wav_bytes(data=data)), preferred_rate=16000)
        self.assertEqual(source.playback_rate, 22050)
        self.assertEqual(source.upsample, 1)
        source = video_audio.WavSource(io.BytesIO(wav_bytes(rate=8000, data=data)), preferred_rate=16000)
        self.assertEqual(source.playback_rate, 16000)
        self.assertEqual(source.upsample, 2)
        self.assertEqual(source.byte_rate, 32000)

    def test_skip_bytes_moves_the_reader(self):
        data = pcm16(list(range(100)))
        source = video_audio.WavSource(io.BytesIO(wav_bytes(data=data)))
        self.assertEqual(source.skip_bytes(40), 40)
        self.assertEqual(source.read_pcm(2), data[40:42])
        self.assertEqual(source.skip_bytes(0), 0)

    def test_rewind_restarts(self):
        data = pcm16(list(range(10)))
        source = video_audio.WavSource(io.BytesIO(wav_bytes(data=data)))
        source.read_pcm(10)
        self.assertTrue(source.rewind())
        self.assertEqual(source.read_pcm(2), data[0:2])


class TestWavSourceIma(unittest.TestCase):
    BLOCK = 1024
    PER_BLOCK = 2041

    def _source(self, blocks=2):
        data = ima_block(self.BLOCK) * blocks
        return video_audio.WavSource(
            io.BytesIO(wav_bytes(tag=0x11, bits=4, block_align=self.BLOCK, data=data)))

    def test_header(self):
        source = self._source(3)
        self.assertEqual(source.format_name, "ima")
        self.assertEqual(source.total_frames, 3 * self.PER_BLOCK)
        self.assertEqual(source.byte_rate, 44100)

    def test_decodes_whole_blocks(self):
        source = self._source(2)
        out = source.read_pcm(4096)
        self.assertEqual(len(out), self.PER_BLOCK * 2)
        # Predictor 0 means the block decodes to silence.
        self.assertEqual(out, bytearray(len(out)))
        self.assertEqual(len(source.read_pcm(4096)), self.PER_BLOCK * 2)
        self.assertIsNone(source.read_pcm(4096))

    def test_reads_at_least_one_block(self):
        source = self._source(1)
        out = source.read_pcm(10)
        self.assertEqual(len(out), self.PER_BLOCK * 2)

    def test_read_into_matches_decoder(self):
        data = ima_block(self.BLOCK, nibbles=0x11) * 2
        source = video_audio.WavSource(
            io.BytesIO(wav_bytes(tag=0x11, bits=4, block_align=self.BLOCK, data=data)))
        reference = source.read_pcm(8192)
        source.rewind()
        out = bytearray(8192)
        n = source.read_into(out, 0, 8192)
        self.assertEqual(n, len(reference))
        self.assertEqual(out[0:n], reference)
        # A second refill picks up where the first stopped, including the
        # partial tail block at the end of the stream.
        rest = source.read_into(out, 0, 8192)
        self.assertEqual(rest, 0)

    def test_skip_rounds_to_blocks(self):
        source = self._source(3)
        dropped = source.skip_bytes(self.PER_BLOCK * 2)
        self.assertEqual(dropped, self.PER_BLOCK * 2)
        self.assertEqual(len(source.read_pcm(4096)), self.PER_BLOCK * 2)
        # Less than a block of skip cannot seek, so nothing moves.
        self.assertEqual(source.skip_bytes(2), 0)


class TestAudioClock(unittest.TestCase):
    def setUp(self):
        self.clock = video_audio.AudioClock(44100, lead_ms=120, low_ms=70)

    def test_lead_and_low_in_bytes(self):
        self.assertEqual(self.clock.lead_bytes(), 5292)
        # 70ms is 3087 bytes, rounded down to a whole 16-bit frame.
        self.assertEqual(self.clock.low_bytes(), 3086)

    def test_byte_counts_are_whole_frames(self):
        clock = video_audio.AudioClock(44100, lead_ms=150, low_ms=90, frame_bytes=4)
        self.assertEqual(clock.lead_bytes() % 4, 0)
        self.assertEqual(clock.low_bytes() % 4, 0)
        clock.start(0)
        clock.note(1000)
        self.assertEqual(clock.late_bytes(50) % 4, 0)
        self.assertEqual(clock.to_write(0, 4096) % 4, 0)
        self.assertEqual(clock.due_bytes(50) % 4, 0)

    def test_writes_when_below_low(self):
        self.clock.start(1000)
        self.assertEqual(self.clock.to_write(1000, 4096), 4096)
        self.clock.note(4096)
        self.assertEqual(self.clock.to_write(1000, 10000), 0)
        self.assertEqual(self.clock.to_write(1000, 100), 0)
        # A queue below the low mark is topped up to the lead, capped by the
        # caller's read budget.
        self.clock.start(1000)
        self.clock.note(2000)
        self.assertEqual(self.clock.to_write(1000, 10000), 5292 - 2000)
        self.assertEqual(self.clock.to_write(1000, 100), 100)

    def test_holds_off_while_queue_deep(self):
        self.clock.start(0)
        self.clock.note(5292)
        self.assertEqual(self.clock.pending_ms(0), 120)
        self.assertEqual(self.clock.to_write(0, 4096), 0)
        # 50ms in, 2205 bytes have played: still above low.
        self.assertEqual(self.clock.to_write(50, 4096), 0)
        # 51ms in, 2249 bytes played: one frame below the low mark.
        self.assertEqual(self.clock.to_write(51, 4096), 2248)

    def test_late_bytes(self):
        self.clock.start(0)
        self.clock.note(1000)
        self.assertEqual(self.clock.late_bytes(0), 0)
        self.assertEqual(self.clock.late_bytes(100), 4410 - 1000)

    def test_start_resets(self):
        self.clock.start(0)
        self.clock.note(5000)
        self.clock.start(500)
        self.assertEqual(self.clock.written, 0)
        self.assertEqual(self.clock.due_bytes(500), 0)


class TestAudioTrack(unittest.TestCase):
    def _track(self, seconds=2, byte_rate=44100):
        frames = byte_rate // 2 * seconds
        data = pcm16([0] * frames)
        source = video_audio.WavSource(io.BytesIO(wav_bytes(data=data)))
        sink = video_audio.NullSink()
        return video_audio.AudioTrack(source, sink), sink

    def test_start_primes_the_lead(self):
        track, sink = self._track()
        t0 = track.start(0)
        self.assertEqual(track.written, track.clock.lead_bytes())
        self.assertEqual(sink.written, track.written)
        self.assertEqual(track.clock.start_ms, t0)

    def test_start_returns_when_the_sink_was_ready(self):
        track, sink = self._track()
        before = video_audio._ticks_ms()
        t0 = track.start(before - 5000)
        self.assertTrue(video_audio._ticks_diff(t0, before) >= 0)

    def test_tops_up_between_frames(self):
        track, sink = self._track()
        t0 = track.start(0)
        written = track.written
        low_ms = track.clock.low_ms
        track.tick(t0 + low_ms // 2)
        self.assertEqual(track.written, written)
        track.tick(t0 + low_ms + 1)
        self.assertTrue(track.written > written)
        self.assertEqual(track.clock.pending_bytes(t0 + low_ms + 1),
                         track.clock.lead_bytes())
        self.assertTrue(track.min_pending_ms >= 0)

    def test_taking_the_last_byte_empties_the_ring(self):
        track, sink = self._track()
        track._len = 100
        track._pos = 0
        track._take(100)
        self.assertEqual(track.buffered_bytes(), 0)
        self.assertEqual(track._len, 0)
        self.assertEqual(track._pos, 0)

    def test_refills_after_draining_to_the_very_end(self):
        track, sink = self._track(seconds=2)
        t0 = track.start(0)
        # A block decoder cannot use a short tail, so a cursor parked at the
        # write head used to stall every later refill until the clip ended.
        track._len = track.queue_bytes
        track._pos = track.queue_bytes
        self.assertEqual(track.buffered_bytes(), 0)
        track.tick(t0 + 100)
        self.assertEqual(track.underruns, 0)
        self.assertTrue(track.buffered_bytes() > 0)

    def test_refills_when_the_ring_ends_a_byte_short(self):
        track, sink = self._track(seconds=2)
        t0 = track.start(0)
        # An odd read cursor used to leave the ring one byte short of full,
        # and a nearly empty queue could then never refill again.
        track._len = track.queue_bytes - 1
        track._pos = track.queue_bytes - 1 - 4000
        self.assertEqual(track.buffered_bytes(), 4000)
        track.tick(t0 + 100)
        self.assertEqual(track.underruns, 0)
        self.assertTrue(track.buffered_bytes() > 4000)

    def test_skips_after_a_long_stall(self):
        track, sink = self._track()
        t0 = track.start(0)
        track.tick(t0 + 500)
        self.assertEqual(track.underruns, 1)
        self.assertEqual(track.resyncs, 1)
        self.assertEqual(track.skipped, 22050 - track.clock.lead_bytes())
        self.assertTrue(track.clock.pending_bytes(t0 + 500) >= 0)

    def test_finishes_at_end_of_file(self):
        track, sink = self._track(seconds=1)
        t0 = track.start(0)
        now = t0
        while not track.finished and video_audio._ticks_diff(now, t0) < 3000:
            now += 10
            track.tick(now)
        self.assertTrue(track.finished)
        self.assertTrue(track.written >= 44100)
        self.assertEqual(track.written % 2, 0)


class TestSidecarPath(unittest.TestCase):
    PATH = "data/test_video_audio_clip.mjpeg"
    WAV = "data/test_video_audio_clip.wav"

    def setUp(self):
        try:
            os.mkdir("data")
        except OSError:
            pass
        self._remove()

    def tearDown(self):
        self._remove()

    def _remove(self):
        try:
            os.remove(self.WAV)
        except OSError:
            pass

    def test_finds_matching_wav(self):
        with open(self.WAV, "wb") as f:
            f.write(bytes(4))
        self.assertEqual(video_audio.sidecar_path(self.PATH), self.WAV)

    def test_returns_none_without_sidecar(self):
        self.assertIsNone(video_audio.sidecar_path(self.PATH))

    def test_ignores_video_extension(self):
        self.assertIsNone(video_audio.sidecar_path("data/clip"))
        self.assertIsNone(video_audio.sidecar_path("data/clip.mjpg"))


if __name__ == "__main__":
    unittest.main()
