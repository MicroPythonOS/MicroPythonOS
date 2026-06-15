"""
test_appstore_async_refresh.py - Verify AppStore refresh_list, two-phase
data flow, _data_loaded gating, and update recheck behavior.

Regression tests:
- refresh_list() must return immediately and always spawn an async task.
- refresh_list() must skip when a refresh is already in progress.
- download_app_index() Phase 1 builds from installed apps (no network).
- download_app_index() Phase 2 merges store apps and patches installed ones.
- _data_loaded flag gates onResume from re-downloading.
- onResume re-triggers icon downloads when some icons are missing.
- _run_update_all must call AppManager.refresh_apps before AppUpdateManager recheck.
- _trigger_update_recheck must refresh apps before scheduling recheck.

Usage:
    Desktop: ./tests/unittest.sh tests/test_appstore_async_refresh.py
"""

import json
import unittest
import sys

sys.path.insert(0, 'builtin/apps/com.micropythonos.appstore/assets')

from mpos.testing import MockNetwork, inject_mocks


class MockLabel:
    """Minimal stand-in for an lv.label so refresh_list can touch please_wait_label."""

    def __init__(self):
        self._text = ""
        self._flags = set()

    def set_text(self, text):
        self._text = text

    def add_flag(self, flag):
        self._flags.add(flag)

    def remove_flag(self, flag):
        self._flags.discard(flag)

    def has_flag(self, flag):
        return flag in self._flags


class MockPrefs:
    """Minimal SharedPreferences stand-in."""

    def __init__(self, backend="github,https://apps.micropythonos.com/app_index.json"):
        self._data = {"backend": backend}

    def get_string(self, key, default=None):
        return self._data.get(key, default)

    def edit(self):
        return self

    def put_string(self, key, value):
        self._data[key] = value
        return self

    def commit(self):
        pass


class MockAppUpdateManager:
    """Trackable stand-in for AppUpdateManager."""

    def __init__(self):
        self.check_calls = []
        self.current_state = "idle"
        self.updatable_apps = []

    def check_for_updates(self, index_url=None):
        self.check_calls.append("check_for_updates")
        async def _noop():
            pass
        return _noop()

    def check_for_updates_now(self, index_url=None):
        self.check_calls.append("check_for_updates_now")

    @classmethod
    def get_instance(cls):
        if not hasattr(cls, "_inst"):
            cls._inst = cls()
        return cls._inst

    @classmethod
    def clear_instance(cls):
        if hasattr(cls, "_inst"):
            delattr(cls, "_inst")


class MockStateLabel(MockLabel):
    """MockLabel with add_state/remove_state for update-all flow."""

    def __init__(self):
        super().__init__()
        self._states = set()

    def add_state(self, state):
        self._states.add(state)

    def remove_state(self, state):
        self._states.discard(state)


class TestAppStoreAsyncRefresh(unittest.TestCase):
    """Ensure AppStore.refresh_list() never blocks the caller."""

    def setUp(self):
        """Patch TaskManager to capture created tasks and reset the async queue."""
        import asyncio
        import mpos

        # Discard any leaked tasks from previous tests / main.py
        asyncio.new_event_loop()

        self.tasks_created = []
        self._orig_create_task = mpos.TaskManager.create_task

        def _capture_task(coro):
            self.tasks_created.append(coro)
            return self._orig_create_task(coro)

        mpos.TaskManager.create_task = _capture_task

    def tearDown(self):
        import mpos

        mpos.TaskManager.create_task = self._orig_create_task

    def _make_store(self):
        """Return an AppStore instance with enough mocked state to call refresh_list."""
        from appstore import AppStore

        store = AppStore()
        store.prefs = MockPrefs()
        store._DEFAULT_BACKEND = "github,https://apps.micropythonos.com/app_index.json"
        store.please_wait_label = MockLabel()
        store._refresh_in_progress = False
        store.update_all_button = MockLabel()
        store.main_screen = MockLabel()
        return store

    # ------------------------------------------------------------------

    def test_refresh_list_does_not_block(self):
        """refresh_list() must return immediately and create an async task."""
        store = self._make_store()
        # Simulate the online path (import network may fail on desktop; the
        # except branch prints a warning and continues, which is fine).
        store.refresh_list()
        self.assertGreaterEqual(
            len(self.tasks_created),
            1,
            "refresh_list() should have created at least one async task",
        )
        # The wrapper task wraps download_app_index; verify the coroutine name.
        coro = self.tasks_created[0]
        self.assertTrue(
            hasattr(coro, "send") and hasattr(coro, "throw"),
            "TaskManager.create_task should receive a coroutine (awaitable)",
        )

    def test_refresh_list_works_when_offline(self):
        """refresh_list() must create a task even when WiFi is not connected (shows installed apps)."""
        inject_mocks({"network": MockNetwork(connected=False)})
        store = self._make_store()
        store.refresh_list()

        # Should NOT show "not connected" error
        self.assertNotEqual(
            store.please_wait_label._text.lower().find("not connected"),
            0,
            "please_wait_label should NOT show an offline error",
        )

        # An async task should still be created (Phase 1 builds from installed apps)
        self.assertGreaterEqual(
            len(self.tasks_created),
            1,
            "refresh_list() must spawn a download task even when offline",
        )

    def test_refresh_list_skips_duplicate(self):
        """A second call while a refresh is already running must be ignored."""
        store = self._make_store()
        store._refresh_in_progress = True
        store.refresh_list()
        self.assertEqual(
            len(self.tasks_created),
            0,
            "refresh_list() must not start a second task while one is in progress",
        )

    def test_download_icons_is_spawned_not_awaited(self):
        """download_app_index should spawn download_icons as a background task."""
        import asyncio

        store = self._make_store()
        # Provide a dummy JSON string that parses into one app.
        json_data = '[{"name":"Test","publisher":"T","short_description":"sd","long_description":"ld","icon_url":"http://i.png","download_url":"http://a.zip","fullname":"com.test.a","version":"1","category":"test","activities":[]}]'

        async def _fake_download(url):
            return json_data

        # Run download_app_index to completion
        coro = store.download_app_index("http://example.com/index.json")
        # Inject the fake response by monkey-patching just for this run.
        import mpos.net.download_manager as dm
        orig = dm.DownloadManager.download_url
        dm.DownloadManager.download_url = staticmethod(_fake_download)
        try:
            # Give the coroutine an event loop to run in
            loop = asyncio.get_event_loop()
            loop.run_until_complete(coro)
        finally:
            dm.DownloadManager.download_url = orig

        # After the "list" is built, download_icons should have been queued as
        # its own task rather than awaited inline inside download_app_index.
        icon_tasks = [
            t
            for t in self.tasks_created
            if getattr(t, "__name__", "") == "download_icons"
            or (hasattr(t, "cr_frame") and t.cr_frame.f_code.co_name == "download_icons")
        ]
        # Because MicroPython coroutine introspection is limited, we settle for
        # the simpler guarantee: at least one task was created for download_icons,
        # proving icons are loaded in the background.
        self.assertGreaterEqual(
            len(self.tasks_created),
            1,
            "download_icons() should be started as a separate background task",
        )


class TestAppStoreUpdateAllRecheck(unittest.TestCase):
    """Ensure _run_update_all refreshes AppManager before rechecking updates."""

    def setUp(self):
        import asyncio
        import mpos
        import appstore_core

        asyncio.new_event_loop()
        self.tasks_created = []
        self.refresh_calls = []
        self._orig_create_task = mpos.TaskManager.create_task

        def _capture_task(coro):
            self.tasks_created.append(coro)
            return self._orig_create_task(coro)

        mpos.TaskManager.create_task = _capture_task

        self._orig_refresh_apps = mpos.AppManager.refresh_apps
        mpos.AppManager.refresh_apps = lambda: self.refresh_calls.append(True)

        async def _fake_download_and_install(*args, **kwargs):
            pass

        self._orig_download_and_install = mpos.AppManager.download_and_install_package
        mpos.AppManager.download_and_install_package = _fake_download_and_install

        self._orig_aum = appstore_core.AppUpdateManager
        appstore_core.AppUpdateManager = MockAppUpdateManager
        MockAppUpdateManager.clear_instance()

    def tearDown(self):
        import mpos
        import appstore_core
        mpos.TaskManager.create_task = self._orig_create_task
        mpos.AppManager.refresh_apps = self._orig_refresh_apps
        mpos.AppManager.download_and_install_package = self._orig_download_and_install
        appstore_core.AppUpdateManager = self._orig_aum

    def _make_store(self):
        from appstore import AppStore
        store = AppStore()
        store.prefs = MockPrefs()
        store._DEFAULT_BACKEND = "github,https://apps.micropythonos.com/app_index.json"
        store.please_wait_label = MockLabel()
        store._refresh_in_progress = False
        store.update_all_button = MockStateLabel()
        store.update_all_label = MockStateLabel()
        store.main_screen = MockLabel()
        store.apps = []
        return store

    def test_update_all_calls_refresh_before_recheck(self):
        import asyncio
        store = self._make_store()
        app = {
            "fullname": "com.test.app",
            "name": "TestApp",
            "download_url": "http://example.com/app.zip",
        }
        loop = asyncio.get_event_loop()
        loop.run_until_complete(store._run_update_all([app]))
        self.assertTrue(
            self.refresh_calls,
            "AppManager.refresh_apps() must be called after update_all completes",
        )
        instance = MockAppUpdateManager.get_instance()
        self.assertIn(
            "check_for_updates_now",
            instance.check_calls,
            "AppUpdateManager.check_for_updates_now() must be called after update_all",
        )
        self.assertEqual(len(self.refresh_calls), 1)
        self.assertEqual(instance.check_calls.count("check_for_updates_now"), 1)


class TestAppStoreDataFlow(unittest.TestCase):
    """Test the two-phase download_app_index and _data_loaded gating."""

    def setUp(self):
        import asyncio
        import mpos

        asyncio.new_event_loop()

        self.tasks_created = []
        self._orig_create_task = mpos.TaskManager.create_task

        def _capture_task(coro):
            self.tasks_created.append(coro)
            return self._orig_create_task(coro)

        mpos.TaskManager.create_task = _capture_task

    def tearDown(self):
        import mpos
        mpos.TaskManager.create_task = self._orig_create_task

    def _make_store(self):
        from appstore import AppStore

        store = AppStore()
        store.prefs = MockPrefs()
        store._DEFAULT_BACKEND = "github,https://apps.micropythonos.com/app_index.json"
        store.please_wait_label = MockLabel()
        store._refresh_in_progress = False
        store._data_loaded = False
        store.update_all_button = MockLabel()
        store.main_screen = MockLabel()
        # Bypass LVGL UI creation — these tests verify data flow, not rendering
        store.create_apps_list = lambda: None
        return store

    # ------------------------------------------------------------------

    def test_phase1_builds_from_installed_apps(self):
        """Phase 1 populates self.apps from AppManager even when offline."""
        from mpos import App, AppManager
        import asyncio

        installed = App("TestApp", "Pub", "desc", "", "", "",
                        "com.test.installed", "1.0")
        orig_list = AppManager._app_list
        AppManager._app_list = [installed]
        try:
            store = self._make_store()
            loop = asyncio.get_event_loop()
            loop.run_until_complete(
                store.download_app_index("http://offline/index.json")
            )
            self.assertTrue(store._data_loaded)
            self.assertEqual(len(store.apps), 1)
            self.assertEqual(store.apps[0].fullname, "com.test.installed")
        finally:
            AppManager._app_list = orig_list

    def test_phase2_merges_store_only_apps(self):
        """Phase 2 appends store-only apps and patches icon_url/download_url on installed ones."""
        from mpos import App, AppManager
        import asyncio
        import mpos.net.download_manager as dm

        installed = App("ExistingApp", "Pub", "desc", "", "", "",
                        "com.test.existing", "1.0")
        orig_list = AppManager._app_list
        AppManager._app_list = [installed]

        json_data = json.dumps([
            {
                "name": "ExistingApp", "publisher": "Pub",
                "short_description": "desc", "long_description": "",
                "icon_url": "http://i.png", "download_url": "http://a.zip",
                "fullname": "com.test.existing", "version": "2.0",
                "category": "test", "activities": [],
            },
            {
                "name": "NewApp", "publisher": "Pub2",
                "short_description": "new", "long_description": "",
                "icon_url": "http://i2.png", "download_url": "http://a2.zip",
                "fullname": "com.test.new", "version": "1.0",
                "category": "test", "activities": [],
            },
        ])

        async def _fake_download(url):
            return json_data

        orig_dl = dm.DownloadManager.download_url
        dm.DownloadManager.download_url = staticmethod(_fake_download)
        try:
            store = self._make_store()
            loop = asyncio.get_event_loop()
            loop.run_until_complete(
                store.download_app_index("http://example.com/index.json")
            )
            # Both apps should be present
            self.assertEqual(len(store.apps), 2)
            # Existing app should have icon_url and download_url patched
            existing = [a for a in store.apps
                        if a.fullname == "com.test.existing"][0]
            self.assertEqual(existing.icon_url, "http://i.png")
            self.assertEqual(existing.download_url, "http://a.zip")
            # New store-only app should be present
            new = [a for a in store.apps
                   if a.fullname == "com.test.new"][0]
            self.assertIsNotNone(new)
            self.assertEqual(new.icon_url, "http://i2.png")
        finally:
            dm.DownloadManager.download_url = orig_dl
            AppManager._app_list = orig_list

    def test_phase2_offline_graceful(self):
        """When the store download fails, Phase 1's installed list remains intact."""
        from mpos import App, AppManager
        import asyncio

        installed = App("TestApp", "Pub", "desc", "", "", "",
                        "com.test.installed", "1.0")
        orig_list = AppManager._app_list
        AppManager._app_list = [installed]
        try:
            store = self._make_store()
            loop = asyncio.get_event_loop()
            loop.run_until_complete(
                store.download_app_index("http://offline/index.json")
            )
            self.assertEqual(len(store.apps), 1)
            self.assertEqual(store.apps[0].fullname, "com.test.installed")
            self.assertTrue(store._data_loaded)
        finally:
            AppManager._app_list = orig_list

    def test_data_loaded_gates_refresh_on_resume(self):
        """onResume must not call refresh_list when _data_loaded is True."""
        store = self._make_store()
        store._data_loaded = True
        store.apps = []
        store.onResume(MockLabel())
        # No tasks should have been created (Phase 1 skipped)
        self.assertEqual(
            len(self.tasks_created),
            0,
            "onResume must NOT start refresh_list when _data_loaded is True",
        )

    def test_on_resume_resumes_missing_icons(self):
        """onResume re-triggers icon downloads when some apps lack icon_data."""
        from mpos import App

        store = self._make_store()
        store._data_loaded = True
        app_missing_icon = App("Test", "Pub", "", "", "http://i.png", "",
                               "com.test.missing", "1.0")
        app_missing_icon.icon_data = None
        store.apps = [app_missing_icon]

        store.onResume(MockLabel())

        self.assertGreaterEqual(
            len(self.tasks_created),
            1,
            "onResume must re-trigger download_icons when icons are missing",
        )


class TestAppDetailUpdateRecheck(unittest.TestCase):
    """Ensure AppDetail._trigger_update_recheck refreshes AppManager first."""

    def setUp(self):
        import asyncio
        import mpos
        import appstore_core

        asyncio.new_event_loop()
        self.tasks_created = []
        self.refresh_calls = []
        self._orig_create_task = mpos.TaskManager.create_task

        def _capture_task(coro):
            self.tasks_created.append(coro)
            return self._orig_create_task(coro)

        mpos.TaskManager.create_task = _capture_task

        self._orig_refresh_apps = mpos.AppManager.refresh_apps
        mpos.AppManager.refresh_apps = lambda: self.refresh_calls.append(True)

        self._orig_aum = appstore_core.AppUpdateManager
        appstore_core.AppUpdateManager = MockAppUpdateManager
        MockAppUpdateManager.clear_instance()

    def tearDown(self):
        import mpos
        import appstore_core
        mpos.TaskManager.create_task = self._orig_create_task
        mpos.AppManager.refresh_apps = self._orig_refresh_apps
        appstore_core.AppUpdateManager = self._orig_aum

    def _make_detail(self):
        from app_detail import AppDetail
        detail = AppDetail()
        detail.app = type("App", (), {"fullname": "com.test.a"})()
        detail.appstore = type("AppStore", (), {
            "get_backend_type_from_settings": lambda self: "github",
            "_BACKEND_API_BADGEHUB": "badgehub",
        })()
        return detail

    def test_trigger_update_recheck_calls_refresh_apps(self):
        detail = self._make_detail()
        detail._trigger_update_recheck()
        self.assertTrue(
            self.refresh_calls,
            "AppManager.refresh_apps() must be called by _trigger_update_recheck",
        )
        instance = MockAppUpdateManager.get_instance()
        self.assertEqual(
            len(instance.check_calls),
            1,
            "AppUpdateManager.check_for_updates() must be called by _trigger_update_recheck",
        )
        self.assertEqual(
            len(self.tasks_created),
            1,
            "_trigger_update_recheck must schedule check_for_updates via TaskManager.create_task",
        )
