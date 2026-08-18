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
    ICON_SRC = "data/_test_icon.png"

    def setUp(self):
        self._rm(self.APP_DIR)
        self._mkdirs("data")
        with open(self.ICON_SRC, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0bIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")

    def tearDown(self):
        self._rm(self.APP_DIR)
        self._rm(self.ICON_SRC)
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

    def _write_manifest_data(self, dest_dir, data):
        manifest = dest_dir + "/MANIFEST.JSON"
        with open(manifest, "w") as f:
            ujson.dump(data, f)

    def test_category_string_becomes_normalized_list(self):
        self._mkdirs(self.APP_DIR)
        self._write_manifest_data(self.APP_DIR, {
            "name": "TestApp",
            "fullname": "com.micropythonos.test_app_flat",
            "version": "0.0.1",
            "category": "graphics",
            "activities": [],
        })
        app = App.from_manifest(self.APP_DIR)
        self.assertEqual(app.categories, ["Graphics"])
        self.assertEqual(app.category, "Graphics")

    def test_categories_list_is_normalized(self):
        self._mkdirs(self.APP_DIR)
        self._write_manifest_data(self.APP_DIR, {
            "name": "TestApp",
            "fullname": "com.micropythonos.test_app_flat",
            "version": "0.0.1",
            "categories": ["default", "Finance"],
            "activities": [],
        })
        app = App.from_manifest(self.APP_DIR)
        self.assertEqual(app.categories, ["Default", "Finance"])
        self.assertEqual(app.category, "Default")

    def test_categories_takes_precedence_over_category(self):
        self._mkdirs(self.APP_DIR)
        self._write_manifest_data(self.APP_DIR, {
            "name": "TestApp",
            "fullname": "com.micropythonos.test_app_flat",
            "version": "0.0.1",
            "category": "ignored",
            "categories": ["graphics", "utilities"],
            "activities": [],
        })
        app = App.from_manifest(self.APP_DIR)
        self.assertEqual(app.categories, ["Graphics", "Utilities"])

    def test_no_category_is_empty_list(self):
        self._mkdirs(self.APP_DIR)
        self._write_manifest_data(self.APP_DIR, {
            "name": "TestApp",
            "fullname": "com.micropythonos.test_app_flat",
            "version": "0.0.1",
            "activities": [],
        })
        app = App.from_manifest(self.APP_DIR)
        self.assertEqual(app.categories, [])
        self.assertEqual(app.category, "")

    def test_normalize_category_title_case(self):
        self.assertEqual(App._normalize_category("launcher"), "Launcher")
        self.assertEqual(App._normalize_category("GRAPHICS"), "Graphics")
        self.assertEqual(App._normalize_category("uTiLiTiEs"), "Utilities")

    def test_is_valid_launcher_with_normalized_category(self):
        self._mkdirs(self.APP_DIR)
        self._write_manifest_data(self.APP_DIR, {
            "name": "TestLauncher",
            "fullname": "com.micropythonos.test_app_flat",
            "version": "0.0.1",
            "category": "launcher",
            "activities": [{
                "entrypoint": "code.py",
                "classname": "Main",
                "intent_filters": [{"action": "main", "category": "launcher"}],
            }],
        })
        self._write_code(self.APP_DIR, "code.py")
        app = App.from_manifest(self.APP_DIR)
        self.assertTrue(app.is_valid_launcher())

    def test_is_valid_launcher_multiple_categories(self):
        self._mkdirs(self.APP_DIR)
        self._write_manifest_data(self.APP_DIR, {
            "name": "TestLauncher",
            "fullname": "com.micropythonos.test_app_flat",
            "version": "0.0.1",
            "categories": ["Default", "Launcher"],
            "activities": [{
                "entrypoint": "code.py",
                "classname": "Main",
                "intent_filters": [{"action": "main", "category": "launcher"}],
            }],
        })
        self._write_code(self.APP_DIR, "code.py")
        app = App.from_manifest(self.APP_DIR)
        self.assertTrue(app.is_valid_launcher())

    def test_direct_construction_normalizes_categories(self):
        app = App(category="utilities")
        self.assertEqual(app.categories, ["Utilities"])
        app = App(category=["default", "Finance"])
        self.assertEqual(app.categories, ["Default", "Finance"])


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
