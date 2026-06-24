import os
import shutil
import unittest

from mpos.content.streaming_unzip import StreamingUnzip


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

    def _assert_not_exists(self, path):
        try:
            os.stat(path)
            self.assertTrue(False)
        except OSError:
            pass

    def _assert_file_size(self, path, expected_size):
        st = os.stat(path)
        self.assertTrue(st[0] & 0x8000)
        self.assertEqual(st[6], expected_size)

    def _assert_app_tree_old(self, dest):
        self._assert_dir(dest)
        self._assert_dir(f"{dest}/assets")
        self._assert_dir(f"{dest}/META-INF")
        self._assert_dir(f"{dest}/res")
        self._assert_dir(f"{dest}/res/mipmap-mdpi")
        self._assert_file_size(f"{dest}/assets/hello.py", 232)
        self._assert_file_size(f"{dest}/META-INF/MANIFEST.JSON", 406)
        self._assert_file_size(f"{dest}/res/mipmap-mdpi/icon_64x64.png", 5499)

    def _assert_app_tree_flat(self, dest):
        self._assert_dir(dest)
        self._assert_dir(f"{dest}/assets")
        self._assert_file_size(f"{dest}/assets/hello.py", 232)
        self._assert_file_size(f"{dest}/MANIFEST.JSON", 406)
        self._assert_file_size(f"{dest}/icon_64x64.png", 5499)
        self._assert_not_exists(f"{dest}/META-INF")
        self._assert_not_exists(f"{dest}/res")
        self._assert_not_exists(f"{dest}/res/mipmap-mdpi")

    # ---- happy path (new flat layout) --------------------------------

    def test_extracts_flat_stored(self):
        """Well-formed flat (stored) MPK with the new layout."""
        with open("../tests/com.micropythonos.ziptest_flat_new.mpk", "rb") as f:
            data = f.read()

        extractor = StreamingUnzip(self.DEST, expected_app_name="com.micropythonos.ziptest")
        chunk_size = 512
        for i in range(0, len(data), chunk_size):
            extractor.feed(data[i:i + chunk_size])
        extractor.finish()

        self._assert_app_tree_flat(self.DEST)

    def test_extracts_flat_deflated(self):
        """Well-formed deflated MPK with the new layout."""
        with open("../tests/com.micropythonos.ziptest_flat_new_deflated.mpk", "rb") as f:
            data = f.read()

        extractor = StreamingUnzip(self.DEST, expected_app_name="com.micropythonos.ziptest")
        for i in range(0, len(data), 713):
            extractor.feed(data[i:i + 713])
        extractor.finish()

        self._assert_app_tree_flat(self.DEST)

    # ---- backward compatibility (old nested layout) -------------------

    def test_extracts_old_nested_stored(self):
        """Old nested-layout stored MPK still extracts correctly."""
        with open("../tests/com.micropythonos.ziptest_flat.mpk", "rb") as f:
            data = f.read()

        extractor = StreamingUnzip(self.DEST, expected_app_name="com.micropythonos.ziptest")
        chunk_size = 512
        for i in range(0, len(data), chunk_size):
            extractor.feed(data[i:i + chunk_size])
        extractor.finish()

        self._assert_app_tree_old(self.DEST)

    def test_extracts_old_nested_deflated(self):
        """Old nested-layout deflated MPK still extracts correctly."""
        with open("../tests/com.micropythonos.ziptest_flat_deflated.mpk", "rb") as f:
            data = f.read()

        extractor = StreamingUnzip(self.DEST, expected_app_name="com.micropythonos.ziptest")
        for i in range(0, len(data), 713):
            extractor.feed(data[i:i + 713])
        extractor.finish()

        self._assert_app_tree_old(self.DEST)

    def test_deflated_with_tiny_chunks(self):
        """Feed single-byte chunks to stress the state machine."""
        with open("../tests/com.micropythonos.ziptest_flat_new_deflated.mpk", "rb") as f:
            data = f.read()

        extractor = StreamingUnzip(self.DEST, expected_app_name="com.micropythonos.ziptest")
        for b in data:
            extractor.feed(bytes([b]))
        extractor.finish()

        self._assert_app_tree_flat(self.DEST)

    # ---- large-first order regression --------------------------------

    def test_extracts_largefirst(self):
        """Well-formed MPK with large first file."""
        with open("../tests/com.micropythonos.ziptest_flat_largefirst.mpk", "rb") as f:
            data = f.read()

        extractor = StreamingUnzip(self.DEST, expected_app_name="com.micropythonos.ziptest")
        for i in range(0, len(data), 1024):
            extractor.feed(data[i:i + 1024])
        extractor.finish()

        self._assert_dir(self.DEST)
        self._assert_dir(f"{self.DEST}/assets")
        self._assert_dir(f"{self.DEST}/META-INF")
        self._assert_dir(f"{self.DEST}/res")

    # ---- error path --------------------------------------------------

    def test_rejects_flat_no_topdir(self):
        """Package without a top-level dir is refused.

        Uses ``ziptest_largefirst.mpk`` whose first entry is a file.
        """
        with open("../tests/com.micropythonos.ziptest_largefirst.mpk", "rb") as f:
            data = f.read()

        extractor = StreamingUnzip(self.DEST, expected_app_name="com.micropythonos.ziptest")
        with self.assertRaises(RuntimeError) as ctx:
            for i in range(0, len(data), 512):
                extractor.feed(data[i:i + 512])
            extractor.finish()
        self.assertIn("not a directory", str(ctx.exception))

    def test_rejects_lightningpiggy_no_topdir(self):
        """Regression: badgehub old MPK whose first entry is assets/confetti.py.

        The original LightningPiggy 0.2.6 package has no top-level directory.
        A mis-selected download would hit this error; the extractor must still
        reject the malformed archive cleanly.
        """
        with open("../tests/com.lightningpiggy.displaywallet_badold.mpk", "rb") as f:
            data = f.read()

        extractor = StreamingUnzip(self.DEST, expected_app_name="com.lightningpiggy.displaywallet")
        with self.assertRaises(RuntimeError) as ctx:
            for i in range(0, len(data), 512):
                extractor.feed(data[i:i + 512])
            extractor.finish()
        self.assertIn("not a directory", str(ctx.exception))

    def test_rejects_wrong_topdir(self):
        """Package whose top dir does not match expected_app_name is refused."""
        with open("../tests/com.micropythonos.ziptest_invalid_topdir.mpk", "rb") as f:
            data = f.read()

        extractor = StreamingUnzip(self.DEST, expected_app_name="com.micropythonos.ziptest")
        with self.assertRaises(RuntimeError) as ctx:
            for i in range(0, len(data), 512):
                extractor.feed(data[i:i + 512])
            extractor.finish()
        self.assertIn("Invalid top-level dir", str(ctx.exception))

    def test_enforces_topdir_entry(self):
        """Any entry not under the top-level dir is caught as out-of-spec."""
        with open("../tests/com.micropythonos.ziptest_mixed_topdir.mpk", "rb") as f:
            data = f.read()

        extractor = StreamingUnzip(self.DEST, expected_app_name="com.micropythonos.ziptest")
        with self.assertRaises(RuntimeError) as ctx:
            extractor.feed(data)
            extractor.finish()
        self.assertIn("outside top-level dir", str(ctx.exception))

    # ---- free-space check ------------------------------------------

    def test_free_space_limit_int(self):
        """Integer free_space_limit is enforced."""
        with open("../tests/com.micropythonos.ziptest_flat_new.mpk", "rb") as f:
            data = f.read()

        # Use a limit of 1 byte to force failure
        extractor = StreamingUnzip(
            self.DEST, expected_app_name="com.micropythonos.ziptest", free_space_limit=1
        )
        with self.assertRaises(RuntimeError) as ctx:
            extractor.feed(data[:2048])  # first chunk is enough to trigger check
            extractor.finish()
        self.assertIn("Not enough free space", str(ctx.exception))

    def test_free_space_limit_callable(self):
        """Callable free_space_limit is invoked with required bytes."""
        with open("../tests/com.micropythonos.ziptest_flat_new.mpk", "rb") as f:
            data = f.read()

        def check(req):
            if req > 100:
                raise RuntimeError("Custom space check failed: need %d bytes" % req)

        extractor = StreamingUnzip(
            self.DEST, expected_app_name="com.micropythonos.ziptest", free_space_limit=check
        )
        with self.assertRaises(RuntimeError) as ctx:
            extractor.feed(data[:2048])
            extractor.finish()
        self.assertIn("Custom space check", str(ctx.exception))

    # ---- zero-size file regression ------------------------------------

    def test_extracts_files_after_zero_size_file(self):
        """Files after a zero-size file entry must all be extracted."""
        with open("../tests/com.micropythonos.ziptest_zerosize.mpk", "rb") as f:
            data = f.read()

        extractor = StreamingUnzip(self.DEST, expected_app_name="com.micropythonos.ziptest")
        for i in range(0, len(data), 512):
            extractor.feed(data[i : i + 512])
        extractor.finish()

        self._assert_dir(self.DEST)
        self._assert_dir(f"{self.DEST}/assets")
        self._assert_file_size(f"{self.DEST}/assets/hello.py", 232)
        self._assert_file_size(f"{self.DEST}/assets/__init__.py", 0)
        self._assert_file_size(f"{self.DEST}/assets/world.py", 80)
        self._assert_dir(f"{self.DEST}/META-INF")
        self._assert_file_size(f"{self.DEST}/META-INF/MANIFEST.JSON", 16)

    def test_extracts_files_after_zero_size_file_single_chunk(self):
        """Same regression with the whole archive in a single feed() call."""
        with open("../tests/com.micropythonos.ziptest_zerosize.mpk", "rb") as f:
            data = f.read()

        extractor = StreamingUnzip(self.DEST, expected_app_name="com.micropythonos.ziptest")
        extractor.feed(data)
        extractor.finish()

        self._assert_file_size(f"{self.DEST}/assets/__init__.py", 0)
        self._assert_file_size(f"{self.DEST}/assets/world.py", 80)
        self._assert_file_size(f"{self.DEST}/META-INF/MANIFEST.JSON", 16)


if __name__ == "__main__":
    unittest.main()
