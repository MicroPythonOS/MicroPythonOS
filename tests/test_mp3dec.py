"""Tests for the mp3dec native module (c_mpos/src/mp3dec.c + minimp3).

The fixtures in tests/data/mp3/ are the same tone renders the manual DAC test
plays through the badge speaker: 0.25 s of silence, then a 1 s A4, A5 and A6
(440/880/1760 Hz) each with 0.12 s gaps, then 0.3 s of silence. They cover
MPEG-1/2/2.5, CBR and VBR (Xing), mono and stereo, 8/22.05/44.1/48 kHz.

Frame and sample totals below come from decoding whole files in one buffer,
which is minimp3's normal (non-streaming) usage. Streaming must produce the
same totals for every feed chunk size: a partial frame at the end of a chunk
has to be kept, not discarded.
"""

import math
import os
import struct
import unittest

import mp3dec

FIXTURES = "../tests/data/mp3"

# name: (sample rate, channels, frames, samples)
ASSETS = {
    "tone_a4a5a6_44100_stereo_128cbr.mp3": (44100, 2, 153, 176256),
    "tone_a4a5a6_44100_stereo_vbr.mp3": (44100, 2, 154, 177408),
    "tone_a4_22050_mono_64cbr.mp3": (22050, 1, 61, 35136),
    "tone_a4_8000_mono_16cbr.mp3": (8000, 1, 24, 13824),
    "tone_a4_48000_stereo_320cbr.mp3": (48000, 2, 32, 36864),
}

CHUNK_SIZES = (1024, 4096, 8192)

_HAVE_FIXTURES = os.path.isfile(FIXTURES + "/" + next(iter(ASSETS)))
_NO_FIXTURES = "fixtures in " + FIXTURES + " are not available"


def _decode_stream(decoder, data, chunk_size, shift=0):
    """Feed *data* in chunks, draining the decoder after each one."""
    out = bytearray(16384)
    pcm = bytearray()
    for offset in range(0, len(data), chunk_size):
        chunk = data[offset:offset + chunk_size]
        if offset + chunk_size >= len(data):
            decoder.finish()
        while True:
            written = decoder.decode_into(chunk, out, shift)
            chunk = b""
            if not written:
                break
            pcm.extend(memoryview(out)[:written])
    return bytes(pcm)


def _decode_file(name, chunk_size, shift=0):
    """Return (pcm, decoder info tuple) for a fixture."""
    decoder = mp3dec.Decoder()
    try:
        with open(FIXTURES + "/" + name, "rb") as f:
            data = f.read()
        return _decode_stream(decoder, data, chunk_size, shift), decoder.info()
    finally:
        decoder.close()


def _peak(pcm, channels):
    peak = 0
    for i in range(0, len(pcm) // (2 * channels)):
        value = struct.unpack_from("<h", pcm, i * 2 * channels)[0]
        if value < 0:
            value = -value
        if value > peak:
            peak = value
    return peak


def _goertzel(pcm, rate, channels, start_s, duration_s, freq):
    start = int(start_s * rate)
    count = int(duration_s * rate)
    coeff = 2.0 * math.cos(2.0 * math.pi * freq / rate)
    s1 = 0.0
    s2 = 0.0
    for i in range(start, start + count):
        sample = struct.unpack_from("<h", pcm, i * 2 * channels)[0] / 32768.0
        s0 = sample + coeff * s1 - s2
        s2 = s1
        s1 = s0
    return math.sqrt(s1 * s1 + s2 * s2 - coeff * s1 * s2) / count


class TestMP3DecoderAPI(unittest.TestCase):

    def test_frame_bytes(self):
        self.assertEqual(mp3dec.FRAME_BYTES, 4608)

    def test_output_buffer_too_small(self):
        decoder = mp3dec.Decoder()
        try:
            with self.assertRaises(ValueError):
                decoder.decode_into(b"", bytearray(mp3dec.FRAME_BYTES - 1), 0)
        finally:
            decoder.close()

    def test_closed_decoder_raises(self):
        decoder = mp3dec.Decoder()
        decoder.close()
        with self.assertRaises(RuntimeError):
            decoder.decode_into(b"", bytearray(mp3dec.FRAME_BYTES), 0)

    def test_empty_input(self):
        decoder = mp3dec.Decoder()
        try:
            self.assertEqual(decoder.decode_into(b"", bytearray(16384), 0), 0)
        finally:
            decoder.close()

    def test_input_buffer_overflow_raises(self):
        decoder = mp3dec.Decoder()
        try:
            with self.assertRaises(ValueError):
                decoder.decode_into(b"\x00" * 17000, bytearray(16384), 0)
        finally:
            decoder.close()


class TestMP3Streaming(unittest.TestCase):

    @unittest.skipIf(not _HAVE_FIXTURES, _NO_FIXTURES)
    def test_frame_counts_independent_of_chunk_size(self):
        for name in sorted(ASSETS):
            rate, channels, frames, samples = ASSETS[name]
            for chunk_size in CHUNK_SIZES:
                pcm, info = _decode_file(name, chunk_size)
                self.assertEqual(info[0], rate, "%s hz @ %d" % (name, chunk_size))
                self.assertEqual(
                    info[1], channels, "%s channels @ %d" % (name, chunk_size)
                )
                self.assertEqual(
                    info[5], frames, "%s frames @ %d" % (name, chunk_size)
                )
                self.assertEqual(
                    info[6], samples, "%s samples @ %d" % (name, chunk_size)
                )
                self.assertEqual(
                    len(pcm), samples * channels * 2, "%s pcm @ %d" % (name, chunk_size)
                )

    @unittest.skipIf(not _HAVE_FIXTURES, _NO_FIXTURES)
    def test_id3_tag_skipped(self):
        for name in sorted(ASSETS):
            pcm, info = _decode_file(name, 4096)
            self.assertEqual(info[7], 45, "%s id3 bytes" % name)

    @unittest.skipIf(not _HAVE_FIXTURES, _NO_FIXTURES)
    def test_tone_frequency(self):
        for name in sorted(ASSETS):
            pcm, info = _decode_file(name, 4096)
            rate = info[0]
            channels = info[1]
            a4 = _goertzel(pcm, rate, channels, 0.35, 0.3, 440)
            a5 = _goertzel(pcm, rate, channels, 0.35, 0.3, 880)
            a6 = _goertzel(pcm, rate, channels, 0.35, 0.3, 1760)
            self.assertTrue(a4 > 0.02, "%s a4 level %s" % (name, a4))
            self.assertTrue(a4 > a5 * 4, "%s a4/a5 %s/%s" % (name, a4, a5))
            self.assertTrue(a4 > a6 * 4, "%s a4/a6 %s/%s" % (name, a4, a6))

    @unittest.skipIf(not _HAVE_FIXTURES, _NO_FIXTURES)
    def test_volume_shift_scales_output(self):
        name = "tone_a4_8000_mono_16cbr.mp3"
        pcm_full, info = _decode_file(name, 4096, 0)
        pcm_half, _ = _decode_file(name, 4096, 1)
        pcm_quarter, _ = _decode_file(name, 4096, 2)
        self.assertEqual(len(pcm_full), len(pcm_half))
        full = _peak(pcm_full, info[1])
        half = _peak(pcm_half, info[1])
        quarter = _peak(pcm_quarter, info[1])
        self.assertTrue(full > 8000)
        self.assertTrue(full // 2 - 2 <= half <= full // 2 + 2, "%s/%s" % (full, half))
        self.assertTrue(
            full // 4 - 2 <= quarter <= full // 4 + 2, "%s/%s" % (full, quarter)
        )

    @unittest.skipIf(not _HAVE_FIXTURES, _NO_FIXTURES)
    def test_garbage_prefix_and_trailer_resynchronise(self):
        name = "tone_a4a5a6_44100_stereo_128cbr.mp3"
        reference, reference_info = _decode_file(name, 4096)
        with open(FIXTURES + "/" + name, "rb") as f:
            data = f.read()
        decoder = mp3dec.Decoder()
        try:
            pcm = _decode_stream(
                decoder,
                b"\x00\x01\x02garbage" + data + b"\xff\x00" * 32,
                4096,
            )
            self.assertEqual(decoder.info()[5], reference_info[5])
        finally:
            decoder.close()
        self.assertEqual(pcm, reference)

    @unittest.skipIf(not _HAVE_FIXTURES, _NO_FIXTURES)
    def test_sync_search_survives_byte_by_byte_feed(self):
        name = "tone_a4_8000_mono_16cbr.mp3"
        small, _ = _decode_file(name, 1)
        whole, _ = _decode_file(name, 1 << 20)
        self.assertEqual(small, whole)


class TestMP3Reset(unittest.TestCase):

    @unittest.skipIf(not _HAVE_FIXTURES, _NO_FIXTURES)
    def test_reset_replays_same_audio(self):
        name = "tone_a4_8000_mono_16cbr.mp3"
        with open(FIXTURES + "/" + name, "rb") as f:
            data = f.read()
        decoder = mp3dec.Decoder()
        try:
            first = _decode_stream(decoder, data, 4096)
            self.assertTrue(len(first) > 0)
            decoder.reset()
            second = _decode_stream(decoder, data, 4096)
        finally:
            decoder.close()
        self.assertEqual(first, second)
