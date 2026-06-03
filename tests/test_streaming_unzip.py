import os
import shutil
import unittest

from mpos.content.streaming_unzip import StreamingUnzip, peek_strip_prefix


class TestStreamingUnzip(unittest.TestCase):

    DEST = "tmp_streaming_unzip"

    def setUp(self):
        self._rm(self.DEST)

    def tearDown(self):
        self._rm(self.DEST)

    def _rm(self, path):
        try:
            st = os.stat(path)
        except OSError:
            return
        if st[0] & 0x4000:
            shutil.rmtree(path)
        else:
            os.remove(path)

    def _assert_dir(self, path):
        st = os.stat(path)
        self.assertTrue(st[0] & 0x4000)

    def _assert_file_size(self, path, expected_size):
        st = os.stat(path)
        self.assertTrue(st[0] & 0x8000)
        self.assertEqual(st[6], expected_size)

    def _assert_app_tree(self, dest):
        self._assert_dir(dest)
        self._assert_dir(f"{dest}/assets")
        self._assert_dir(f"{dest}/META-INF")
        self._assert_dir(f"{dest}/res")
        self._assert_dir(f"{dest}/res/mipmap-mdpi")
        self._assert_file_size(
            f"{dest}/assets/hello.py",
            232,
        )
        self._assert_file_size(
            f"{dest}/META-INF/MANIFEST.JSON",
            406,
        )
        self._assert_file_size(
            f"{dest}/res/mipmap-mdpi/icon_64x64.png",
            5499,
        )

    def test_extracts_uncompressed(self):
        source_mpk = "../tests/com.micropythonos.ziptest_Xr0.mpk"
        with open(source_mpk, "rb") as f:
            data = f.read()

        # Feed in small chunks (simulating network download)
        extractor = StreamingUnzip(self.DEST)
        chunk_size = 512
        for i in range(0, len(data), chunk_size):
            extractor.feed(data[i:i + chunk_size])
        extractor.finish()

        # The zip has no top-level directory, but it should strip nothing
        self._assert_app_tree(self.DEST)

    def test_extracts_deflated(self):
        source_mpk = "../tests/com.micropythonos.ziptest_r.mpk"
        with open(source_mpk, "rb") as f:
            data = f.read()

        extractor = StreamingUnzip(self.DEST)
        chunk_size = 1024
        for i in range(0, len(data), chunk_size):
            extractor.feed(data[i:i + chunk_size])
        extractor.finish()

        self._assert_app_tree(self.DEST)

    def test_extracts_with_topdir(self):
        source_mpk = "../tests/com.micropythonos.ziptest_topdir.mpk"
        with open(source_mpk, "rb") as f:
            data = f.read()

        # peek_strip_prefix only needs the first few hundred bytes
        prefix = peek_strip_prefix(data, "com.micropythonos.ziptest")
        self.assertEqual(prefix, "com.micropythonos.ziptest/")

        extractor = StreamingUnzip(self.DEST, strip_prefix=prefix)
        for i in range(0, len(data), 713):
            extractor.feed(data[i:i + 713])
        extractor.finish()

        self._assert_app_tree(self.DEST)

    def test_rejects_invalid_topdir(self):
        source_mpk = "../tests/com.micropythonos.ziptest_invalid_topdir.mpk"
        with open(source_mpk, "rb") as f:
            data = f.read()

        with self.assertRaises(ValueError):
            peek_strip_prefix(data, "com.micropythonos.ziptest")

    def test_deflated_with_tiny_chunks(self):
        source_mpk = "../tests/com.micropythonos.ziptest_r.mpk"
        with open(source_mpk, "rb") as f:
            data = f.read()

        # Feed single-byte chunks to stress the state machine
        extractor = StreamingUnzip(self.DEST)
        for b in data:
            extractor.feed(bytes([b]))
        extractor.finish()

        self._assert_app_tree(self.DEST)


class TestPeekStripPrefix(unittest.TestCase):

    def test_no_strip(self):
        with open("../tests/com.micropythonos.ziptest_Xr0.mpk", "rb") as f:
            data = f.read(1024)
        prefix = peek_strip_prefix(data, "com.micropythonos.ziptest")
        self.assertEqual(prefix, "")

    def test_strip_expected(self):
        with open("../tests/com.micropythonos.ziptest_topdir.mpk", "rb") as f:
            data = f.read(1024)
        prefix = peek_strip_prefix(data, "com.micropythonos.ziptest")
        self.assertEqual(prefix, "com.micropythonos.ziptest/")

    def test_mismatch(self):
        with open("../tests/com.micropythonos.ziptest_invalid_topdir.mpk", "rb") as f:
            data = f.read(1024)
        with self.assertRaises(ValueError):
            peek_strip_prefix(data, "com.micropythonos.ziptest")


if __name__ == "__main__":
    unittest.main()
