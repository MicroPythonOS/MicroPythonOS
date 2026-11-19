import sys
import unittest
import asyncio

sys.path.insert(0, "builtin/apps/com.micropythonos.appstore")

import app_detail
import appstore
from mpos import AppManager


class Widget:
    def __init__(self):
        self.text = ""

    def set_text(self, text):
        self.text = text

    def get_text(self):
        return self.text

    def add_state(self, state):
        pass


class TestInstallSafety(unittest.TestCase):
    def setUp(self):
        asyncio.new_event_loop()

    def test_valid_launcher_compiles_on_micropython(self):
        import json
        import store_install

        path = "data/appstore-entry-test"
        store_install.mkdirs(path)
        try:
            with open(path + "/main.py", "w") as output:
                output.write("class Probe: pass\n")
            with open(path + "/MANIFEST.JSON", "w") as output:
                json.dump(
                    {
                        "fullname": "com.test.probe",
                        "version": "1.0.0",
                        "activities": [
                            {
                                "entrypoint": "main.py",
                                "classname": "Probe",
                                "intent_filters": [{"action": "main", "category": "launcher"}],
                            }
                        ],
                    },
                    output,
                )
            store_install.validate_manifest(path, "com.test.probe", "1.0.0")
        finally:
            store_install.remove_tree(path)

    def test_successful_retry_clears_previous_error_and_updates_version(self):
        detail = app_detail.AppDetail()
        detail._has_foreground = True
        detail.app = type(
            "App",
            (),
            {"fullname": "com.test.probe", "_store_source": "upystore", "long_description": "Original description"},
        )()
        detail.long_desc_label = Widget()
        detail.long_desc_label.set_text("Install failed: Offline")
        detail._show_progress_bar = lambda: None
        detail._hide_progress_bar = lambda: None
        detail.add_action_buttons = lambda *args: None
        detail._trigger_update_recheck = lambda: None
        detail.buttoncont = None

        async def progress(*args, **kwargs):
            pass

        async def install(*args, **kwargs):
            return {"version": "1.1.0", "revision": 2}

        detail._update_progress = progress
        original = app_detail.install_package
        original_refresh = AppManager.refresh_apps
        app_detail.install_package = install
        AppManager.refresh_apps = lambda: None
        try:
            asyncio.get_event_loop().run_until_complete(detail.download_and_install(detail.app, "apps/com.test.probe"))
            self.assertFalse("Install failed" in detail.long_desc_label.text)
            self.assertIn("Original description", detail.long_desc_label.text)
            self.assertEqual(detail.app._remote_version, "1.1.0")
            self.assertEqual(detail.app.revision, 2)
        finally:
            app_detail.install_package = original
            AppManager.refresh_apps = original_refresh

    def test_detail_request_failure_does_not_block_uninstall(self):
        from mpos import TaskManager

        detail = app_detail.AppDetail()
        detail._details_error = True
        detail.app = type("App", (), {"fullname": "com.test.probe", "download_url": None})()
        detail.install_button = Widget()
        detail.install_label = Widget()
        detail.install_label.set_text("Uninstall")
        calls = []
        detail.fetch_and_set_app_details = lambda: calls.append("fetch")
        detail.uninstall_app = lambda name: calls.append("uninstall")
        original = TaskManager.create_task
        TaskManager.create_task = lambda coroutine: None
        try:
            detail.toggle_install(detail.app)
            self.assertEqual(calls, ["uninstall"])
        finally:
            TaskManager.create_task = original

    def test_failed_uninstall_preserves_receipt_and_restores_actions(self):
        detail = app_detail.AppDetail()
        detail._has_foreground = True
        detail._action_in_progress = True
        detail.app = None
        detail.buttoncont = None
        detail.long_desc_label = Widget()
        calls = []
        detail._show_progress_bar = lambda: None
        detail._hide_progress_bar = lambda: None
        detail.add_action_buttons = lambda *args: calls.append("actions")
        detail._trigger_update_recheck = lambda: None

        async def progress(*args, **kwargs):
            pass

        detail._update_progress = progress
        original = AppManager.uninstall_app
        original_refresh = AppManager.refresh_apps
        original_receipt = app_detail.forget_receipt
        AppManager.uninstall_app = lambda name: None
        AppManager.refresh_apps = lambda: None
        app_detail.forget_receipt = lambda name: calls.append("receipt removed")
        try:
            asyncio.get_event_loop().run_until_complete(detail.uninstall_app("com.test.missing"))
            self.assertFalse("receipt removed" in calls)
            self.assertFalse(detail._action_in_progress)
            self.assertIn("actions", calls)
            self.assertIn("Uninstall failed", detail.long_desc_label.text)
        finally:
            AppManager.uninstall_app = original
            AppManager.refresh_apps = original_refresh
            app_detail.forget_receipt = original_receipt

    def test_batch_finishes_without_touching_background_widgets(self):
        store = appstore.AppStore()
        store._has_foreground = False
        store._data_loaded = True
        store.apps = []
        installed = []
        original = appstore.install_package
        original_refresh = AppManager.refresh_apps
        import appstore_core

        manager = appstore_core.AppUpdateManager.get_instance()
        original_check = manager.check_for_updates_now

        async def install(data):
            installed.append(data["fullname"])

        appstore.install_package = install
        AppManager.refresh_apps = lambda: None
        manager.check_for_updates_now = lambda: None
        try:
            asyncio.get_event_loop().run_until_complete(
                store._run_update_all(
                    [
                        {"fullname": "com.test.first", "download_url": "https://example.test/a"},
                        {"fullname": "com.test.second", "download_url": "https://example.test/b"},
                    ]
                )
            )
            self.assertEqual(installed, ["com.test.first", "com.test.second"])
            self.assertFalse(store._data_loaded)
            self.assertFalse(store._batch_updating)
        finally:
            appstore.install_package = original
            AppManager.refresh_apps = original_refresh
            manager.check_for_updates_now = original_check


if __name__ == "__main__":
    unittest.main()
