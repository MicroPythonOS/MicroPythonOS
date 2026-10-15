"""Tests for the qrdecode C module (c_mpos/src/quirc_decode.c).

The fixtures in tests/qrdecode/ are small camera-like grayscale frames
(binary PGM): square finder patterns, slight rotation, blur, noise and uneven
lighting. They were rendered with segno + OpenCV.

The module keeps one decoder between calls (resized when the frame size
changes) until qrdecode.release(), so these tests also check that frame size
changes, errors and release() leave it in a usable state.
"""

import gc
import unittest

import qrdecode

FIXTURES = "../tests/qrdecode"

# ESP-IDF heap capability bits (esp_heap_caps.h)
_MALLOC_CAP_8BIT = 1 << 2
_MALLOC_CAP_SPIRAM = 1 << 10
_MALLOC_CAP_INTERNAL = 1 << 11

try:
    import esp32

    _HAS_PSRAM = bool(esp32.idf_heap_info(_MALLOC_CAP_SPIRAM))
except ImportError:
    esp32 = None
    _HAS_PSRAM = False

V2_PAYLOAD = b"https://micropythonos.com"
V1_PAYLOAD = b"MicroPythonOS"


def _read_pgm(name):
    with open(FIXTURES + "/" + name, "rb") as f:
        data = f.read()
    magic, size, maxval, pixels = data.split(b"\n", 3)
    width, height = [int(v) for v in size.decode().split()]
    if magic != b"P5" or maxval != b"255" or len(pixels) != width * height:
        raise ValueError("unexpected PGM header in " + name)
    return pixels, width, height


# test_runner.py --ondevice doesn't copy tests/qrdecode to the device. The fixture
# tests are skipped with a decorator, not from setUp: the device's unittest
# doesn't catch a SkipTest raised in setUp, and it would end the whole run.
try:
    _V2 = _read_pgm("v2_url_120x120.pgm")
    _V1 = _read_pgm("v1_text_96x80.pgm")
    _HAS_FIXTURES = True
except OSError:
    _HAS_FIXTURES = False
_NO_FIXTURES = "fixtures in " + FIXTURES + " are not available"


def _no_code_frame(width, height):
    return bytes((2 * x + 3 * y) & 0xFF for y in range(height) for x in range(width))


def _unreadable_frame(frame, width):
    # Blank out the middle of the V2 code: the three finder patterns are
    # still found, but too many data modules are lost to correct.
    corrupt = bytearray(frame)
    for y in range(52, 81):
        corrupt[y * width + 46:y * width + 75] = b"\xc8" * 29
    return corrupt


def _to_rgb565(gray):
    out = bytearray(2 * len(gray))
    for i, g in enumerate(gray):
        value = ((g >> 3) << 11) | ((g >> 2) << 5) | (g >> 3)
        out[2 * i] = value & 0xFF
        out[2 * i + 1] = value >> 8
    return out


class TestQRDecode(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if _HAS_FIXTURES:
            cls.v2, cls.v2_w, cls.v2_h = _V2
            cls.v1, cls.v1_w, cls.v1_h = _V1

    @classmethod
    def tearDownClass(cls):
        # Don't leave the decoder allocated for the tests that run after these.
        qrdecode.release()

    @unittest.skipUnless(_HAS_FIXTURES, _NO_FIXTURES)
    def test_decodes_square_finder_code(self):
        self.assertEqual(qrdecode.qrdecode(self.v2, self.v2_w, self.v2_h), V2_PAYLOAD)

    @unittest.skipUnless(_HAS_FIXTURES, _NO_FIXTURES)
    def test_decodes_non_square_frame(self):
        self.assertEqual((self.v1_w, self.v1_h), (96, 80))
        self.assertEqual(qrdecode.qrdecode(self.v1, self.v1_w, self.v1_h), V1_PAYLOAD)

    @unittest.skipUnless(_HAS_FIXTURES, _NO_FIXTURES)
    def test_decodes_memoryview(self):
        # The camera hands its frame buffer over as a memoryview.
        frame = memoryview(bytearray(self.v2))
        self.assertEqual(qrdecode.qrdecode(frame, self.v2_w, self.v2_h), V2_PAYLOAD)

    @unittest.skipUnless(_HAS_FIXTURES, _NO_FIXTURES)
    def test_decodes_offset_slice_without_touching_neighbours(self):
        padded = bytearray(b"\x00" * 3) + bytearray(self.v2) + bytearray(b"\xff" * 5)
        before = bytes(padded)
        frame = memoryview(padded)[3:3 + len(self.v2)]
        self.assertEqual(qrdecode.qrdecode(frame, self.v2_w, self.v2_h), V2_PAYLOAD)
        self.assertEqual(bytes(padded), before)

    @unittest.skipUnless(_HAS_FIXTURES, _NO_FIXTURES)
    def test_no_code_raises_value_error(self):
        with self.assertRaises(ValueError):
            qrdecode.qrdecode(_no_code_frame(64, 48), 64, 48)

    @unittest.skipUnless(_HAS_FIXTURES, _NO_FIXTURES)
    def test_unreadable_code_raises_type_error(self):
        with self.assertRaises(TypeError):
            qrdecode.qrdecode(_unreadable_frame(self.v2, self.v2_w), self.v2_w, self.v2_h)

    @unittest.skipUnless(_HAS_FIXTURES, _NO_FIXTURES)
    def test_frame_size_changes_between_calls(self):
        no_code = _no_code_frame(64, 48)
        for _ in range(2):
            self.assertEqual(qrdecode.qrdecode(self.v2, self.v2_w, self.v2_h), V2_PAYLOAD)
            self.assertEqual(qrdecode.qrdecode(self.v1, self.v1_w, self.v1_h), V1_PAYLOAD)
            with self.assertRaises(ValueError):
                qrdecode.qrdecode(no_code, 64, 48)
        self.assertEqual(qrdecode.qrdecode(self.v1, self.v1_w, self.v1_h), V1_PAYLOAD)

    @unittest.skipUnless(_HAS_FIXTURES, _NO_FIXTURES)
    def test_input_buffer_is_not_modified(self):
        for frame, w, h in (
            (bytearray(self.v2), self.v2_w, self.v2_h),
            (_unreadable_frame(self.v2, self.v2_w), self.v2_w, self.v2_h),
            (bytearray(_no_code_frame(64, 48)), 64, 48),
        ):
            before = bytes(frame)
            try:
                qrdecode.qrdecode(frame, w, h)
            except (ValueError, TypeError):
                pass
            self.assertEqual(bytes(frame), before)

    @unittest.skipUnless(_HAS_FIXTURES, _NO_FIXTURES)
    def test_bad_arguments_leave_decoder_usable(self):
        self.assertEqual(qrdecode.qrdecode(self.v2, self.v2_w, self.v2_h), V2_PAYLOAD)
        with self.assertRaises(ValueError):
            qrdecode.qrdecode(self.v2, self.v2_w, self.v2_h - 1)
        with self.assertRaises(ValueError):
            qrdecode.qrdecode(self.v2, 0, self.v2_h)
        with self.assertRaises(ValueError):
            qrdecode.qrdecode_rgb565(self.v2, self.v2_w, self.v2_h)
        self.assertEqual(qrdecode.qrdecode(self.v2, self.v2_w, self.v2_h), V2_PAYLOAD)

    @unittest.skipUnless(_HAS_FIXTURES, _NO_FIXTURES)
    def test_release_frees_decoder_and_next_call_reallocates(self):
        qrdecode.release()
        qrdecode.release()
        self.assertEqual(qrdecode.qrdecode(self.v2, self.v2_w, self.v2_h), V2_PAYLOAD)
        qrdecode.release()
        self.assertEqual(qrdecode.qrdecode(self.v1, self.v1_w, self.v1_h), V1_PAYLOAD)
        qrdecode.release()
        qrdecode.release()

    @unittest.skipUnless(_HAS_FIXTURES, _NO_FIXTURES)
    def test_rgb565_decodes_same_payload(self):
        frame = _to_rgb565(self.v2)
        before = bytes(frame)
        self.assertEqual(qrdecode.qrdecode_rgb565(frame, self.v2_w, self.v2_h), V2_PAYLOAD)
        self.assertEqual(bytes(frame), before)
        self.assertEqual(qrdecode.qrdecode_rgb565(_to_rgb565(self.v1), self.v1_w, self.v1_h), V1_PAYLOAD)

    @unittest.skipUnless(_HAS_FIXTURES, _NO_FIXTURES)
    def test_rgb565_errors_are_caught_by_the_caller(self):
        # The exception must reach this frame's except clause, not one further out.
        caught = []
        try:
            qrdecode.qrdecode_rgb565(_to_rgb565(_no_code_frame(64, 48)), 64, 48)
        except ValueError:
            caught.append("ValueError")
        try:
            qrdecode.qrdecode_rgb565(_to_rgb565(_unreadable_frame(self.v2, self.v2_w)), self.v2_w, self.v2_h)
        except TypeError:
            caught.append("TypeError")
        self.assertEqual(caught, ["ValueError", "TypeError"])
        self.assertEqual(qrdecode.qrdecode_rgb565(_to_rgb565(self.v2), self.v2_w, self.v2_h), V2_PAYLOAD)


class TestQRDecodeFrameSize(unittest.TestCase):
    """Frame sizes whose pixel count overflows are rejected before anything is allocated.

    With 32-bit arithmetic (ESP32), 65536 x 65537 wraps around to 65536 pixels:
    it used to pass the buffer size check and get a 64 KB buffer for 65537 rows.
    """

    def tearDown(self):
        qrdecode.release()

    def _value_error(self, func, *args):
        try:
            func(*args)
        except ValueError as e:
            return str(e)
        self.fail("no ValueError")

    def test_overflowing_size_raises_value_error(self):
        self.assertEqual(self._value_error(qrdecode.qrdecode, bytearray(65536), 65536, 65537), "frame too large")

    def test_overflowing_rgb565_size_raises_value_error(self):
        self.assertEqual(self._value_error(qrdecode.qrdecode_rgb565, bytearray(131072), 65536, 65537), "frame too large")

    def test_decoder_still_works_after_rejected_size(self):
        self._value_error(qrdecode.qrdecode, bytearray(65536), 65536, 65537)
        self.assertEqual(self._value_error(qrdecode.qrdecode, _no_code_frame(64, 48), 64, 48), "no QR code found")


class TestQRDecodeMemory(unittest.TestCase):
    """The decoder kept between frames lives in PSRAM, not in internal RAM.

    Internal RAM is scarce and shared with the display's DMA buffers and the
    camera driver, and the decoder is kept for as long as QR scanning is on.
    ESP32 with PSRAM only; skipped elsewhere.
    """

    def tearDown(self):
        qrdecode.release()

    def _free(self, caps):
        return sum(region[1] for region in esp32.idf_heap_info(caps))

    @unittest.skipUnless(_HAS_PSRAM, "needs an ESP32 with PSRAM")
    def test_kept_decoder_holds_no_internal_ram(self):
        width = height = 640  # the camera's QR mode
        frame = bytearray(width * height)
        internal = _MALLOC_CAP_8BIT | _MALLOC_CAP_INTERNAL
        held = []
        # Other tasks can allocate internal RAM at the same time, so take the smallest of three.
        for _ in range(3):
            qrdecode.release()
            gc.collect()
            internal_before = self._free(internal)
            spiram_before = self._free(_MALLOC_CAP_SPIRAM)
            with self.assertRaises(ValueError):
                qrdecode.qrdecode(frame, width, height)
            gc.collect()
            held.append((internal_before - self._free(internal), spiram_before - self._free(_MALLOC_CAP_SPIRAM)))
        internal_held = min(h[0] for h in held)
        spiram_held = min(h[1] for h in held)
        # The decoder is still allocated: its image buffer alone is width * height bytes
        self.assertTrue(spiram_held >= width * height, "decoder holds %d bytes of PSRAM" % spiram_held)
        # quirc's flood-fill stack alone would be 6,816 bytes at this height
        self.assertTrue(internal_held < 2048, "decoder holds %d bytes of internal RAM" % internal_held)


if __name__ == "__main__":
    unittest.main()
