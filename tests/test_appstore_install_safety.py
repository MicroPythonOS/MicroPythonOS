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

    def test_paused_space_progress_ignores_destroyed_label(self):
        detail = app_detail.AppDetail()
        detail._has_foreground = False
        detail.install_label = None
        asyncio.get_event_loop().run_until_complete(detail.space_progress(0, 0))

    def test_verified_archive_uses_real_async_framework_extractor(self):
        import ubinascii
        import json
        import store_install
        from mpos.content.streaming_unzip import StreamingUnzip

        if not hasattr(StreamingUnzip, "feed_async"):
            self.skipTest("Runtime has no asynchronous archive extractor")
        root = "data/appstore-async-extraction-test"
        destination = root + "/com.test.probe"
        archive = root + "/probe.mpk"
        store_install.mkdirs(root)
        original = AppManager.install_mpk

        def forbid_legacy(*args):
            raise RuntimeError("Expected the current asynchronous extractor")

        try:
            with open(archive, "wb") as output:
                output.write(ubinascii.a2b_base64("UEsDBBQAAAAAAAAAIVwAAAAAAAAAAAAAAAAPAAAAY29tLnRlc3QucHJvYmUvUEsDBBQAAAAAAAAAIVzM5EWE4gAAAOIAAAAcAAAAY29tLnRlc3QucHJvYmUvTUFOSUZFU1QuSlNPTnsiZnVsbG5hbWUiOiAiY29tLnRlc3QucHJvYmUiLCAibmFtZSI6ICJQcm9iZSIsICJwdWJsaXNoZXIiOiAiTWljcm9QeXRob25PUyIsICJ2ZXJzaW9uIjogIjEuMC4wIiwgImFjdGl2aXRpZXMiOiBbeyJlbnRyeXBvaW50IjogIm1haW4ucHkiLCAiY2xhc3NuYW1lIjogIlByb2JlIiwgImludGVudF9maWx0ZXJzIjogW3siYWN0aW9uIjogIm1haW4iLCAiY2F0ZWdvcnkiOiAibGF1bmNoZXIifV19XX1QSwMEFAAAAAAAAAAhXBfnE7oSAAAAEgAAABYAAABjb20udGVzdC5wcm9iZS9tYWluLnB5Y2xhc3MgUHJvYmU6IHBhc3MKUEsBAhQAFAAAAAAAAAAhXAAAAAAAAAAAAAAAAA8AAAAAAAAAAAAAAIABAAAAAGNvbS50ZXN0LnByb2JlL1BLAQIUABQAAAAAAAAAIVzM5EWE4gAAAOIAAAAcAAAAAAAAAAAAAACAAS0AAABjb20udGVzdC5wcm9iZS9NQU5JRkVTVC5KU09OUEsBAhQAFAAAAAAAAAAhXBfnE7oSAAAAEgAAABYAAAAAAAAAAAAAAIABSQEAAGNvbS50ZXN0LnByb2JlL21haW4ucHlQSwUGAAAAAAMAAwDLAAAAjwEAAAAA"))
            AppManager.install_mpk = forbid_legacy
            asyncio.get_event_loop().run_until_complete(store_install.extract_package(archive, destination, "com.test.probe"))
            with open(destination + "/MANIFEST.JSON") as source:
                self.assertEqual(json.load(source)["fullname"], "com.test.probe")
            with open(destination + "/main.py") as source:
                self.assertEqual(source.read(), "class Probe: pass\n")
            store_install.validate_manifest(destination, "com.test.probe", "1.0.0")
        finally:
            AppManager.install_mpk = original
            store_install.remove_tree(root)

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

        calls = []

        async def install(*args, **kwargs):
            calls.append(kwargs)
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
            self.assertEqual(calls[0]["space_callback"], detail.space_progress)
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


    def test_pausing_detail_cancels_pending_icon_timer(self):
        detail = app_detail.AppDetail()
        detail._has_foreground = True
        detail.app = type("App", (), {"icon_data": None, "icon_url": "https://example.test/icon"})()
        calls = []

        class Timer:
            def delete(self):
                calls.append("deleted")

        class TimerAPI:
            def timer_create(self, callback, *args):
                return Timer()

        original = app_detail.lv
        app_detail.lv = TimerAPI()
        try:
            detail._start_icon_download()
            detail.onPause(None)
            self.assertEqual(calls, ["deleted"])
            self.assertFalse(detail._icon_download_started)
        finally:
            app_detail.lv = original

    def test_destroyed_detail_releases_widget_references(self):
        detail = app_detail.AppDetail()
        detail._has_foreground = False
        detail.install_button = Widget()
        detail.long_desc_label = Widget()
        detail.appstore = object()
        detail.onDestroy(None)
        self.assertIsNone(detail.install_button)
        self.assertIsNone(detail.long_desc_label)
        self.assertIsNone(detail.appstore)

    def test_icon_callback_accepts_a_new_lvgl_timer_wrapper(self):
        detail = app_detail.AppDetail()
        detail._has_foreground = True
        detail.app = type("App", (), {"icon_data": None, "icon_url": "https://example.test/icon"})()
        callbacks = []
        scheduled = []
        deleted = []

        class Timer:
            def delete(self):
                deleted.append(True)

        class TimerAPI:
            def timer_create(self, callback, *args):
                callbacks.append(callback)
                return Timer()

        original_lv = app_detail.lv
        original_task = app_detail.TaskManager.create_task
        app_detail.lv = TimerAPI()
        app_detail.TaskManager.create_task = lambda task: scheduled.append(task)
        detail._download_icon = lambda: "icon-request"
        try:
            detail._start_icon_download()
            callbacks[0](object())
            self.assertEqual(scheduled, ["icon-request"])
            self.assertEqual(deleted, [True])
            self.assertIsNone(detail._icon_timer)
        finally:
            app_detail.lv = original_lv
            app_detail.TaskManager.create_task = original_task

    def test_cancelled_icon_callback_cannot_consume_a_new_timer(self):
        detail = app_detail.AppDetail()
        detail._has_foreground = True
        detail.app = type("App", (), {"icon_data": None, "icon_url": "https://example.test/icon"})()
        callbacks = []

        class Timer:
            def delete(self):
                pass

        class TimerAPI:
            def timer_create(self, callback, *args):
                callbacks.append(callback)
                return Timer()

        original = app_detail.lv
        app_detail.lv = TimerAPI()
        try:
            detail._start_icon_download()
            detail.onPause(None)
            detail._has_foreground = True
            detail._start_icon_download()
            current = detail._icon_timer
            callbacks[0](object())
            self.assertIs(detail._icon_timer, current)
            detail.onPause(None)
        finally:
            app_detail.lv = original

    def test_destroyed_store_only_clears_its_own_icon_widgets(self):
        store = appstore.AppStore()
        store._has_foreground = False
        owned = object()
        newer = object()
        first = type("App", (), {"fullname": "com.test.first", "image_icon_widget": owned})()
        second = type("App", (), {"fullname": "com.test.second", "image_icon_widget": newer})()
        store.apps = [first, second]
        store._icon_widgets = {first.fullname: owned, second.fullname: object()}
        store.main_screen = object()
        store._stop_all_timers = lambda: None
        store.onDestroy(None)
        self.assertIsNone(first.image_icon_widget)
        self.assertIs(second.image_icon_widget, newer)
        self.assertIsNone(store.main_screen)
        self.assertEqual(store._icon_widgets, {})


if __name__ == "__main__":
    unittest.main()
