"""littlefs2e extent files, on hardware.

Run with the usual device runner (desktop skips: the lfs2e module is a
firmware user C module). Uses the generic (block-aligned) extent path; the
64 KiB XIP alignment is exercised by the Doom launcher and the C suite's
test_extent.toml.
"""

import os
import sys
import unittest

import mpos.extent as extent


@unittest.skipUnless(
    sys.platform == "esp32" and extent.available(),
    "littlefs2e is only available on ESP32 firmware",
)
class ExtentFileTest(unittest.TestCase):
    PATH = "/extent-test.bin"

    def tearDown(self):
        try:
            os.remove(self.PATH)
        except OSError:
            pass

    def _write(self, data):
        with open(self.PATH, "wb") as f:
            f.write(data)

    def test_create_read_and_convert_back(self):
        data = bytes((i * 7) & 0xFF for i in range(20000))
        self._write(data)
        offset, length, crc = extent.ensure(self.PATH)
        self.assertEqual(length, len(data))
        self.assertEqual(offset % extent.geometry()[0], 0)
        self.assertNotEqual(crc, 0)
        self.assertEqual(extent.info(self.PATH), (offset, length, crc))

        # The extent is readable through the ordinary file API.
        with open(self.PATH, "rb") as f:
            self.assertEqual(f.read(), data)

        # A normal write replaces the extent with ordinary file data.
        self._write(b"small")
        self.assertIsNone(extent.info(self.PATH))
        with open(self.PATH, "rb") as f:
            self.assertEqual(f.read(), b"small")

    def test_remove_frees_the_run(self):
        self._write(b"x" * 12000)
        extent.ensure(self.PATH)
        self.assertIsNotNone(extent.info(self.PATH))
        os.remove(self.PATH)
        self.assertIsNone(extent.info(self.PATH))


if __name__ == "__main__":
    unittest.main()
