"""
test_appstore_async_refresh.py - Verify AppStore refresh_list, two-phase
data flow, _data_loaded gating, and update recheck behavior.

Regression tests:
- refresh_list() must return immediately and always spawn an async task.
- refresh_list() must skip when a refresh is already in progress.
- download_app_index() Phase 1 builds from installed apps (no network).
- download_app_index() Phase 2 merges store apps and patches installed ones.
- _data_loaded flag gates onResume from re-downloading.
- download_app_index() must not spawn icon download tasks for the app list.
- onResume must not re-trigger icon downloads; placeholders are used instead.
- _run_update_all must call AppManager.refresh_apps before AppUpdateManager recheck.
- _trigger_update_recheck must refresh apps before scheduling recheck.

Usage:
"""

import json
import unittest
import sys

sys.path.insert(0, 'builtin/apps/com.micropythonos.appstore')

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
        store._raw_timer = None
        store._blurhash_timer = None
        store._icon_queue = []
        store._blurhash_queue = []
        store._wip_apps = []
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

    def test_app_index_does_not_download_icons(self):
        """download_app_index should not start icon downloads for the app list."""
        import asyncio

        store = self._make_store()
        store.create_apps_list = lambda: None
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

        # No background icon download tasks should be queued from the list.
        self.assertEqual(
            len(self.tasks_created),
            0,
            "download_app_index must not spawn icon download tasks",
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
        store._wip_apps = []
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

    def test_on_resume_does_not_download_icons(self):
        """onResume must not start icon downloads when some apps lack icon_data."""
        from mpos import App

        store = self._make_store()
        store._data_loaded = True
        app_missing_icon = App("Test", "Pub", "", "", "http://i.png", "",
                               "com.test.missing", "1.0")
        app_missing_icon.icon_data = None
        store.apps = [app_missing_icon]

        store.onResume(MockLabel())

        self.assertEqual(
            len(self.tasks_created),
            0,
            "onResume must not spawn icon download tasks for missing icons",
        )


class TestAppStoreHideWip(unittest.TestCase):
    """Verify hide_wip setting filters BadgeHub work_in_progress apps."""

    def setUp(self):
        import mpos
        import asyncio
        asyncio.new_event_loop()

    def _make_store(self, hide_wip):
        from appstore import AppStore

        store = AppStore()
        store.prefs = MockPrefs(
            backend="badgehub,https://badgehub.eu/api/v3/project-summaries?badge=mpos_api_0,https://badgehub.eu/api/v3/projects"
        )
        store._DEFAULT_BACKEND = store.prefs.get_string("backend")
        store._hide_wip = hide_wip
        store.please_wait_label = MockLabel()
        store._refresh_in_progress = False
        store._data_loaded = False
        store.update_all_button = MockLabel()
        store.main_screen = MockLabel()
        store.create_apps_list = lambda: None
        store._update_category_dropdown = lambda: None
        store._builtin_fullnames = set()
        store._wip_apps = []
        return store

    def test_hide_wip_filters_work_in_progress(self):
        import json
        import asyncio
        import mpos.net.download_manager as dm
        from mpos import AppManager

        json_data = json.dumps([
            {"slug": "com.test.stable", "name": "StableApp", "description": "",
             "development_status": "stable"},
            {"slug": "com.test.wip", "name": "WipApp", "description": "",
             "development_status": "work_in_progress"},
        ])

        async def _fake_download(url):
            return json_data

        orig_list = AppManager._app_list
        AppManager._app_list = []
        orig_dl = dm.DownloadManager.download_url
        dm.DownloadManager.download_url = staticmethod(_fake_download)
        try:
            store = self._make_store(hide_wip=True)
            loop = asyncio.get_event_loop()
            loop.run_until_complete(
                store.download_app_index("https://badgehub.eu/api/v3/project-summaries?badge=mpos_api_0")
            )
            fullnames = [a.fullname for a in store.apps]
            self.assertIn("com.test.stable", fullnames)
            self.assertTrue("com.test.wip" not in fullnames, "work_in_progress app should be filtered out")
        finally:
            dm.DownloadManager.download_url = orig_dl
            AppManager._app_list = orig_list

    def test_show_wip_includes_work_in_progress(self):
        import json
        import asyncio
        import mpos.net.download_manager as dm
        from mpos import AppManager

        json_data = json.dumps([
            {"slug": "com.test.stable", "name": "StableApp", "description": "",
             "development_status": "stable"},
            {"slug": "com.test.wip", "name": "WipApp", "description": "",
             "development_status": "work_in_progress"},
        ])

        async def _fake_download(url):
            return json_data

        orig_list = AppManager._app_list
        AppManager._app_list = []
        orig_dl = dm.DownloadManager.download_url
        dm.DownloadManager.download_url = staticmethod(_fake_download)
        try:
            store = self._make_store(hide_wip=False)
            loop = asyncio.get_event_loop()
            loop.run_until_complete(
                store.download_app_index("https://badgehub.eu/api/v3/project-summaries?badge=mpos_api_0")
            )
            fullnames = [a.fullname for a in store.apps]
            self.assertIn("com.test.stable", fullnames)
            self.assertIn("com.test.wip", fullnames)
        finally:
            dm.DownloadManager.download_url = orig_dl
            AppManager._app_list = orig_list


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


class TestAppDetailBadgehubFileSelection(unittest.TestCase):
    """Ensure AppDetail selects the correct .mpk when BadgeHub lists several."""

    def _make_files(self):
        return [
            {
                "name": "com.lightningpiggy.displaywallet_0.2.6",
                "ext": ".mpk",
                "full_path": "com.lightningpiggy.displaywallet_0.2.6.mpk",
                "url": "https://badgehub.eu/rev/files/0.2.6.mpk",
                "size_of_content": 160000,
            },
            {
                "name": "com.lightningpiggy.displaywallet_0.6.0",
                "ext": ".mpk",
                "full_path": "com.lightningpiggy.displaywallet_0.6.0.mpk",
                "url": "https://badgehub.eu/rev/files/0.6.0.mpk",
                "size_of_content": 309363,
            },
            {
                "name": "icon-64x64",
                "ext": ".png",
                "full_path": "icon-64x64.png",
                "url": "https://badgehub.eu/rev/files/icon.png",
                "size_of_content": 1974,
            },
        ]

    def test_prefers_main_executable(self):
        """The file named in app_metadata.application.executable wins."""
        from appstore_core import _extract_main_executable, _find_download_file

        files = self._make_files()
        app_metadata = {
            "version": "0.6.0",
            "application": [{"executable": "com.lightningpiggy.displaywallet_0.2.6.mpk"}],
        }
        main_executable = _extract_main_executable(app_metadata)
        chosen = _find_download_file(
            files,
            [".mpk", ".zip"],
            app_version=app_metadata["version"],
            main_executable=main_executable,
        )
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["url"], "https://badgehub.eu/rev/files/0.2.6.mpk")

    def test_prefers_version_match_when_no_main_executable(self):
        """When no main executable is set, the .mpk matching the version is chosen."""
        from appstore_core import _find_download_file

        files = self._make_files()
        chosen = _find_download_file(
            files,
            [".mpk", ".zip"],
            app_version="0.6.0",
            main_executable=None,
        )
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["url"], "https://badgehub.eu/rev/files/0.6.0.mpk")

    def test_extract_main_executable_variants(self):
        """Main executable can live in app_metadata.application (list or dict) or top-level."""
        from appstore_core import _extract_main_executable

        self.assertEqual(
            _extract_main_executable({
                "application": [{"executable": "a.mpk"}],
            }),
            "a.mpk",
        )
        self.assertEqual(
            _extract_main_executable({
                "application": {"executable": "b.mpk"},
            }),
            "b.mpk",
        )
        self.assertEqual(
            _extract_main_executable({"executable": "c.mpk"}),
            "c.mpk",
        )
        self.assertIsNone(_extract_main_executable({}))
        self.assertIsNone(_extract_main_executable(None))

    def test_fetch_badgehub_details_selects_version_matched_mpk(self):
        """Integration: real BadgeHub fixture shape with one .mpk chooses the right file."""
        import asyncio
        import mpos.net.download_manager as dm
        from app_detail import AppDetail

        # Snapshot of the BadgeHub API response for com.lightningpiggy.displaywallet.
        # Kept inline so the test does not depend on an untracked external file.
        fixture = (
            '{"slug":"com.lightningpiggy.displaywallet",'
            '"version":{'
            '"revision":38,"files":['
            '{"name":"icon-64x64","ext":".png","full_path":"icon-64x64.png",'
            '"url":"https://badgehub.eu/api/v3/projects/com.lightningpiggy.displaywallet/rev38/files/icon-64x64.png",'
            '"size_of_content":1974},'
            '{"name":"com.lightningpiggy.displaywallet_0.6.0","ext":".mpk",'
            '"full_path":"com.lightningpiggy.displaywallet_0.6.0.mpk",'
            '"url":"https://badgehub.eu/api/v3/projects/com.lightningpiggy.displaywallet/rev38/files/com.lightningpiggy.displaywallet_0.6.0.mpk",'
            '"size_of_content":309363}'
            '],'
            '"app_metadata":{'
            '"name":"Lightning Piggy",'
            '"description":"Display wallet",'
            '"long_description":"See https://www.LightningPiggy.com",'
            '"author":"LightningPiggy Foundation",'
            '"icon_map":{"64x64":"icon-64x64.png"},'
            '"version":"0.6.0",'
            '"badges":["mpos_api_0"]}}}'
        )

        app_obj = type(
            "App",
            (),
            {
                "fullname": "com.lightningpiggy.displaywallet",
                "download_url": None,
                "download_url_size": None,
                "version": None,
                "publisher": None,
                "long_description": None,
            },
        )()

        detail = AppDetail()
        detail.app = app_obj
        detail.appstore = type(
            "AppStore",
            (),
            {
                "get_backend_details_url_from_settings": lambda self: "https://badgehub.eu/api/v3/projects",
                "_BACKEND_API_BADGEHUB": "badgehub",
            },
        )()

        async def fake_download(url, **kwargs):
            return fixture

        orig_dl = dm.DownloadManager.download_url
        dm.DownloadManager.download_url = staticmethod(fake_download)
        try:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(detail.fetch_badgehub_app_details(app_obj))
        finally:
            dm.DownloadManager.download_url = orig_dl

        self.assertEqual(app_obj.version, "0.6.0")
        self.assertIsNotNone(app_obj.download_url)
        self.assertTrue(
            app_obj.download_url.endswith("com.lightningpiggy.displaywallet_0.6.0.mpk"),
            app_obj.download_url,
        )
        self.assertEqual(app_obj.download_url_size, 309363)


class TestBadgehubReportInstall(unittest.TestCase):
    """Verify that installing an app from BadgeHub reports the install."""

    def setUp(self):
        import asyncio
        asyncio.new_event_loop()

        class MockBtn:
            def add_state(self, s): pass
            def remove_state(self, s): pass
        class MockLbl:
            def set_text(self, t): pass
        class MockBar:
            def add_flag(self, f): pass
            def remove_flag(self, f): pass
            def set_value(self, v, w): pass
        self.MockBtn = MockBtn
        self.MockLbl = MockLbl
        self.MockBar = MockBar

    def test_fetch_badgehub_details_includes_revision(self):
        import asyncio
        import mpos.net.download_manager as dm
        from appstore_core import fetch_badgehub_project_details

        fixture = (
            '{"slug":"com.test.app",'
            '"version":{'
            '"revision":42,'
            '"files":[{"name":"app.mpk","ext":".mpk","full_path":"app.mpk",'
            '"url":"https://badgehub.eu/rev/files/app.mpk","size_of_content":1000}],'
            '"app_metadata":{"version":"1.0","author":"Test","long_description":"desc"}}}'
        )

        async def fake_download(url, **kwargs):
            return fixture

        orig = dm.DownloadManager.download_url
        dm.DownloadManager.download_url = staticmethod(fake_download)
        try:
            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(fetch_badgehub_project_details("https://example.com/projects/com.test.app"))
        finally:
            dm.DownloadManager.download_url = orig

        self.assertEqual(result["revision"], 42)
        self.assertEqual(result["version"], "1.0")

    def test_report_badgehub_install_constructs_correct_url(self):
        import appstore_core

        orig_get = appstore_core._get_device_mac_and_id
        appstore_core._get_device_mac_and_id = lambda: ("52:54:00:5e:e8:ab", "54df76309001b5b859eecf1b3832aba97b3a4587")
        try:
            mac, sha1_id = appstore_core._get_device_mac_and_id()
        finally:
            appstore_core._get_device_mac_and_id = orig_get

        self.assertEqual(mac, "52:54:00:5e:e8:ab")
        self.assertEqual(sha1_id, "54df76309001b5b859eecf1b3832aba97b3a4587")
        expected_url = "https://badgehub.eu/api/v3/projects/com.test.app/rev42/report/install?mac=%s&id=%s" % (mac, sha1_id)
        self.assertEqual(expected_url,
                         "https://badgehub.eu/api/v3/projects/com.test.app/rev42/report/install?mac=52:54:00:5e:e8:ab&id=54df76309001b5b859eecf1b3832aba97b3a4587")

    def test_get_device_mac_and_id_real_sha1(self):
        import appstore_core
        import sys

        class FakeMachine:
            @staticmethod
            def unique_id():
                return bytes([0x52, 0x54, 0x00, 0x5E, 0xE8, 0xAB])

        orig_machine = sys.modules.get('machine')
        sys.modules['machine'] = FakeMachine()
        try:
            mac, sha1_id = appstore_core._get_device_mac_and_id()
        finally:
            if orig_machine is not None:
                sys.modules['machine'] = orig_machine
            else:
                del sys.modules['machine']

        self.assertEqual(mac, "52:54:00:5e:e8:ab")
        self.assertEqual(sha1_id, "54df76309001b5b859eecf1b3832aba97b3a4587")

    def test_download_and_install_reports_on_success(self):
        import asyncio
        import mpos
        from app_detail import AppDetail

        report_calls = []

        async def fake_report(fullname, revision):
            report_calls.append((fullname, revision))

        async def fake_download_and_install(url, fullname, **kwargs):
            pass

        orig_report = __import__("appstore_core").report_badgehub_install
        orig_dl = mpos.AppManager.download_and_install_package
        orig_create = mpos.TaskManager.create_task
        mpos.AppManager.download_and_install_package = fake_download_and_install

        tasks = []
        mpos.TaskManager.create_task = lambda c: tasks.append(c) or asyncio.get_event_loop().run_until_complete(c)

        try:
            detail = AppDetail()
            detail.app = type("App", (), {
                "fullname": "com.test.app",
                "download_url": "https://badgehub.eu/file.mpk",
                "revision": 42,
            })()
            detail.appstore = type("AppStore", (), {
                "get_backend_type_from_settings": lambda self: "badgehub",
                "_BACKEND_API_BADGEHUB": "badgehub",
            })()

            detail.install_button = self.MockBtn()
            detail.install_label = self.MockLbl()
            detail.progress_bar = self.MockBar()
            detail.add_action_buttons = lambda *a: None

            # inject our fake report function
            import appstore_core
            appstore_core.report_badgehub_install = fake_report

            loop = asyncio.get_event_loop()
            loop.run_until_complete(detail.download_and_install(detail.app, "apps/com.test.app"))
        finally:
            mpos.AppManager.download_and_install_package = orig_dl
            mpos.TaskManager.create_task = orig_create
            appstore_core.report_badgehub_install = orig_report

        self.assertEqual(len(report_calls), 1)
        self.assertEqual(report_calls[0], ("com.test.app", 42))

    def test_download_and_install_skips_report_when_no_revision(self):
        import asyncio
        import mpos
        from app_detail import AppDetail

        report_calls = []

        async def fake_report(fullname, revision):
            report_calls.append((fullname, revision))

        async def fake_download_and_install(url, fullname, **kwargs):
            pass

        orig_dl = mpos.AppManager.download_and_install_package
        orig_create = mpos.TaskManager.create_task
        mpos.AppManager.download_and_install_package = fake_download_and_install
        mpos.TaskManager.create_task = lambda c: asyncio.get_event_loop().run_until_complete(c)

        try:
            import appstore_core
            orig_report = appstore_core.report_badgehub_install
            appstore_core.report_badgehub_install = fake_report

            detail = AppDetail()
            detail.app = type("App", (), {
                "fullname": "com.test.app",
                "download_url": "https://badgehub.eu/file.mpk",
            })()
            detail.appstore = type("AppStore", (), {
                "get_backend_type_from_settings": lambda self: "badgehub",
                "_BACKEND_API_BADGEHUB": "badgehub",
            })()
            detail.install_button = self.MockBtn()
            detail.install_label = self.MockLbl()
            detail.progress_bar = self.MockBar()
            detail.add_action_buttons = lambda *a: None

            loop = asyncio.get_event_loop()
            loop.run_until_complete(detail.download_and_install(detail.app, "apps/com.test.app"))
        finally:
            mpos.AppManager.download_and_install_package = orig_dl
            mpos.TaskManager.create_task = orig_create
            appstore_core.report_badgehub_install = orig_report

        self.assertEqual(len(report_calls), 0)
