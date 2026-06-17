import logging
import os
import shutil
import unittest
import ujson

from mpos import App, AppManager


class _ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        # MicroPython reuses the LogRecord object, so snapshot the message now.
        self.records.append(record.message)


class TestAppManifestAndIcon(unittest.TestCase):
    APP_DIR = "apps/com.micropythonos.test_app_flat"
    ICON_SRC = "apps/com.micropythonos.helloworld/icon_64x64.png"

    def setUp(self):
        self._rm(self.APP_DIR)

    def tearDown(self):
        self._rm(self.APP_DIR)
        AppManager.clear()

    def _rm(self, path):
        try:
            st = os.stat(path)
        except OSError:
            return
        if st[0] & 0x4000:
            shutil.rmtree(path)
        else:
            os.remove(path)

    def _mkdirs(self, path):
        parts = path.split("/")
        acc = ""
        for part in parts:
            if not part:
                continue
            acc = acc + "/" + part if acc else part
            try:
                os.mkdir(acc)
            except OSError as e:
                if e.errno != 17:  # EEXIST
                    raise

    def _copy_file(self, source, dest):
        with open(source, "rb") as sf:
            with open(dest, "wb") as df:
                while True:
                    chunk = sf.read(1024)
                    if not chunk:
                        break
                    df.write(chunk)

    def _copy_icon(self, dest_dir, old_layout=False):
        if old_layout:
            icon_dir = dest_dir + "/res/mipmap-mdpi"
            self._mkdirs(icon_dir)
            dest = icon_dir + "/icon_64x64.png"
        else:
            dest = dest_dir + "/icon_64x64.png"
        self._copy_file(self.ICON_SRC, dest)
        return dest

    def _write_manifest(self, dest_dir, entrypoint, manifest_name="MANIFEST.JSON"):
        manifest = dest_dir + "/" + manifest_name
        data = {
            "name": "TestApp",
            "publisher": "MicroPythonOS",
            "fullname": "com.micropythonos.test_app_flat",
            "version": "0.0.1",
            "category": "development",
            "activities": [
                {
                    "entrypoint": entrypoint,
                    "classname": "Main",
                    "intent_filters": [{"action": "main", "category": "launcher"}],
                }
            ],
        }
        with open(manifest, "w") as f:
            ujson.dump(data, f)

    def _write_code(self, dest_dir, entrypoint):
        path = dest_dir + "/" + entrypoint
        parent = path.rsplit("/", 1)[0]
        if parent != dest_dir:
            self._mkdirs(parent)
        with open(path, "w") as f:
            f.write("class Main:\n    pass\n")

    def _attach_handler(self):
        handler = _ListHandler()
        logger = logging.getLogger("mpos.app.app")
        logger.handlers.append(handler)
        return handler, logger

    def _detach_handler(self, handler, logger):
        try:
            logger.handlers.remove(handler)
        except ValueError:
            pass

    def test_from_manifest_prefers_root_manifest(self):
        self._mkdirs(self.APP_DIR)
        self._write_manifest(self.APP_DIR, "assets/code.py")
        self._write_code(self.APP_DIR, "assets/code.py")
        app = App.from_manifest(self.APP_DIR)
        self.assertEqual(app.fullname, "com.micropythonos.test_app_flat")
        self.assertEqual(app.main_launcher_activity["entrypoint"], "assets/code.py")

    def test_from_manifest_falls_back_to_meta_inf_with_warning(self):
        handler, logger = self._attach_handler()
        try:
            self._mkdirs(self.APP_DIR)
            self._mkdirs(self.APP_DIR + "/META-INF")
            self._write_manifest(
                self.APP_DIR + "/META-INF", "assets/code.py", manifest_name="MANIFEST.JSON"
            )
            self._write_code(self.APP_DIR, "assets/code.py")
            app = App.from_manifest(self.APP_DIR)
            self.assertEqual(app.fullname, "com.micropythonos.test_app_flat")
            self.assertTrue(
                any("Deprecated manifest path" in r for r in handler.records)
            )
        finally:
            self._detach_handler(handler, logger)

    def test_load_icon_data_prefers_flat_icon(self):
        self._mkdirs(self.APP_DIR)
        self._write_manifest(self.APP_DIR, "assets/code.py")
        self._write_code(self.APP_DIR, "assets/code.py")
        self._copy_icon(self.APP_DIR, old_layout=False)
        app = App.from_manifest(self.APP_DIR)
        self.assertEqual(
            app.icon_path,
            "apps/com.micropythonos.test_app_flat/icon_64x64.png",
        )
        self.assertTrue(len(app.icon_data) > 0)

    def test_load_icon_data_falls_back_to_nested_icon_with_warning(self):
        handler, logger = self._attach_handler()
        try:
            self._mkdirs(self.APP_DIR)
            self._write_manifest(self.APP_DIR, "assets/code.py")
            self._write_code(self.APP_DIR, "assets/code.py")
            self._copy_icon(self.APP_DIR, old_layout=True)
            app = App.from_manifest(self.APP_DIR)
            self.assertEqual(
                app.icon_path,
                "apps/com.micropythonos.test_app_flat/res/mipmap-mdpi/icon_64x64.png",
            )
            self.assertTrue(len(app.icon_data) > 0)
            self.assertTrue(
                any("Deprecated icon path" in r for r in handler.records)
            )
        finally:
            self._detach_handler(handler, logger)

    def test_flat_entrypoint_in_manifest(self):
        self._mkdirs(self.APP_DIR)
        self._write_manifest(self.APP_DIR, "code.py")
        self._write_code(self.APP_DIR, "code.py")
        self._copy_icon(self.APP_DIR, old_layout=False)
        app = App.from_manifest(self.APP_DIR)
        self.assertEqual(app.main_launcher_activity["entrypoint"], "code.py")

    def test_nested_entrypoint_in_manifest(self):
        self._mkdirs(self.APP_DIR)
        self._write_manifest(self.APP_DIR, "assets/code.py")
        self._write_code(self.APP_DIR, "assets/code.py")
        self._copy_icon(self.APP_DIR, old_layout=False)
        app = App.from_manifest(self.APP_DIR)
        self.assertEqual(app.main_launcher_activity["entrypoint"], "assets/code.py")


class TestAppManagerStartApp(unittest.TestCase):
    APP_DIR = "apps/com.micropythonos.test_start_app"

    def setUp(self):
        self._rm(self.APP_DIR)

    def tearDown(self):
        self._rm(self.APP_DIR)
        AppManager.clear()

    def _rm(self, path):
        try:
            st = os.stat(path)
        except OSError:
            return
        if st[0] & 0x4000:
            shutil.rmtree(path)
        else:
            os.remove(path)

    def _mkdirs(self, path):
        parts = path.split("/")
        acc = ""
        for part in parts:
            if not part:
                continue
            acc = acc + "/" + part if acc else part
            try:
                os.mkdir(acc)
            except OSError as e:
                if e.errno != 17:
                    raise

    def test_start_app_returns_false_without_main_launcher_activity(self):
        self._mkdirs(self.APP_DIR)
        manifest = self.APP_DIR + "/MANIFEST.JSON"
        data = {
            "name": "NoLauncher",
            "publisher": "MicroPythonOS",
            "fullname": "com.micropythonos.test_start_app",
            "version": "0.0.1",
            "category": "development",
            "activities": [
                {
                    "entrypoint": "assets/other.py",
                    "classname": "Other",
                    "intent_filters": [{"action": "other", "category": "default"}],
                }
            ],
        }
        with open(manifest, "w") as f:
            ujson.dump(data, f)
        self._mkdirs(self.APP_DIR + "/assets")
        with open(self.APP_DIR + "/assets/other.py", "w") as f:
            f.write("class Other:\n    pass\n")
        AppManager.clear()
        result = AppManager.start_app("com.micropythonos.test_start_app")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
