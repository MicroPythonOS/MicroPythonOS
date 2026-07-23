"""
Tests for the AppStore "updates available" pipeline.

Covers the six serious gaps from tests/plans/app_updates.md:
1. Boot service wiring
2. check_for_updates() state machine and network error handling
3. Notification posting and click->launch
4. _run_update_all() sequential per-app update
5. Post-update UI cleanup
6. suppress_notifications toggle
"""

import sys
import unittest

sys.path.insert(0, "builtin/apps/com.micropythonos.appstore")

# ---------------------------------------------------------------------------
# LVGL constants (available even when display is uninitialised)
# ---------------------------------------------------------------------------

HIDDEN_FLAG = 0x0001
DISABLED_STATE = 0x0080


# ---------------------------------------------------------------------------
# Shared mocks
# ---------------------------------------------------------------------------

class MockLabel:
    def __init__(self):
        self._text = ""
        self._flags = set()
        self._states = set()

    def set_text(self, text):
        self._text = text

    def add_flag(self, flag):
        self._flags.add(flag)

    def remove_flag(self, flag):
        self._flags.discard(flag)

    def has_flag(self, flag):
        return flag in self._flags

    def add_state(self, state):
        self._states.add(state)

    def remove_state(self, state):
        self._states.discard(state)


class MockPrefs:
    """Mimics SharedPreferences(app_id) — first arg is app_id, not data."""

    def __init__(self, app_id, filename=None):
        self._data = {"backend": "github,https://apps.micropythonos.com/app_index.json"}

    def get_string(self, key, default=None):
        return self._data.get(key, default)

    def edit(self):
        return self

    def put_string(self, key, value):
        self._data[key] = value
        return self

    def commit(self):
        pass


class MockConnectivityManager:
    def __init__(self, online=True):
        self._online = online
        self._callbacks = []

    def is_online(self):
        return self._online

    def register_callback(self, cb):
        self._callbacks.append(cb)

    def unregister_callback(self, cb):
        if cb in self._callbacks:
            self._callbacks.remove(cb)

    @classmethod
    def get(cls):
        if not hasattr(cls, "_inst"):
            cls._inst = cls()
        return cls._inst

    @classmethod
    def reset_instance(cls):
        if hasattr(cls, "_inst"):
            delattr(cls, "_inst")


# ---------------------------------------------------------------------------
# Gap #1: Boot service wiring
# ---------------------------------------------------------------------------

class TestBootServiceWiring(unittest.TestCase):
    def setUp(self):
        import asyncio
        asyncio.new_event_loop()

    def test_onStart_calls_app_update_manager_start(self):
        import appstore_boot_service, appstore_core

        start_calls = []

        class _MockAUM:
            _instance = None

            @classmethod
            def get_instance(cls):
                if cls._instance is None:
                    cls._instance = cls()
                return cls._instance

            def start(self):
                start_calls.append(True)

            def stop(self):
                pass

        orig_core = appstore_core.AppUpdateManager
        orig_svc = appstore_boot_service.AppUpdateManager
        appstore_core.AppUpdateManager = _MockAUM
        appstore_boot_service.AppUpdateManager = _MockAUM
        try:
            svc = appstore_boot_service.AppStoreService()
            svc.onStart(None)
            self.assertEqual(len(start_calls), 1)
        finally:
            appstore_core.AppUpdateManager = orig_core
            appstore_boot_service.AppUpdateManager = orig_svc

    def test_onDestroy_calls_app_update_manager_stop(self):
        import appstore_boot_service, appstore_core

        stop_calls = []

        class _MockAUM:
            _instance = None

            @classmethod
            def get_instance(cls):
                if cls._instance is None:
                    cls._instance = cls()
                return cls._instance

            def start(self):
                pass

            def stop(self):
                stop_calls.append(True)

        orig_core = appstore_core.AppUpdateManager
        orig_svc = appstore_boot_service.AppUpdateManager
        appstore_core.AppUpdateManager = _MockAUM
        appstore_boot_service.AppUpdateManager = _MockAUM
        try:
            svc = appstore_boot_service.AppStoreService()
            svc.onDestroy()
            self.assertEqual(len(stop_calls), 1)
        finally:
            appstore_core.AppUpdateManager = orig_core
            appstore_boot_service.AppUpdateManager = orig_svc


# ---------------------------------------------------------------------------
# Gap #2: check_for_updates() state machine + network errors
# ---------------------------------------------------------------------------

class TestAppUpdateManagerCheck(unittest.TestCase):
    def setUp(self):
        import asyncio
        asyncio.new_event_loop()

    def _patch_aum(self):
        import appstore_core
        from appstore_core import AppUpdateManager, AppUpdateState
        import mpos

        MockConnectivityManager.reset_instance()
        orig_cm = appstore_core.ConnectivityManager
        appstore_core.ConnectivityManager = MockConnectivityManager

        orig_sp = appstore_core.SharedPreferences
        appstore_core.SharedPreferences = MockPrefs

        notify_calls = []
        cancel_calls = []

        def _fake_notify(n):
            notify_calls.append(n)

        def _fake_cancel(nid):
            cancel_calls.append(nid)

        orig_notify = mpos.NotificationManager.notify
        orig_cancel = mpos.NotificationManager.cancel
        mpos.NotificationManager.notify = _fake_notify
        mpos.NotificationManager.cancel = _fake_cancel

        AppUpdateManager._instance = None
        aum = AppUpdateManager.get_instance()
        aum._suppress_notifications = True

        return {
            "aum": aum,
            "orig_cm": orig_cm,
            "orig_sp": orig_sp,
            "orig_notify": orig_notify,
            "orig_cancel": orig_cancel,
            "notify_calls": notify_calls,
            "cancel_calls": cancel_calls,
            "appstore_core": appstore_core,
            "AppUpdateState": AppUpdateState,
        }

    def _unpatch(self, ctx):
        import mpos
        ctx["appstore_core"].ConnectivityManager = ctx["orig_cm"]
        ctx["appstore_core"].SharedPreferences = ctx["orig_sp"]
        mpos.NotificationManager.notify = ctx["orig_notify"]
        mpos.NotificationManager.cancel = ctx["orig_cancel"]
        ctx["appstore_core"].AppUpdateManager._instance = None
        MockConnectivityManager.reset_instance()

    def _mock_download_url(self, return_value=None, exception=None):
        import mpos.net.download_manager as dm

        async def _dl(url):
            if exception:
                raise exception
            return return_value

        orig = dm.DownloadManager.download_url
        dm.DownloadManager.download_url = staticmethod(_dl)
        return orig

    def _mock_is_update_available(self, results):
        import mpos
        orig = mpos.AppManager.is_update_available

        def _fake(fullname, version):
            return results.get(fullname, False)

        mpos.AppManager.is_update_available = staticmethod(_fake)
        return orig

    def test_check_for_updates_finds_updates_github_format(self):
        ctx = self._patch_aum()
        try:
            import json
            app_index = json.dumps([
                {"fullname": "com.test.a", "name": "TestA", "version": "2.0", "download_url": "http://x/a.mpk"},
                {"fullname": "com.test.b", "name": "TestB", "version": "1.0", "download_url": "http://x/b.mpk"},
            ])
            orig_dl = self._mock_download_url(return_value=app_index)
            orig_iav = self._mock_is_update_available({"com.test.a": True, "com.test.b": False})
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                loop.run_until_complete(ctx["aum"].check_for_updates())
                self.assertEqual(ctx["aum"].current_state, ctx["AppUpdateState"].UPDATES_AVAILABLE)
                self.assertEqual(len(ctx["aum"].updatable_apps), 1)
                self.assertEqual(ctx["aum"].updatable_apps[0]["fullname"], "com.test.a")
            finally:
                import mpos.net.download_manager as dm
                dm.DownloadManager.download_url = orig_dl
                import mpos
                mpos.AppManager.is_update_available = orig_iav
        finally:
            self._unpatch(ctx)

    def test_check_for_updates_finds_no_updates(self):
        ctx = self._patch_aum()
        try:
            import json
            app_index = json.dumps([
                {"fullname": "com.test.a", "name": "TestA", "version": "1.0", "download_url": "http://x/a.mpk"},
            ])
            orig_dl = self._mock_download_url(return_value=app_index)
            orig_iav = self._mock_is_update_available({"com.test.a": False})
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                loop.run_until_complete(ctx["aum"].check_for_updates())
                self.assertEqual(ctx["aum"].current_state, ctx["AppUpdateState"].NO_UPDATES)
                self.assertEqual(len(ctx["aum"].updatable_apps), 0)
            finally:
                import mpos.net.download_manager as dm
                dm.DownloadManager.download_url = orig_dl
                import mpos
                mpos.AppManager.is_update_available = orig_iav
        finally:
            self._unpatch(ctx)

    def test_check_for_updates_badgehub_format(self):
        ctx = self._patch_aum()
        try:
            import json
            app_index = json.dumps([
                {"slug": "com.test.alpha", "name": "Alpha", "version": "2.0"},
                {"slug": "com.test.beta", "name": "Beta", "version": "1.0"},
            ])
            orig_dl = self._mock_download_url(return_value=app_index)
            orig_iav = self._mock_is_update_available({"com.test.alpha": True, "com.test.beta": False})
            orig_get_url = ctx["aum"]._get_index_url_and_type

            def _fake_get_url():
                return ("https://badgehub.eu/api/v3/project-summaries", "badgehub")

            ctx["aum"]._get_index_url_and_type = _fake_get_url
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                loop.run_until_complete(ctx["aum"].check_for_updates())
                self.assertEqual(ctx["aum"].current_state, ctx["AppUpdateState"].UPDATES_AVAILABLE)
                self.assertEqual(len(ctx["aum"].updatable_apps), 1)
                self.assertEqual(ctx["aum"].updatable_apps[0]["fullname"], "com.test.alpha")
                self.assertEqual(ctx["aum"].updatable_apps[0]["version"], "2.0")
                self.assertIsNone(ctx["aum"].updatable_apps[0]["download_url"])
            finally:
                import mpos.net.download_manager as dm
                dm.DownloadManager.download_url = orig_dl
                import mpos
                mpos.AppManager.is_update_available = orig_iav
                ctx["aum"]._get_index_url_and_type = orig_get_url
        finally:
            self._unpatch(ctx)

    def test_check_for_updates_network_error_becomes_waiting_wifi(self):
        ctx = self._patch_aum()
        try:
            orig_dl = self._mock_download_url(exception=OSError(-113, "ECONNABORTED"))
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                loop.run_until_complete(ctx["aum"].check_for_updates())
                self.assertEqual(ctx["aum"].current_state, ctx["AppUpdateState"].WAITING_WIFI)
            finally:
                import mpos.net.download_manager as dm
                dm.DownloadManager.download_url = orig_dl
        finally:
            self._unpatch(ctx)

    def test_check_for_updates_non_network_error_becomes_error(self):
        ctx = self._patch_aum()
        try:
            orig_dl = self._mock_download_url(exception=ValueError("bad url"))
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                loop.run_until_complete(ctx["aum"].check_for_updates())
                self.assertEqual(ctx["aum"].current_state, ctx["AppUpdateState"].ERROR)
            finally:
                import mpos.net.download_manager as dm
                dm.DownloadManager.download_url = orig_dl
        finally:
            self._unpatch(ctx)

    def test_check_for_updates_json_parse_error(self):
        ctx = self._patch_aum()
        try:
            orig_dl = self._mock_download_url(return_value="not json {{{")
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                loop.run_until_complete(ctx["aum"].check_for_updates())
                self.assertEqual(ctx["aum"].current_state, ctx["AppUpdateState"].ERROR)
            finally:
                import mpos.net.download_manager as dm
                dm.DownloadManager.download_url = orig_dl
        finally:
            self._unpatch(ctx)

    def test_check_in_progress_prevents_reentry(self):
        ctx = self._patch_aum()
        try:
            ctx["aum"]._check_in_progress = True
            import asyncio
            loop = asyncio.get_event_loop()
            loop.run_until_complete(ctx["aum"].check_for_updates())
            self.assertEqual(ctx["aum"].current_state, ctx["AppUpdateState"].IDLE)
        finally:
            self._unpatch(ctx)

    def test_check_for_updates_now_skips_when_check_in_progress(self):
        ctx = self._patch_aum()
        try:
            ctx["aum"]._check_in_progress = True
            import mpos
            tasks = []
            orig_ct = mpos.TaskManager.create_task

            def _capture(coro):
                tasks.append(coro)

            mpos.TaskManager.create_task = _capture
            try:
                ctx["aum"].check_for_updates_now()
                self.assertEqual(len(tasks), 0)
            finally:
                mpos.TaskManager.create_task = orig_ct
        finally:
            self._unpatch(ctx)

    def test_state_transitions_through_checking(self):
        ctx = self._patch_aum()
        try:
            import json
            app_index = json.dumps([
                {"fullname": "com.test.a", "name": "TestA", "version": "2.0", "download_url": "http://x/a.mpk"},
            ])
            states_seen = []

            def _capture_state(state):
                states_seen.append(state)

            ctx["aum"].set_state_callback(_capture_state)
            orig_dl = self._mock_download_url(return_value=app_index)
            orig_iav = self._mock_is_update_available({"com.test.a": True})
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                loop.run_until_complete(ctx["aum"].check_for_updates())
                self.assertIn(ctx["AppUpdateState"].CHECKING_UPDATES, states_seen)
                self.assertEqual(states_seen[-1], ctx["AppUpdateState"].UPDATES_AVAILABLE)
            finally:
                import mpos.net.download_manager as dm
                dm.DownloadManager.download_url = orig_dl
                import mpos
                mpos.AppManager.is_update_available = orig_iav
        finally:
            self._unpatch(ctx)

    def test_network_changed_offline_while_checking(self):
        ctx = self._patch_aum()
        try:
            ctx["aum"].current_state = ctx["AppUpdateState"].CHECKING_UPDATES
            ctx["aum"]._network_changed(False)
            self.assertEqual(ctx["aum"].current_state, ctx["AppUpdateState"].WAITING_WIFI)
        finally:
            self._unpatch(ctx)

    def test_network_changed_online_from_waiting_triggers_check(self):
        ctx = self._patch_aum()
        try:
            import mpos
            tasks = []
            orig_ct = mpos.TaskManager.create_task

            def _capture(coro):
                tasks.append(coro)

            mpos.TaskManager.create_task = _capture
            try:
                ctx["aum"].current_state = ctx["AppUpdateState"].WAITING_WIFI
                ctx["aum"]._network_changed(True)
                self.assertEqual(len(tasks), 1)
            finally:
                mpos.TaskManager.create_task = orig_ct
        finally:
            self._unpatch(ctx)

    def test_network_changed_online_from_error_triggers_check(self):
        ctx = self._patch_aum()
        try:
            import mpos
            tasks = []
            orig_ct = mpos.TaskManager.create_task

            def _capture(coro):
                tasks.append(coro)

            mpos.TaskManager.create_task = _capture
            try:
                ctx["aum"].current_state = ctx["AppUpdateState"].ERROR
                ctx["aum"]._network_changed(True)
                self.assertEqual(len(tasks), 1)
            finally:
                mpos.TaskManager.create_task = orig_ct
        finally:
            self._unpatch(ctx)


# ---------------------------------------------------------------------------
# Gaps #3 and #6: Notification posting + suppress_notifications toggle
# ---------------------------------------------------------------------------

class TestAppUpdateManagerNotifications(unittest.TestCase):
    def setUp(self):
        import asyncio
        asyncio.new_event_loop()

    def tearDown(self):
        MockConnectivityManager.reset_instance()

    def test_notify_updates_available_posts_correct_notification(self):
        import appstore_core
        from appstore_core import AppUpdateManager
        import mpos

        orig_notify = mpos.NotificationManager.notify
        notify_calls = []

        def _fake_notify(n):
            notify_calls.append(n)

        mpos.NotificationManager.notify = _fake_notify
        AppUpdateManager._instance = None
        aum = AppUpdateManager.get_instance()
        aum.updatable_apps = [
            {"fullname": "com.test.a", "name": "TestA"},
            {"fullname": "com.test.b", "name": "TestB"},
        ]
        try:
            aum._notify_updates_available()
            self.assertEqual(len(notify_calls), 1)
            n = notify_calls[0]
            self.assertEqual(n.notification_id, "appstore.updates_available")
            self.assertEqual(n.title, "App updates available")
            self.assertEqual(n.text, "2 apps can be updated")
            self.assertTrue(n.auto_cancel)
            self.assertEqual(n.intent.app_fullname, "com.micropythonos.appstore")
        finally:
            mpos.NotificationManager.notify = orig_notify
            AppUpdateManager._instance = None

    def test_notify_updates_available_singular(self):
        import appstore_core
        from appstore_core import AppUpdateManager
        import mpos

        orig_notify = mpos.NotificationManager.notify
        notify_calls = []

        def _fake_notify(n):
            notify_calls.append(n)

        mpos.NotificationManager.notify = _fake_notify
        AppUpdateManager._instance = None
        aum = AppUpdateManager.get_instance()
        aum.updatable_apps = [{"fullname": "com.test.a", "name": "TestA"}]
        try:
            aum._notify_updates_available()
            self.assertEqual(len(notify_calls), 1)
            self.assertEqual(notify_calls[0].text, "1 app can be updated")
        finally:
            mpos.NotificationManager.notify = orig_notify
            AppUpdateManager._instance = None

    def test_suppress_notifications_blocks_posting(self):
        import appstore_core
        from appstore_core import AppUpdateManager
        import mpos

        orig_notify = mpos.NotificationManager.notify
        notify_calls = []

        def _fake_notify(n):
            notify_calls.append(n)

        mpos.NotificationManager.notify = _fake_notify
        AppUpdateManager._instance = None
        aum = AppUpdateManager.get_instance()
        aum._suppress_notifications = True
        aum.updatable_apps = [{"fullname": "com.test.a", "name": "TestA"}]
        try:
            aum._notify_updates_available()
            self.assertEqual(len(notify_calls), 0)
        finally:
            mpos.NotificationManager.notify = orig_notify
            AppUpdateManager._instance = None

    def test_clear_notification_calls_cancel(self):
        import appstore_core
        from appstore_core import AppUpdateManager
        import mpos

        orig_cancel = mpos.NotificationManager.cancel
        cancel_calls = []

        def _fake_cancel(nid):
            cancel_calls.append(nid)

        mpos.NotificationManager.cancel = _fake_cancel
        AppUpdateManager._instance = None
        aum = AppUpdateManager.get_instance()
        try:
            aum._clear_notification()
            self.assertEqual(cancel_calls, ["appstore.updates_available"])
        finally:
            mpos.NotificationManager.cancel = orig_cancel
            AppUpdateManager._instance = None

    def test_suppress_notifications_property(self):
        import appstore_core
        from appstore_core import AppUpdateManager
        AppUpdateManager._instance = None
        aum = AppUpdateManager.get_instance()
        try:
            self.assertFalse(aum.suppress_notifications)
            aum.suppress_notifications = True
            self.assertTrue(aum.suppress_notifications)
            aum.suppress_notifications = 1
            self.assertTrue(aum.suppress_notifications)
            aum.suppress_notifications = False
            self.assertFalse(aum.suppress_notifications)
        finally:
            AppUpdateManager._instance = None


# ---------------------------------------------------------------------------
# Gap #4: _run_update_all() sequential per-app update
# ---------------------------------------------------------------------------

class TestAppUpdateRunAll(unittest.TestCase):
    def setUp(self):
        import asyncio
        asyncio.new_event_loop()

    def _make_store(self):
        import mpos
        from appstore import AppStore

        self._orig_refresh = mpos.AppManager.refresh_apps
        self._orig_dl = mpos.AppManager.download_and_install_package
        self.refresh_calls = []
        self.install_calls = []

        mpos.AppManager.refresh_apps = lambda: self.refresh_calls.append(True)

        async def _fake_dl(url, fullname, **kwargs):
            self.install_calls.append((url, fullname))

        mpos.AppManager.download_and_install_package = _fake_dl

        store = AppStore()
        store.prefs = MockPrefs(None)
        store._DEFAULT_BACKEND = "github,https://apps.micropythonos.com/app_index.json"
        store.please_wait_label = MockLabel()
        store._refresh_in_progress = False
        store.update_all_button = MockLabel()
        store.update_all_label = MockLabel()
        store.main_screen = MockLabel()
        store.apps = []
        return store

    def tearDown(self):
        import mpos
        mpos.AppManager.refresh_apps = getattr(self, "_orig_refresh", lambda: None)
        mpos.AppManager.download_and_install_package = getattr(self, "_orig_dl", lambda *a, **kw: None)

    def test_run_update_all_installs_each_app_in_order(self):
        store = self._make_store()
        apps = [
            {"fullname": "com.test.a", "name": "AppA", "download_url": "http://x/a.mpk"},
            {"fullname": "com.test.b", "name": "AppB", "download_url": "http://x/b.mpk"},
        ]
        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_until_complete(store._run_update_all(apps))
        self.assertEqual(len(self.install_calls), 2)
        self.assertEqual(self.install_calls[0], ("http://x/a.mpk", "com.test.a"))
        self.assertEqual(self.install_calls[1], ("http://x/b.mpk", "com.test.b"))
        self.assertTrue(self.refresh_calls)

    def test_run_update_all_skips_apps_without_fullname(self):
        store = self._make_store()
        apps = [
            {"name": "NoFullname", "download_url": "http://x/a.mpk"},
            {"fullname": "com.test.b", "name": "AppB", "download_url": "http://x/b.mpk"},
        ]
        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_until_complete(store._run_update_all(apps))
        self.assertEqual(len(self.install_calls), 1)
        self.assertEqual(self.install_calls[0][1], "com.test.b")

    def test_run_update_all_skips_apps_without_download_url(self):
        store = self._make_store()
        apps = [
            {"fullname": "com.test.a", "name": "AppA"},
        ]
        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_until_complete(store._run_update_all(apps))
        self.assertEqual(len(self.install_calls), 0)

    def test_run_update_all_fetches_badgehub_details(self):
        import mpos.net.download_manager as dm

        store = self._make_store()
        apps = [
            {"fullname": "com.test.alpha", "name": "Alpha"},
        ]
        orig_dl = dm.DownloadManager.download_url

        async def _fake_details(url):
            import json
            return json.dumps({
                "version": {
                    "revision": 5,
                    "app_metadata": {"version": "2.0", "author": "Test"},
                    "files": [{
                        "name": "com.test.alpha_2.0",
                        "ext": ".mpk",
                        "full_path": "com.test.alpha_2.0.mpk",
                        "url": "http://badgehub.eu/file.mpk",
                        "size_of_content": 1000,
                    }],
                }
            })

        dm.DownloadManager.download_url = staticmethod(_fake_details)
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            loop.run_until_complete(store._run_update_all(apps))
            self.assertEqual(len(self.install_calls), 1)
            self.assertEqual(self.install_calls[0][0], "http://badgehub.eu/file.mpk")
        finally:
            dm.DownloadManager.download_url = orig_dl

    def test_run_update_all_handles_install_failure(self):
        import mpos

        store = self._make_store()
        mpos.AppManager.download_and_install_package = self._orig_dl
        fail_calls = []

        async def _fail_first(url, fullname, **kwargs):
            fail_calls.append(fullname)
            if fullname == "com.test.a":
                raise OSError("download failed")
            self.install_calls.append((url, fullname))

        mpos.AppManager.download_and_install_package = _fail_first

        apps = [
            {"fullname": "com.test.a", "name": "AppA", "download_url": "http://x/a.mpk"},
            {"fullname": "com.test.b", "name": "AppB", "download_url": "http://x/b.mpk"},
        ]
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            loop.run_until_complete(store._run_update_all(apps))
            self.assertEqual(len(self.install_calls), 1)
            self.assertEqual(self.install_calls[0][1], "com.test.b")
            self.assertIn("com.test.a", fail_calls)
        finally:
            mpos.AppManager.download_and_install_package = self._orig_dl

    def test_run_update_all_disables_button_during_update(self):
        import mpos

        store = self._make_store()
        button_states_during = []

        async def _capture_state(url, fullname, **kwargs):
            button_states_during.append(bool(store.update_all_button._states))

        mpos.AppManager.download_and_install_package = _capture_state
        try:
            apps = [
                {"fullname": "com.test.a", "name": "AppA", "download_url": "http://x/a.mpk"},
            ]
            import asyncio
            loop = asyncio.get_event_loop()
            loop.run_until_complete(store._run_update_all(apps))
            self.assertTrue(button_states_during, "button should be disabled during install")
            self.assertTrue(button_states_during[0], "button._states should be non-empty (disabled)")
        finally:
            mpos.AppManager.download_and_install_package = self._orig_dl

    def test_run_update_all_handles_out_of_space(self):
        import mpos

        store = self._make_store()
        mpos.AppManager.download_and_install_package = self._orig_dl

        async def _fail_space(url, fullname, **kwargs):
            raise OSError("Not enough free space available")

        mpos.AppManager.download_and_install_package = _fail_space

        apps = [
            {"fullname": "com.test.a", "name": "AppA", "download_url": "http://x/a.mpk"},
        ]
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            loop.run_until_complete(store._run_update_all(apps))
            # button should be re-enabled after the loop
            self.assertEqual(len(store.update_all_button._states), 0)
            # label should show space error
            self.assertIn("Not enough space", store.update_all_label._text)
        finally:
            mpos.AppManager.download_and_install_package = self._orig_dl


# ---------------------------------------------------------------------------
# Gap #5: Post-update UI cleanup
# ---------------------------------------------------------------------------

class TestAppUpdatePostUpdate(unittest.TestCase):
    def setUp(self):
        import asyncio
        asyncio.new_event_loop()

    def _make_store(self):
        from appstore import AppStore

        store = AppStore()
        store.prefs = MockPrefs(None)
        store._DEFAULT_BACKEND = "github,https://apps.micropythonos.com/app_index.json"
        store.please_wait_label = MockLabel()
        store._refresh_in_progress = False
        store.update_all_button = MockLabel()
        store.update_all_label = MockLabel()
        store.main_screen = MockLabel()
        store.apps = []
        store._update_labels = {}
        return store

    def test_sync_update_banner_shows_button_when_updates_available(self):
        from appstore_core import AppUpdateState
        store = self._make_store()
        store._sync_update_banner(AppUpdateState.UPDATES_AVAILABLE, [
            {"fullname": "com.test.a", "name": "A"},
            {"fullname": "com.test.b", "name": "B"},
        ])
        self.assertEqual(store.update_all_label._text, "Update 2 Apps")
        self.assertFalse(store.update_all_button.has_flag(HIDDEN_FLAG))

    def test_sync_update_banner_shows_singular(self):
        from appstore_core import AppUpdateState
        store = self._make_store()
        store._sync_update_banner(AppUpdateState.UPDATES_AVAILABLE, [
            {"fullname": "com.test.a", "name": "A"},
        ])
        self.assertEqual(store.update_all_label._text, "Update 1 App")

    def test_sync_update_banner_hides_button_when_no_updates(self):
        from appstore_core import AppUpdateState
        store = self._make_store()
        store._sync_update_banner(AppUpdateState.UPDATES_AVAILABLE, [{"fullname": "com.test.a", "name": "A"}])
        self.assertFalse(store.update_all_button.has_flag(HIDDEN_FLAG))
        store._sync_update_banner(AppUpdateState.NO_UPDATES, [])
        self.assertTrue(store.update_all_button.has_flag(HIDDEN_FLAG))

    def test_sync_update_banner_hides_button_for_all_other_states(self):
        from appstore_core import AppUpdateState
        store = self._make_store()
        # first show the button
        store._sync_update_banner(AppUpdateState.UPDATES_AVAILABLE, [{"fullname": "com.test.a", "name": "A"}])
        for state in [AppUpdateState.IDLE, AppUpdateState.CHECKING_UPDATES,
                       AppUpdateState.NO_UPDATES, AppUpdateState.ERROR,
                       AppUpdateState.WAITING_WIFI]:
            store._sync_update_banner(state, [])
            self.assertTrue(store.update_all_button.has_flag(HIDDEN_FLAG),
                            "button should be hidden for state %s" % state)
            # re-show for next iteration
            store.update_all_button._flags.discard(HIDDEN_FLAG)

    def test_sync_update_banner_shows_per_app_labels(self):
        from appstore_core import AppUpdateState
        store = self._make_store()
        label_a = MockLabel()
        label_b = MockLabel()
        store._update_labels = {"com.test.a": label_a, "com.test.b": label_b}
        store._sync_update_banner(AppUpdateState.UPDATES_AVAILABLE, [
            {"fullname": "com.test.a", "name": "A"},
        ])
        self.assertFalse(label_a.has_flag(HIDDEN_FLAG))
        self.assertTrue(label_b.has_flag(HIDDEN_FLAG))

    def test_on_update_state_change_updates_banner(self):
        from appstore_core import AppUpdateManager, AppUpdateState
        store = self._make_store()
        store._has_foreground = True
        AppUpdateManager._instance = None
        aum = AppUpdateManager.get_instance()
        aum.updatable_apps = [{"fullname": "com.test.a", "name": "A"}]
        aum.current_state = AppUpdateState.UPDATES_AVAILABLE
        try:
            store._on_update_state_change(AppUpdateState.UPDATES_AVAILABLE)
            self.assertEqual(store.update_all_label._text, "Update 1 App")
        finally:
            AppUpdateManager._instance = None


if __name__ == "__main__":
    unittest.main()
