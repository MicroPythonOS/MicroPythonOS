# Unit tests for the BMP encoder behind save_screenshot_bmp()
import struct
import sys
import unittest

sys.path.insert(0, "lib")
from mpos.ui.testing import encode_bmp

HEADER_SIZE = 54


def make_pixels(width, height):
    """Build an LVGL RGB888 buffer (blue, green, red per pixel)."""
    buf = bytearray(width * height * 3)
    for y in range(height):
        for x in range(width):
            i = (y * width + x) * 3
            buf[i] = x * 3          # blue
            buf[i + 1] = y * 5      # green
            buf[i + 2] = 200 - x    # red
    return buf


class TestEncodeBmp(unittest.TestCase):

    def test_header_describes_the_image(self):
        width, height = 8, 3
        bmp = encode_bmp(make_pixels(width, height), width, height)
        self.assertEqual(bmp[0:2], b"BM")
        self.assertEqual(struct.unpack("<I", bmp[2:6])[0], len(bmp))
        self.assertEqual(struct.unpack("<I", bmp[10:14])[0], HEADER_SIZE)
        self.assertEqual(struct.unpack("<I", bmp[14:18])[0], 40)
        self.assertEqual(struct.unpack("<I", bmp[18:22])[0], width)
        self.assertEqual(struct.unpack("<i", bmp[22:26])[0], -height)  # top-down
        self.assertEqual(struct.unpack("<H", bmp[26:28])[0], 1)
        self.assertEqual(struct.unpack("<H", bmp[28:30])[0], 24)
        self.assertEqual(struct.unpack("<I", bmp[34:38])[0], len(bmp) - HEADER_SIZE)

    def test_rows_are_copied_when_they_need_no_padding(self):
        width, height = 8, 3  # 24 bytes per row, already a multiple of 4
        pixels = make_pixels(width, height)
        bmp = encode_bmp(pixels, width, height)
        self.assertEqual(len(bmp), HEADER_SIZE + width * height * 3)
        self.assertEqual(bytes(bmp[HEADER_SIZE:]), bytes(pixels))

    def test_rows_are_padded_to_four_bytes(self):
        width, height = 3, 2  # 9 bytes per row, padded to 12
        pixels = make_pixels(width, height)
        bmp = encode_bmp(pixels, width, height)
        stride = 12
        self.assertEqual(len(bmp), HEADER_SIZE + stride * height)
        for y in range(height):
            row = bmp[HEADER_SIZE + y * stride:HEADER_SIZE + (y + 1) * stride]
            self.assertEqual(bytes(row[:width * 3]), bytes(pixels[y * width * 3:(y + 1) * width * 3]))
            self.assertEqual(bytes(row[width * 3:]), b"\x00" * (stride - width * 3))

    def test_a_screen_sized_image_has_the_expected_size(self):
        width, height = 320, 240
        bmp = encode_bmp(bytearray(width * height * 3), width, height)
        self.assertEqual(len(bmp), HEADER_SIZE + width * height * 3)


if __name__ == "__main__":
    unittest.main()
