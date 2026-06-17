import logging
import os
import shutil
import unittest

from mpos import AppManager


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        # MicroPython reuses the LogRecord object, so snapshot the message now.
        self.records.append(record.message)


class TestAppManagerInstallMpk(unittest.TestCase):
    """Tests for the offline ``install_mpk`` path using the strict MPK spec."""

    APP_FULLNAME = "com.micropythonos.ziptest"
    APP_ROOT = f"apps/{APP_FULLNAME}"
    TEMP_MPK = "data/tmp_ziptest_Xr0.mpk"

    def setUp(self):
        self.dest_folder = self.APP_ROOT
        self.temp_mpk = self.TEMP_MPK
        self._remove_path(self.dest_folder)
        self._remove_path(self.temp_mpk)
        try:
            os.stat("data")
        except OSError:
            os.mkdir("data")

    def tearDown(self):
        self._remove_path(self.dest_folder)
        self._remove_path(self.temp_mpk)

    def _remove_path(self, path):
        try:
            st = os.stat(path)
        except OSError:
            return
        if st[0] & 0x4000:
            shutil.rmtree(path)
        else:
            os.remove(path)

    def _copy_file(self, source, dest):
        with open(source, "rb") as source_file:
            with open(dest, "wb") as dest_file:
                while True:
                    chunk = source_file.read(1024)
                    if not chunk:
                        break
                    dest_file.write(chunk)

    def _exists(self, path):
        try:
            os.stat(path)
            return True
        except OSError:
            return False

    def _assert_dir(self, path):
        st = os.stat(path)
        self.assertTrue(st[0] & 0x4000)

    def _assert_not_exists(self, path):
        self.assertFalse(self._exists(path))

    def _assert_file_size(self, path, expected_size):
        st = os.stat(path)
        self.assertTrue(st[0] & 0x8000)
        self.assertEqual(st[6], expected_size)

    def _assert_app_tree_old(self, root):
        """Layout used by pre-flatten MPKs."""
        self._assert_dir(root)
        self._assert_dir(f"{root}/assets")
        self._assert_dir(f"{root}/META-INF")
        self._assert_dir(f"{root}/res")
        self._assert_dir(f"{root}/res/mipmap-mdpi")
        self._assert_file_size(f"{root}/assets/hello.py", 232)
        self._assert_file_size(f"{root}/META-INF/MANIFEST.JSON", 406)
        self._assert_file_size(f"{root}/res/mipmap-mdpi/icon_64x64.png", 5499)

    def _assert_app_tree_flat(self, root):
        """New flat app layout."""
        self._assert_dir(root)
        self._assert_dir(f"{root}/assets")
        self._assert_file_size(f"{root}/assets/hello.py", 232)
        self._assert_file_size(f"{root}/MANIFEST.JSON", 406)
        self._assert_file_size(f"{root}/icon_64x64.png", 5499)
        self._assert_not_exists(f"{root}/META-INF")
        self._assert_not_exists(f"{root}/res")
        self._assert_not_exists(f"{root}/res/mipmap-mdpi")

    def _capture_app_logs(self):
        handler = _ListHandler()
        logger = logging.getLogger("mpos.app.app")
        logger.handlers.append(handler)
        return handler, logger

    def _detach_app_logs(self, handler, logger):
        try:
            logger.handlers.remove(handler)
        except ValueError:
            pass

    # ---- happy path (new flat layout) --------------------------------

    def test_install_flat_mpk(self):
        """Well-formed flat (stored) MPK extracts correctly."""
        self._copy_file("../tests/com.micropythonos.ziptest_flat_new.mpk", self.temp_mpk)
        AppManager.install_mpk(self.temp_mpk, self.dest_folder)
        self.assertFalse(self._exists(self.temp_mpk))
        self._assert_app_tree_flat(self.APP_ROOT)

    def test_install_deflated_mpk(self):
        """Well-formed deflated MPK extracts correctly."""
        self._copy_file("../tests/com.micropythonos.ziptest_flat_new_deflated.mpk", self.temp_mpk)
        AppManager.install_mpk(self.temp_mpk, self.dest_folder)
        self.assertFalse(self._exists(self.temp_mpk))
        self._assert_app_tree_flat(self.APP_ROOT)

    def test_install_largefirst_mpk(self):
        """Well-formed MPK with a large first file extracts correctly."""
        self._copy_file("../tests/com.micropythonos.ziptest_flat_largefirst.mpk", self.temp_mpk)
        AppManager.install_mpk(self.temp_mpk, self.dest_folder)
        self.assertFalse(self._exists(self.temp_mpk))
        self._assert_dir(self.APP_ROOT)
        self._assert_dir(f"{self.APP_ROOT}/assets")
        self._assert_dir(f"{self.APP_ROOT}/META-INF")
        self._assert_dir(f"{self.APP_ROOT}/res")

    # ---- backward compatibility (old nested layout) -------------------

    def test_install_old_flat_mpk(self):
        """Old nested-layout MPK still installs and emits deprecation warnings."""
        handler, logger = self._capture_app_logs()
        try:
            self._copy_file("../tests/com.micropythonos.ziptest_flat.mpk", self.temp_mpk)
            AppManager.install_mpk(self.temp_mpk, self.dest_folder)
            self.assertFalse(self._exists(self.temp_mpk))
            self._assert_app_tree_old(self.APP_ROOT)
            self.assertTrue(any("Deprecated manifest path" in t for t in handler.records), handler.records)
            self.assertTrue(any("Deprecated icon path" in t for t in handler.records), handler.records)
        finally:
            self._detach_app_logs(handler, logger)

    def test_install_old_deflated_mpk(self):
        """Old nested-layout deflated MPK still installs."""
        self._copy_file("../tests/com.micropythonos.ziptest_flat_deflated.mpk", self.temp_mpk)
        AppManager.install_mpk(self.temp_mpk, self.dest_folder)
        self.assertFalse(self._exists(self.temp_mpk))
        self._assert_app_tree_old(self.APP_ROOT)

    # ---- error path --------------------------------------------------

    def test_rejects_first_entry_not_a_dir(self):
        """Package whose first entry is a file (not a directory) is refused."""
        self._copy_file("../tests/com.micropythonos.ziptest_largefirst.mpk", self.temp_mpk)

        with self.assertRaises(RuntimeError) as ctx:
            AppManager.install_mpk(self.temp_mpk, self.dest_folder)

        self.assertIn("not a directory", str(ctx.exception))
        self._assert_not_exists(self.dest_folder)

    def test_rejects_wrong_topdir(self):
        """Package whose top dir does not match destination name is refused."""
        self._copy_file("../tests/com.micropythonos.ziptest_Xr0.mpk", self.temp_mpk)

        with self.assertRaises(RuntimeError) as ctx:
            AppManager.install_mpk(self.temp_mpk, self.dest_folder)

        self.assertIn("Invalid top-level dir", str(ctx.exception))
        self._assert_not_exists(self.dest_folder)

    def test_rejects_wrong_expected_fullname(self):
        """Package whose top dir does not match the expected fullname is refused."""
        self._copy_file("../tests/com.micropythonos.ziptest_invalid_topdir.mpk", self.temp_mpk)
        self.dest_folder = "apps/com.micropythonos.ziptest_invalid"
        with self.assertRaises(RuntimeError) as ctx:
            AppManager.install_mpk(self.temp_mpk, self.dest_folder)
        self.assertIn("Invalid top-level dir", str(ctx.exception))
        self._assert_not_exists(self.dest_folder)


if __name__ == "__main__":
    unittest.main()
