import asyncio
import sys
import unittest

sys.path.insert(0, 'builtin/apps/com.micropythonos.appstore')

from mpos import App, TaskManager
import appstore
import appstore_core
import store_source


class TestCoexist(unittest.TestCase):
    def test_store_object_is_separate_from_global_app(self):
        original = App(name='Installed', fullname='com.test.coexist', version='1.0.0', installed_path='apps/com.test.coexist', load_icons=False)
        copied = appstore.AppStore._copy_installed_app(original)
        self.assertFalse(copied is original)
        store_source.attach(copied, {'version': '2.0.0', 'publisher': 'Remote', '_store_source': 'upystore'})
        self.assertEqual(original.version, '1.0.0')
        self.assertFalse(hasattr(original, '_store_source'))
        self.assertEqual(copied.installed_path, original.installed_path)

    def test_pending_deeplink_waits_while_paused(self):
        store = appstore.AppStore()
        store._has_foreground = False
        store._pending_deeplink = 'com.test.coexist'
        app = type('App', (), {'fullname': 'com.test.coexist'})()
        store.apps = [app]
        store._wip_apps = []
        calls = []
        store.show_app_detail = calls.append
        store._resolve_pending_deeplink()
        self.assertEqual(calls, [])
        self.assertEqual(store._pending_deeplink, app.fullname)
        store._has_foreground = True
        store._resolve_pending_deeplink()
        self.assertEqual(calls, [app])
        self.assertIsNone(store._pending_deeplink)

    def test_destroy_discards_pending_navigation(self):
        store = appstore.AppStore()
        store.apps = []
        store._pending_deeplink = 'com.test.coexist'
        store.onDestroy(None)
        self.assertIsNone(store._pending_deeplink)

    def test_service_start_is_idempotent(self):
        manager = appstore_core.AppUpdateManager()
        events = []
        class Connectivity:
            def register_callback(self, callback):
                events.append('register')
            def unregister_callback(self, callback):
                events.append('unregister')
        connectivity = Connectivity()
        original_get = appstore_core.ConnectivityManager.get
        original_task = TaskManager.create_task
        tasks = []
        appstore_core.ConnectivityManager.get = lambda: connectivity
        TaskManager.create_task = tasks.append
        try:
            manager.start()
            manager.start()
            self.assertEqual(events, ['register'])
            self.assertEqual(len(tasks), 1)
            manager.stop()
            self.assertEqual(events, ['register', 'unregister'])
        finally:
            manager.stop()
            appstore_core.ConnectivityManager.get = original_get
            TaskManager.create_task = original_task

    def test_notification_identity_is_separate(self):
        self.assertEqual(appstore_core.AppUpdateManager.NOTIFICATION_ID, 'appstore.updates_available')
        self.assertEqual(appstore_core.AppUpdateManager.ICON_PATH, 'M:builtin/apps/com.micropythonos.appstore/icon_64x64.png')


if __name__ == '__main__':
    unittest.main()
