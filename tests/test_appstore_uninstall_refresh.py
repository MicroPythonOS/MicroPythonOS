"""
test_appstore_uninstall_refresh.py - Verify the AppStore list picks up install
and uninstall changes made on the detail screen.

Issue #255: after uninstalling an app from its detail screen and going back,
the app was still listed under Installed. AppManager.refresh_apps() replaces
its cache with new App objects, so the object the AppStore list holds keeps
its old installed_path. AppStore.onResume() must sync installed_path from the
refreshed cache and rebuild the list when it changed.

Usage:
    python3 scripts/test_runner.py tests/test_appstore_uninstall_refresh.py
"""

import os
import sys
import ujson
import unittest

sys.path.insert(0, "builtin/apps/com.micropythonos.appstore")


class MockWidget:
    """Minimal stand-in for an lv object used by the banner code."""

    def __init__(self):
        self._flags = set()

    def add_flag(self, flag):
        self._flags.add(flag)

    def remove_flag(self, flag):
        self._flags.discard(flag)

    def has_flag(self, flag):
        return flag in self._flags

    def align(self, *args):
        pass

    def set_height(self, *args):
        pass


class TestAppStoreInstalledStateSync(unittest.TestCase):
    TEST_FULLNAME = "com.test.uninstallme"
    APP_DIR = "apps/" + TEST_FULLNAME

    def setUp(self):
        from appstore import AppStore
        from mpos import AppManager

        self._saved_app_list = list(AppManager._app_list)
        self._saved_by_fullname = dict(AppManager._by_fullname)

        self.store = AppStore()
        self.store.update_all_button = MockWidget()
        self.store.apps_list = MockWidget()
        self.store.category_dropdown = None
        self.store._update_labels = {}
        self.store._wip_apps = []
        self.store._data_loaded = True
        self.store._icon_pipeline = "none"
        self.store._icon_timer = None
        self.store._has_foreground = True

        self.build_calls = []
        self.store.create_apps_list = lambda: self.build_calls.append(1)

    def tearDown(self):
        from mpos import AppManager

        self._remove_app_dir()
        AppManager._app_list = self._saved_app_list
        AppManager._by_fullname = self._saved_by_fullname

    def _remove_app_dir(self):
        try:
            os.remove(self.APP_DIR + "/MANIFEST.JSON")
        except OSError:
            pass
        try:
            os.rmdir(self.APP_DIR)
        except OSError:
            pass

    def _create_app_dir(self):
        from mpos import AppManager, App

        try:
            os.mkdir(self.APP_DIR)
        except OSError:
            pass
        with open(self.APP_DIR + "/MANIFEST.JSON", "w") as f:
            f.write(ujson.dumps({
                "name": "UninstallMe",
                "fullname": self.TEST_FULLNAME,
                "version": "1.0",
                "category": "utilities",
            }))
        AppManager.refresh_apps()
        return AppManager.get(self.TEST_FULLNAME)

    def test_uninstall_removes_app_from_installed_list(self):
        installed = self._create_app_dir()
        self.assertIsNotNone(installed)
        self.assertEqual(installed.installed_path, self.APP_DIR)

        # The AppStore list holds the App object from the AppManager cache.
        self.store.apps = [installed]

        from mpos import AppManager
        AppManager.uninstall_app(self.TEST_FULLNAME)

        # Stale cache object still claims to be installed (the bug).
        self.assertIsNotNone(installed.installed_path)

        self.store.onResume(MockWidget())

        self.assertIsNone(
            installed.installed_path,
            "uninstalled app must lose its installed_path",
        )
        self.assertEqual(
            len(self.build_calls), 1,
            "the Installed list must be rebuilt after an uninstall",
        )

    def test_install_adds_app_to_installed_list(self):
        from mpos import App, AppManager

        store_app = App(
            name="UninstallMe",
            fullname=self.TEST_FULLNAME,
            version="1.0",
            installed_path=None,
        )
        self.store.apps = [store_app]

        self._create_app_dir()
        self.assertIsNone(store_app.installed_path)

        self.store.onResume(MockWidget())

        self.assertEqual(
            store_app.installed_path, self.APP_DIR,
            "installed app must pick up its installed_path",
        )
        self.assertEqual(
            len(self.build_calls), 1,
            "the Installed list must be rebuilt after an install",
        )

    def test_resume_without_changes_does_not_rebuild(self):
        installed = self._create_app_dir()
        self.assertIsNotNone(installed)
        self.store.apps = [installed]

        self.store.onResume(MockWidget())

        self.assertEqual(
            self.build_calls, [],
            "an unchanged list must not be rebuilt on resume",
        )
        self.assertEqual(installed.installed_path, self.APP_DIR)


if __name__ == "__main__":
    unittest.main()
