import os
import shutil
import unittest

from mpos import AppManager

class TestAppManagerInstallMpk(unittest.TestCase):
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

    def _assert_file_size(self, path, expected_size):
        st = os.stat(path)
        self.assertTrue(st[0] & 0x8000)
        self.assertEqual(st[6], expected_size)

    def _assert_app_tree(self, root):
        self._assert_dir(root)
        self._assert_dir(f"{root}/assets")
        self._assert_dir(f"{root}/META-INF")
        self._assert_dir(f"{root}/res")
        self._assert_dir(f"{root}/res/mipmap-mdpi")

        self._assert_file_size(
            f"{root}/assets/hello.py",
            232,
        )
        self._assert_file_size(
            f"{root}/META-INF/MANIFEST.JSON",
            406,
        )
        self._assert_file_size(
            f"{root}/res/mipmap-mdpi/icon_64x64.png",
            5499,
        )

    def test_install_mpk_extracts_files(self):
        # Uncompressed and without extended attributes:
        source_mpk = "../tests/com.micropythonos.ziptest_Xr0.mpk"
        self._copy_file(source_mpk, self.temp_mpk)

        AppManager.install_mpk(self.temp_mpk, self.dest_folder)

        self.assertFalse(self._exists(self.temp_mpk))
        self._assert_app_tree(self.APP_ROOT)

    def test_install_mpk_extracts_files_xr(self):
        # Default zip (deflate.RAW)
        source_mpk = "../tests/com.micropythonos.ziptest_r.mpk"
        self._copy_file(source_mpk, self.temp_mpk)

        AppManager.install_mpk(self.temp_mpk, self.dest_folder)

        self.assertFalse(self._exists(self.temp_mpk))
        self._assert_app_tree(self.APP_ROOT)


    def test_install_mpk_extracts_files_topdir(self):
        # Zip contains top dir
        source_mpk = "../tests/com.micropythonos.ziptest_topdir.mpk"
        self._copy_file(source_mpk, self.temp_mpk)

        self.dest_folder = "apps/com.micropythonos.ziptest"
        AppManager.install_mpk(self.temp_mpk, self.dest_folder)

        self.assertFalse(self._exists(self.temp_mpk))
        self._assert_app_tree(self.dest_folder)

    def test_install_mpk_rejects_invalid_topdir(self):
        # Zip contains top dir that does not match destination name
        source_mpk = "../tests/com.micropythonos.ziptest_invalid_topdir.mpk"
        self._copy_file(source_mpk, self.temp_mpk)

        self.dest_folder = "apps/com.micropythonos.ziptest_invalid"
        AppManager.install_mpk(self.temp_mpk, self.dest_folder)

        self.assertFalse(self._exists(self.temp_mpk))
        self.assertFalse(self._exists(self.dest_folder))
