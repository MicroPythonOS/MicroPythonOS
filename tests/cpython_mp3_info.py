#!/usr/bin/env python3
"""CPython tests for the pure-Python MP3 header parser (mpos/audio/mp3.py).

AudioManager needs the sample rate before it opens I2S, and the music player
shows a duration, so get_info() has to work without the native decoder. These
tests load the module standalone (no MicroPython runtime) and compare the five
fixtures in tests/data/mp3/ against ffprobe values. The fixtures cover MPEG-1,
MPEG-2 and MPEG-2.5, CBR and VBR (Xing), mono and stereo.

Usage:
    python3 tests/cpython_mp3_info.py
"""

import importlib.util
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MP3_MODULE = os.path.join(
    HERE, "..", "internal_filesystem", "lib", "mpos", "audio", "mp3.py"
)
FIXTURES = os.path.join(HERE, "data", "mp3")

_spec = importlib.util.spec_from_file_location("mpos_mp3", MP3_MODULE)
mp3 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mp3)

# name: (sample rate, channels, kbps, duration_ms, vbr, xing frames)
ASSETS = {
    "tone_a4a5a6_44100_stereo_128cbr.mp3": (44100, 2, 128, 3996, False, None),
    "tone_a4a5a6_44100_stereo_vbr.mp3": (44100, 2, 36, 3996, True, 153),
    "tone_a4_22050_mono_64cbr.mp3": (22050, 1, 63, 1567, False, 60),
    "tone_a4_8000_mono_16cbr.mp3": (8000, 1, 16, 1656, False, 23),
    "tone_a4_48000_stereo_320cbr.mp3": (48000, 2, 320, 744, False, 31),
}

ID3_SIZE = 45


def _header(version_bits, bitrate_index, rate_index, padding, mono):
    """Build a 4-byte MPEG Layer III frame header."""
    byte1 = 0xFF
    byte2 = 0xE0 | (version_bits << 3) | (0x01 << 1) | 0x01
    byte3 = (bitrate_index << 4) | (rate_index << 2) | (padding << 1)
    byte4 = 0xC0 if mono else 0x00
    return bytes((byte1, byte2, byte3, byte4))


class TestID3(unittest.TestCase):

    def test_absent(self):
        self.assertEqual(mp3._id3v2_size(b""), 0)
        self.assertEqual(mp3._id3v2_size(b"ID3"), 0)
        self.assertEqual(mp3._id3v2_size(b"RIFF" + b"\x00" * 20), 0)

    def test_plain_tag(self):
        header = b"ID3\x03\x00\x00" + bytes((0, 0, 0x01, 0x00))
        self.assertEqual(mp3._id3v2_size(header), 10 + 128)

    def test_synchsafe_size(self):
        header = b"ID3\x04\x00\x00" + bytes((0x7F, 0x7F, 0x7F, 0x7F))
        self.assertEqual(mp3._id3v2_size(header), 10 + 0x0FFFFFFF)

    def test_footer(self):
        header = b"ID3\x04\x00\x10" + bytes((0, 0, 0x00, 0x40))
        self.assertEqual(mp3._id3v2_size(header), 10 + 64 + 10)


class TestParseHeader(unittest.TestCase):

    def test_mpeg1_stereo(self):
        info = mp3._parse_header(_header(3, 9, 0, 0, False), 0)
        self.assertEqual(info["version_bits"], 3)
        self.assertEqual(info["sample_rate"], 44100)
        self.assertEqual(info["channels"], 2)
        self.assertEqual(info["bitrate_kbps"], 128)
        self.assertEqual(info["samples_per_frame"], 1152)
        self.assertEqual(info["frame_bytes"], 417)

    def test_mpeg1_padding(self):
        info = mp3._parse_header(_header(3, 9, 0, 1, False), 0)
        self.assertEqual(info["frame_bytes"], 418)

    def test_mpeg2_mono(self):
        info = mp3._parse_header(_header(2, 8, 0, 0, True), 0)
        self.assertEqual(info["version_bits"], 2)
        self.assertEqual(info["sample_rate"], 22050)
        self.assertEqual(info["channels"], 1)
        self.assertEqual(info["bitrate_kbps"], 64)
        self.assertEqual(info["samples_per_frame"], 576)

    def test_mpeg25_mono(self):
        info = mp3._parse_header(_header(0, 2, 2, 0, True), 0)
        self.assertEqual(info["version_bits"], 0)
        self.assertEqual(info["sample_rate"], 8000)
        self.assertEqual(info["channels"], 1)
        self.assertEqual(info["bitrate_kbps"], 16)
        self.assertEqual(info["frame_bytes"], 144)

    def test_reserved_version(self):
        self.assertIsNone(mp3._parse_header(_header(1, 9, 0, 0, False), 0))

    def test_not_layer3(self):
        header = bytearray(_header(3, 9, 0, 0, False))
        header[1] = (header[1] & 0xF9) | 0x04  # layer II
        self.assertIsNone(mp3._parse_header(bytes(header), 0))

    def test_bad_bitrate_and_rate(self):
        self.assertIsNone(mp3._parse_header(_header(3, 15, 0, 0, False), 0))
        self.assertIsNone(mp3._parse_header(_header(3, 0, 0, 0, False), 0))
        self.assertIsNone(mp3._parse_header(_header(3, 9, 3, 0, False), 0))

    def test_bad_sync(self):
        self.assertIsNone(mp3._parse_header(b"\xfe\xfb\x90\x00", 0))
        self.assertIsNone(mp3._parse_header(b"\xff\xdb\x90\x00", 0))

    def test_short_buffer(self):
        self.assertIsNone(mp3._parse_header(b"\xff\xfb", 0))
        self.assertIsNone(mp3._parse_header(b"\xff\xfb\x90\x00", 99))


class TestFindFrame(unittest.TestCase):

    def _two_frames(self):
        first = _header(3, 9, 0, 0, False) + b"\x00" * 413
        second = _header(3, 9, 0, 0, False) + b"\x00" * 413
        return first, second

    def test_skips_junk(self):
        first, second = self._two_frames()
        offset, info = mp3._find_frame(b"\x00\x01\x02" + first + second)
        self.assertEqual(offset, 3)
        self.assertEqual(info["sample_rate"], 44100)

    def test_rejects_false_sync(self):
        first, second = self._two_frames()
        junk = _header(3, 9, 0, 0, False) + b"\x00" * 20
        offset, info = mp3._find_frame(junk + first + second)
        self.assertEqual(offset, len(junk))

    def test_single_frame_is_accepted(self):
        first, _ = self._two_frames()
        offset, info = mp3._find_frame(first)
        self.assertEqual(offset, 0)
        self.assertIsNotNone(info)

    def test_no_frame(self):
        offset, info = mp3._find_frame(b"\x00" * 1000)
        self.assertIsNone(offset)
        self.assertIsNone(info)


class TestGetInfo(unittest.TestCase):

    def test_assets_match_ffprobe(self):
        for name, expected in sorted(ASSETS.items()):
            rate, channels, kbps, duration_ms, vbr, xing_frames = expected
            info = mp3.get_info(os.path.join(FIXTURES, name))
            self.assertEqual(info["sample_rate"], rate, name)
            self.assertEqual(info["channels"], channels, name)
            self.assertEqual(info["bitrate_kbps"], kbps, name)
            self.assertEqual(info["duration_ms"], duration_ms, name)
            self.assertEqual(info["vbr"], vbr, name)
            self.assertEqual(info["xing_frames"], xing_frames, name)
            self.assertEqual(info["id3_size"], ID3_SIZE, name)
            self.assertEqual(info["audio_offset"], info["id3_size"], name)

    def test_total_samples(self):
        for name in ASSETS:
            info = mp3.get_info(os.path.join(FIXTURES, name))
            self.assertEqual(
                info["total_samples"],
                info["duration_ms"] * info["sample_rate"] // 1000,
                name,
            )

    def test_file_size(self):
        for name in ASSETS:
            info = mp3.get_info(os.path.join(FIXTURES, name))
            self.assertEqual(
                info["file_size"], os.path.getsize(os.path.join(FIXTURES, name))
            )

    def test_id3v1_trailer_is_excluded(self):
        name = "tone_a4a5a6_44100_stereo_128cbr.mp3"
        source = os.path.join(FIXTURES, name)
        base = mp3.get_info(source)["duration_ms"]
        tempdir = tempfile.mkdtemp()
        try:
            tagged = os.path.join(tempdir, "tagged.mp3")
            shutil.copyfile(source, tagged)
            with open(tagged, "ab") as f:
                f.write(b"TAG" + b"\x00" * 125)
            self.assertEqual(mp3.get_info(tagged)["duration_ms"], base)

            garbage = os.path.join(tempdir, "garbage.mp3")
            shutil.copyfile(source, garbage)
            with open(garbage, "ab") as f:
                f.write(b"\x00" * 128)
            self.assertEqual(mp3.get_info(garbage)["duration_ms"], base + 8)
        finally:
            shutil.rmtree(tempdir)

    def test_garbage_file_raises(self):
        tempdir = tempfile.mkdtemp()
        try:
            path = os.path.join(tempdir, "not-an-mp3.mp3")
            with open(path, "wb") as f:
                f.write(b"\x00\x01\x02\x03" * 64)
            with self.assertRaises(ValueError):
                mp3.get_info(path)
        finally:
            shutil.rmtree(tempdir)


if __name__ == "__main__":
    unittest.main()
