import io
import os
import sys
import unittest

sys.path.insert(0, "apps/com.micropythonos.video_player")

import video_engine


def make_jpeg(width, height, payload=b"payload", sof=True):
    out = bytearray(b"\xff\xd8")
    out += b"\xff\xe0" + bytes([0, 16]) + b"JFIF\x00" + bytes(9)
    if sof:
        # SOF0: length, precision, height, width, components
        out += b"\xff\xc0" + bytes([0, 11, 8, height >> 8, height & 255,
                                    width >> 8, width & 255, 3])
        out += b"\x01\x11\x00\x02\x11\x00\x03\x11\x00"
    out += b"\xff\xda" + bytes([0, 8]) + b"\x01\x01\x00\x00\x3f\x00"
    out += payload
    out += b"\xff\xd9"
    return bytes(out)


class TestJpegDimensions(unittest.TestCase):
    def test_reads_sof_dimensions(self):
        frame = make_jpeg(320, 240)
        self.assertEqual(video_engine.jpeg_dimensions(frame), (320, 240))

    def test_reads_other_sizes(self):
        for w, h in ((160, 120), (240, 180), (1, 1), (640, 480)):
            self.assertEqual(video_engine.jpeg_dimensions(make_jpeg(w, h)), (w, h))

    def test_returns_none_without_sof(self):
        self.assertEqual(video_engine.jpeg_dimensions(make_jpeg(10, 10, sof=False)),
                         (None, None))

    def test_returns_none_on_short_input(self):
        self.assertEqual(video_engine.jpeg_dimensions(b"\xff\xd8"), (None, None))


class TestFpsFromName(unittest.TestCase):
    def test_parses_common_names(self):
        self.assertEqual(video_engine.fps_from_name("ruler_320x240_15fps.mjpeg"), 15)
        self.assertEqual(video_engine.fps_from_name("/sdcard/clips/a_30fps.mjpeg"), 30)
        self.assertEqual(video_engine.fps_from_name("x_8FPS.MJPG"), 8)

    def test_rejects_missing_or_bad_values(self):
        self.assertIsNone(video_engine.fps_from_name("clip.mjpeg"))
        self.assertIsNone(video_engine.fps_from_name("clip_fps.mjpeg"))
        self.assertIsNone(video_engine.fps_from_name("clip_0fps.mjpeg"))
        self.assertIsNone(video_engine.fps_from_name("clip_500fps.mjpeg"))


class TestMjpegReader(unittest.TestCase):
    def _stream(self, sizes):
        frames = []
        for i, size in enumerate(sizes):
            # No SOI/EOI sequences inside the payload.
            frames.append(make_jpeg(16, 16, payload=bytes([0x40 + i]) * size))
        return b"".join(frames), frames

    def _read_all(self, reader):
        out = []
        while True:
            frame = reader.next()
            if frame is None:
                break
            out.append(bytes(frame))
        return out

    def test_splits_frames_from_one_buffer(self):
        data, frames = self._stream([40, 120, 70])
        reader = video_engine.MjpegReader(io.BytesIO(data), chunk=4096, cap=4096)
        self.assertEqual(self._read_all(reader), frames)
        self.assertEqual(reader.frames, 3)
        self.assertIsNone(reader.error)

    def test_splits_frames_across_small_refills(self):
        # Frames are larger than the chunk and the capacity forces several
        # compactions while one frame is being assembled.
        data, frames = self._stream([100, 30, 200, 90])
        reader = video_engine.MjpegReader(io.BytesIO(data), chunk=16, cap=256)
        self.assertEqual(self._read_all(reader), frames)
        self.assertEqual(reader.frames, 4)
        self.assertIsNone(reader.error)

    def test_rewind_replays_the_stream(self):
        data, frames = self._stream([50, 60])
        reader = video_engine.MjpegReader(io.BytesIO(data), chunk=32, cap=128)
        self.assertEqual(len(self._read_all(reader)), 2)
        self.assertTrue(reader.rewind())
        self.assertEqual(self._read_all(reader), frames)

    def test_frame_starting_near_buffer_end_is_not_dropped(self):
        # A full buffer does not mean the frame is too big: the next frame can
        # start a few bytes before the end and still fit after compaction.
        data, frames = self._stream([200, 5])
        reader = video_engine.MjpegReader(io.BytesIO(data), chunk=16, cap=256)
        self.assertEqual(self._read_all(reader), frames)
        self.assertIsNone(reader.error)

    def test_oversized_frame_is_skipped_and_stream_resyncs(self):
        data, frames = self._stream([206, 5])
        reader = video_engine.MjpegReader(io.BytesIO(data), chunk=16, cap=256)
        self.assertEqual(self._read_all(reader), frames[1:])
        self.assertEqual(reader.error, "frame exceeds buffer")

    def test_trailing_partial_frame_is_ignored(self):
        data, frames = self._stream([50, 60])
        reader = video_engine.MjpegReader(io.BytesIO(data + b"\xff\xd8\x00\x01"),
                                          chunk=32, cap=128)
        self.assertEqual(self._read_all(reader), frames)

    def test_skip_seeks_past_frames_and_resyncs(self):
        # Equal frame sizes: the average is exact, so skipping two frames lands
        # on the next one after the current position.
        data, frames = self._stream([40, 40, 40, 40, 40, 40])
        reader = video_engine.MjpegReader(io.BytesIO(data), chunk=32, cap=128)
        for _ in range(2):
            self.assertIsNotNone(reader.next())
        self.assertTrue(reader.skip(2))
        self.assertEqual(bytes(reader.next()), frames[4])
        self.assertEqual(reader.skipped, 2)

    def test_skip_resyncs_when_average_is_wrong(self):
        data, frames = self._stream([40, 40, 200, 40, 40, 40])
        reader = video_engine.MjpegReader(io.BytesIO(data), chunk=32, cap=512)
        for _ in range(2):
            self.assertIsNotNone(reader.next())
        # The average lands inside the large frame; the next call must resync on
        # a real SOI instead of returning garbage.
        self.assertTrue(reader.skip(2))
        frame = bytes(reader.next())
        self.assertTrue(frame.startswith(b"\xff\xd8"))
        self.assertTrue(frame.endswith(b"\xff\xd9"))
        self.assertIn(frame, frames)

    def test_skip_past_the_end_returns_no_frame(self):
        data, _ = self._stream([40, 40])
        reader = video_engine.MjpegReader(io.BytesIO(data), chunk=32, cap=128)
        reader.next()
        reader.skip(50)
        self.assertIsNone(reader.next())

    def test_skip_is_refused_without_frame_size_or_seek(self):
        data, _ = self._stream([40, 40])
        reader = video_engine.MjpegReader(io.BytesIO(data), chunk=32, cap=128)
        # No frame read yet, so there is no average to seek by.
        self.assertFalse(reader.skip(2))

        class NoSeek:
            def __init__(self, payload):
                self._bio = io.BytesIO(payload)

            def readinto(self, buf):
                return self._bio.readinto(buf)

            def tell(self):
                raise OSError("not seekable")

            def seek(self, *args):
                raise OSError("not seekable")

        reader = video_engine.MjpegReader(NoSeek(data), chunk=32, cap=128)
        self.assertIsNotNone(reader.next())
        self.assertFalse(reader.skip(2))

    def test_single_frame_skip_is_read_instead_of_seeked(self):
        # The resync read after a seek pulls in about a frame, so dropping one
        # frame is cheaper by reading it.
        data, _ = self._stream([40, 40, 40])
        reader = video_engine.MjpegReader(io.BytesIO(data), chunk=32, cap=128)
        reader.next()
        self.assertFalse(reader.skip(1))
        self.assertEqual(reader.skipped, 0)


class TestPacer(unittest.TestCase):
    def test_advances_on_schedule(self):
        pacer = video_engine.Pacer(15, 1000)
        self.assertEqual(pacer.due_ms(), 1000)
        self.assertEqual(pacer.wait_ms(1000), 0)
        self.assertEqual(pacer.wait_ms(960), 40)
        self.assertEqual(pacer.mark_shown(1000), 0)
        self.assertEqual(pacer.due_ms(), 1066)
        self.assertEqual(pacer.mark_shown(1066), 0)

    def test_skips_frames_when_late(self):
        pacer = video_engine.Pacer(15, 0)
        pacer.mark_shown(0)
        # 167 ms late at 15 fps: two whole 66 ms intervals have gone by.
        self.assertEqual(pacer.mark_shown(300), 2)
        self.assertEqual(pacer.frame, 4)
        self.assertEqual(pacer.due_ms(), 266)

    def test_no_skip_when_not_late(self):
        pacer = video_engine.Pacer(15, 0)
        self.assertEqual(pacer.mark_shown(10), 0)
        self.assertEqual(pacer.frame, 1)

    def test_drop_can_be_disabled(self):
        pacer = video_engine.Pacer(15, 0, drop=False)
        self.assertEqual(pacer.mark_shown(1000), 0)
        self.assertEqual(pacer.frame, 1)

    def test_zero_fps_falls_back(self):
        pacer = video_engine.Pacer(0, 0)
        self.assertEqual(pacer.fps, 15)


class TestSniffFormat(unittest.TestCase):
    def _write(self, data, name="data/sniff.bin"):
        try:
            os.mkdir("data")
        except OSError:
            pass
        with open(name, "wb") as handle:
            handle.write(data)
        return name

    def test_names_an_mp4(self):
        path = self._write(b"\x00\x00\x00\x20ftypisom" + bytes(8))
        self.assertEqual(video_engine.sniff_format(path), "an MP4/MOV file")
        os.remove(path)

    def test_names_matroska_and_avi(self):
        path = self._write(b"\x1aE\xdf\xa3" + bytes(12))
        self.assertEqual(video_engine.sniff_format(path), "a Matroska/WebM file")
        os.remove(path)
        path = self._write(b"RIFF\x10\x00\x00\x00AVI " + bytes(4))
        self.assertEqual(video_engine.sniff_format(path), "a RIFF file (AVI or WAV)")
        os.remove(path)

    def test_recognises_mjpeg(self):
        path = self._write(b"\xff\xd8\xff\xe0" + bytes(12))
        self.assertEqual(video_engine.sniff_format(path), "a JPEG image or MJPEG stream")
        os.remove(path)

    def test_unknown_bytes_say_nothing(self):
        path = self._write(b"nonsense data here")
        self.assertIsNone(video_engine.sniff_format(path))
        os.remove(path)

    def test_reading_a_file_object_keeps_its_position(self):
        stream = io.BytesIO(b"\x00\x00\x00\x20ftypisom" + bytes(8))
        stream.seek(2)
        self.assertEqual(video_engine.sniff_format(stream), "an MP4/MOV file")
        self.assertEqual(stream.tell(), 2)


if __name__ == "__main__":
    unittest.main()
