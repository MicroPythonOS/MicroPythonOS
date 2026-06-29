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


class TestAppManagerPackageLoading(unittest.TestCase):
    """Tests for opt-in package loading in AppManager."""

    APP_NAME = "com_micropythonos_testpkgloader"
    APP_ROOT = "apps/" + APP_NAME

    def setUp(self):
        self._cleanup()
        AppManager.clear()

    def tearDown(self):
        self._cleanup()
        AppManager.clear()
        AppManager.refresh_apps()

    def _cleanup(self):
        try:
            shutil.rmtree(self.APP_ROOT)
        except OSError:
            pass

    @staticmethod
    def _mkdir(path):
        try:
            os.mkdir(path)
        except OSError:
            pass

    def _write_file(self, path, content):
        with open(path, "w") as f:
            f.write(content)

    def _make_app_dir(self):
        self._mkdir("apps")
        self._mkdir(self.APP_ROOT)
        self._mkdir(self.APP_ROOT + "/assets")

    def _write_modules(self, package=True, cls_text="class Hello:\n    pass"):
        self._make_app_dir()
        manifest = (
            '{"name":"PkgTest","publisher":"t","short_description":"x",'
            '"long_description":"x","fullname":"' + self.APP_NAME +
            '","version":"1.0.0","category":"development",'
            '"activities":[{"entrypoint":"assets/hello.py","classname":"Hello",'
            '"intent_filters":[{"action":"main","category":"test"}]}]}'
        )
        self._write_file(self.APP_ROOT + "/MANIFEST.JSON", manifest)
        if package:
            self._write_file(self.APP_ROOT + "/__init__.py", "")
            self._write_file(self.APP_ROOT + "/assets/__init__.py", "")
        self._write_file(self.APP_ROOT + "/assets/hello.py", cls_text)

    def test_is_valid_identifier(self):
        self.assertTrue(AppManager._is_valid_identifier("hello"))
        self.assertTrue(AppManager._is_valid_identifier("_x123"))
        self.assertFalse(AppManager._is_valid_identifier("123bad"))
        self.assertFalse(AppManager._is_valid_identifier("bad-name"))
        self.assertFalse(AppManager._is_valid_identifier(""))

    def test_package_info_when_init_present(self):
        self._write_modules(package=True)
        AppManager.refresh_apps()
        app = AppManager.get(self.APP_NAME)
        self.assertTrue(app is not None)
        pkg = AppManager._package_info(app, "assets/hello.py")
        self.assertTrue(pkg is not None)
        parent, module_name = pkg
        self.assertEqual(module_name, self.APP_NAME + ".assets.hello")
        self.assertEqual(parent, "apps")

    def test_package_info_when_init_missing(self):
        self._write_modules(package=False)
        AppManager.refresh_apps()
        app = AppManager.get(self.APP_NAME)
        self.assertTrue(app is not None)
        self.assertIsNone(AppManager._package_info(app, "assets/hello.py"))

    def test_package_info_invalid_fullname(self):
        self._make_app_dir()
        self._write_file(self.APP_ROOT + "/__init__.py", "")
        self._write_file(self.APP_ROOT + "/assets/__init__.py", "")

        class _FakeApp:
            installed_path = self.APP_ROOT
            fullname = "bad-name.here"

        self.assertIsNone(AppManager._package_info(_FakeApp(), "assets/hello.py"))

    def test_package_info_when_init_mpy_present(self):
        self._make_app_dir()
        manifest = (
            '{"name":"PkgTest","publisher":"t","short_description":"x",'
            '"long_description":"x","fullname":"' + self.APP_NAME +
            '","version":"1.0.0","category":"development",'
            '"activities":[{"entrypoint":"assets/hello.py","classname":"Hello",'
            '"intent_filters":[{"action":"main","category":"test"}]}]}'
        )
        self._write_file(self.APP_ROOT + "/MANIFEST.JSON", manifest)
        self._write_file(self.APP_ROOT + "/__init__.mpy", "")
        self._write_file(self.APP_ROOT + "/assets/__init__.mpy", "")
        self._write_file(self.APP_ROOT + "/assets/hello.py", "class Hello:\n    pass")
        AppManager.refresh_apps()
        app = AppManager.get(self.APP_NAME)
        self.assertTrue(app is not None)
        pkg = AppManager._package_info(app, "assets/hello.py")
        self.assertTrue(pkg is not None)
        parent, module_name = pkg
        self.assertEqual(module_name, self.APP_NAME + ".assets.hello")
        self.assertEqual(parent, "apps")

    def test_package_info_mpy_entrypoint(self):
        self._make_app_dir()
        manifest = (
            '{"name":"PkgTest","publisher":"t","short_description":"x",'
            '"long_description":"x","fullname":"' + self.APP_NAME +
            '","version":"1.0.0","category":"development",'
            '"activities":[{"entrypoint":"assets/hello.mpy","classname":"Hello",'
            '"intent_filters":[{"action":"main","category":"test"}]}]}'
        )
        self._write_file(self.APP_ROOT + "/MANIFEST.JSON", manifest)
        self._write_file(self.APP_ROOT + "/__init__.py", "")
        self._write_file(self.APP_ROOT + "/assets/__init__.py", "")
        self._write_file(self.APP_ROOT + "/assets/hello.mpy", "")
        AppManager.refresh_apps()
        app = AppManager.get(self.APP_NAME)
        self.assertTrue(app is not None)
        pkg = AppManager._package_info(app, "assets/hello.mpy")
        self.assertTrue(pkg is not None)
        parent, module_name = pkg
        self.assertEqual(module_name, self.APP_NAME + ".assets.hello")
        self.assertEqual(parent, "apps")

    def test_del_module_tree(self):
        import sys

        sys.modules["x.y"] = object()
        sys.modules["x.y.z"] = object()
        sys.modules["x.y.other"] = object()
        sys.modules["x.a"] = object()
        AppManager._del_module_tree("x.y")
        self.assertTrue("x.y" not in sys.modules)
        self.assertTrue("x.y.z" not in sys.modules)
        self.assertTrue("x.y.other" not in sys.modules)
        self.assertTrue("x.a" in sys.modules)
        del sys.modules["x.a"]

    def test_import_handler_class_package(self):
        self._write_modules(package=True, cls_text="class Hello:\n    X = 1")
        AppManager.refresh_apps()
        spec = {
            "app_fullname": self.APP_NAME,
            "entrypoint": "assets/hello.py",
            "classname": "Hello",
        }
        cls = AppManager._import_handler_class(spec)
        self.assertTrue(cls is not None)
        self.assertEqual(cls.__name__, "Hello")
        self.assertEqual(cls.X, 1)

    def test_import_handler_class_package_reloads(self):
        self._write_modules(package=True, cls_text="class Hello:\n    X = 1")
        AppManager.refresh_apps()
        spec = {
            "app_fullname": self.APP_NAME,
            "entrypoint": "assets/hello.py",
            "classname": "Hello",
        }
        key = (spec["app_fullname"], spec["entrypoint"], spec["classname"])
        cls1 = AppManager._import_handler_class(spec)
        self.assertEqual(cls1.X, 1)
        del AppManager._handler_class_cache[key]
        self._write_modules(package=True, cls_text="class Hello:\n    X = 2")
        cls2 = AppManager._import_handler_class(spec)
        self.assertEqual(cls2.X, 2)


if __name__ == "__main__":
    unittest.main()
