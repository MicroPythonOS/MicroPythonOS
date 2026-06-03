import os
import shutil
import unittest
import asyncio

from mpos.content.app_manager import AppManager


class TestAppManagerStreamingInstall(unittest.TestCase):

    DEST = "apps/com.micropythonos.ziptest"
    APP_FULLNAME = "com.micropythonos.ziptest"

    def setUp(self):
        self._rm(self.DEST)

    def tearDown(self):
        self._rm(self.DEST)
        self._rm("data/tmp_ziptest_Xr0.mpk")

    def _rm(self, path):
        try:
            st = os.stat(path)
        except OSError:
            return
        if st[0] & 0x4000:
            shutil.rmtree(path)
        else:
            os.remove(path)

    def _copy_file(self, source, dest):
        with open(source, "rb") as sf:
            with open(dest, "wb") as df:
                while True:
                    chunk = sf.read(1024)
                    if not chunk:
                        break
                    df.write(chunk)

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
        self._assert_file_size(f"{root}/assets/hello.py", 232)
        self._assert_file_size(f"{root}/META-INF/MANIFEST.JSON", 406)
        self._assert_file_size(f"{root}/res/mipmap-mdpi/icon_64x64.png", 5499)

    def _run_install(self, source_mpk):
        """Helper that runs the old install_mpk path using the real file."""
        self._copy_file(source_mpk, "data/tmp_ziptest_Xr0.mpk")
        AppManager.install_mpk("data/tmp_ziptest_Xr0.mpk", self.DEST)

    def _run_streaming_install(self, source_mpk):
        """Helper that mocks download_url with chunk_callback to exercise streaming."""
        from mpos.net.download_manager import DownloadManager

        async def fake_download(url, outfile=None, total_size=None,
                                progress_callback=None, chunk_callback=None,
                                headers=None, speed_callback=None, redact_url=False):
            with open(source_mpk, "rb") as f:
                while True:
                    data = f.read(512)
                    if not data:
                        break
                    if chunk_callback:
                        await chunk_callback(data)
            return True

        orig_download = DownloadManager.download_url
        DownloadManager.download_url = fake_download
        try:
            asyncio.run(
                AppManager.download_and_install_package(
                    f"http://mock/{self.APP_FULLNAME}.mpk",
                    self.APP_FULLNAME,
                )
            )
        finally:
            DownloadManager.download_url = orig_download

    def test_install_mpk_uncompressed(self):
        self._run_install("../tests/com.micropythonos.ziptest_Xr0.mpk")
        self._assert_app_tree(self.DEST)

    def test_install_mpk_deflated(self):
        self._run_install("../tests/com.micropythonos.ziptest_r.mpk")
        self._assert_app_tree(self.DEST)

    def test_install_mpk_topdir(self):
        self._run_install("../tests/com.micropythonos.ziptest_topdir.mpk")
        self._assert_app_tree(self.DEST)

    def test_streaming_install_uncompressed(self):
        self._run_streaming_install("../tests/com.micropythonos.ziptest_Xr0.mpk")
        self._assert_app_tree(self.DEST)

    def test_streaming_install_deflated(self):
        self._run_streaming_install("../tests/com.micropythonos.ziptest_r.mpk")
        self._assert_app_tree(self.DEST)

    def test_streaming_install_topdir(self):
        self._run_streaming_install("../tests/com.micropythonos.ziptest_topdir.mpk")
        self._assert_app_tree(self.DEST)

    def test_streaming_install_largefirst_flat(self):
        """Flat package whose first file is larger than a single chunk.

        This reproduces the bug where early peek incorrectly concluded
        the package had a top-level directory because only the first
        entry was visible in the initial 4 KiB buffer.
        """
        self._run_streaming_install("../tests/com.micropythonos.ziptest_largefirst.mpk")
        self._assert_dir(self.DEST)
        self._assert_dir(f"{self.DEST}/assets")
        self._assert_dir(f"{self.DEST}/META-INF")
        self._assert_dir(f"{self.DEST}/res")

    def test_streaming_rejects_invalid_topdir(self):
        from mpos.net.download_manager import DownloadManager

        async def fake_download(url, outfile=None, total_size=None,
                                progress_callback=None, chunk_callback=None,
                                headers=None, speed_callback=None, redact_url=False):
            with open("../tests/com.micropythonos.ziptest_invalid_topdir.mpk", "rb") as f:
                while True:
                    data = f.read(1024)
                    if not data:
                        break
                    if chunk_callback:
                        await chunk_callback(data)
            return True

        orig_download = DownloadManager.download_url
        DownloadManager.download_url = fake_download
        try:
            with self.assertRaises(RuntimeError) as ctx:
                asyncio.run(
                    AppManager.download_and_install_package(
                        "http://mock/bad.mpk",
                        "com.micropythonos.ziptest_invalid",
                    )
                )
            self.assertIn("Invalid top-level dir", str(ctx.exception))
        finally:
            DownloadManager.download_url = orig_download


if __name__ == "__main__":
    unittest.main()
