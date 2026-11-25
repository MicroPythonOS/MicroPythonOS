import asyncio
import sys
import unittest

sys.path.insert(0, 'builtin/apps/com.micropythonos.appstore')

from mpos import AppManager, Intent, NotificationManager, TaskManager
import appstore
import appstore_core
import store_source


class TestUpdates(unittest.TestCase):
    def setUp(self):
        asyncio.new_event_loop()
        self.saved = []
        self.replace(store_source, 'current_source', lambda: 'upystore')
        self.replace(appstore_core.AppUpdateManager, '_instance', None)
        self.manager = appstore_core.AppUpdateManager.get_instance()
        self.replace(self.manager, '_notify_updates_available', lambda: None)
        self.replace(self.manager, '_clear_notification', lambda: None)

    def replace(self, owner, name, value):
        self.saved.append((owner, name, getattr(owner, name)))
        setattr(owner, name, value)

    def tearDown(self):
        for owner, name, original in reversed(self.saved):
            setattr(owner, name, original)

    def test_update_check_retains_revision_and_source(self):
        calls = []
        async def catalog(url):
            calls.append(url)
            return [{'slug': 'com.test.a', 'name': 'A', 'version': '1.0.0', 'revision': 2, '_store_source': 'upystore', '_store_slug': 'com-test-a'}]
        self.replace(store_source, 'fetch_updates', catalog)
        self.replace(appstore_core, 'update_available', lambda *args: True)
        asyncio.get_event_loop().run_until_complete(self.manager.check_for_updates(force=True))
        self.assertEqual(calls, ['https://upystore.io/app_index.json'])
        self.assertEqual(self.manager.current_state, 'updates_available')
        self.assertEqual(self.manager.updatable_apps[0]['revision'], 2)
        self.assertEqual(self.manager.updatable_apps[0]['_store_source'], 'upystore')

    def test_update_request_error_recovers_on_retry(self):
        async def failure(url):
            raise ValueError('unavailable package metadata')
        self.replace(store_source, 'fetch_updates', failure)
        asyncio.get_event_loop().run_until_complete(self.manager.check_for_updates(force=True))
        self.assertEqual(self.manager.current_state, 'error')
        self.assertFalse(self.manager._check_in_progress)
        async def success(url):
            return []
        store_source.fetch_updates = success
        asyncio.get_event_loop().run_until_complete(self.manager.check_for_updates(force=True))
        self.assertEqual(self.manager.current_state, 'no_updates')

    def test_notification_launches_independent_updates_page(self):
        self.manager.updatable_apps = [{'fullname': 'com.test.a'}]
        self.replace(self.manager, '_update_notifications_enabled', lambda: True)
        notifications = []
        self.replace(NotificationManager, 'notify', notifications.append)
        appstore_core.AppUpdateManager._notify_updates_available(self.manager)
        self.assertEqual(len(notifications), 1)
        notification = notifications[0]
        self.assertEqual(notification.notification_id, 'appstore.updates_available')
        self.assertEqual(notification.app_fullname, 'com.micropythonos.appstore')
        self.assertEqual(notification.intent.app_fullname, 'com.micropythonos.appstore')
        self.assertEqual(notification.intent.extras['category'], 'Updates')

    def test_update_all_is_sequential_and_rechecks_after_refresh(self):
        store = appstore.AppStore()
        store._has_foreground = False
        events = []
        async def install(app):
            events.append(app['fullname'])
            await TaskManager.sleep_ms(0)
        self.replace(appstore, 'install_package', install)
        self.replace(AppManager, 'refresh_apps', lambda: events.append('refresh'))
        self.replace(self.manager, 'check_for_updates_now', lambda: events.append('recheck'))
        apps = [{'fullname': name, 'download_url': 'https://upystore.io/package.mpk'} for name in ('com.test.a', 'com.test.b')]
        asyncio.get_event_loop().run_until_complete(store._run_update_all(apps))
        self.assertEqual(events, ['com.test.a', 'com.test.b', 'refresh', 'recheck'])
        self.assertFalse(store._batch_updating)

    def test_persisted_notification_dispatch_preserves_updates_category(self):
        from mpos import Notification
        self.manager.updatable_apps = [{'fullname': 'com.test.a'}]
        self.replace(self.manager, '_update_notifications_enabled', lambda: True)
        notifications = []
        self.replace(NotificationManager, 'notify', notifications.append)
        appstore_core.AppUpdateManager._notify_updates_available(self.manager)
        notification = Notification.from_persisted_dict(notifications[0].to_persisted_dict())
        AppManager.refresh_apps()
        calls = []
        self.replace(AppManager, 'start_app', lambda fullname, intent=None, **kwargs: calls.append((fullname, intent)) or True)
        self.assertTrue(NotificationManager._dispatch_intent(notification))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], 'com.micropythonos.appstore')
        self.assertIsNotNone(calls[0][1])
        self.assertEqual(calls[0][1].extras['category'], 'Updates')

    def test_pause_detaches_only_own_callback(self):
        store = appstore.AppStore()
        store._has_foreground = True
        store._stop_all_timers = lambda: None
        self.manager.set_state_callback(store._on_update_state_change)
        store.onPause(None)
        self.assertIsNone(self.manager._state_callback)
        self.assertFalse(self.manager.suppress_notifications)
        self.assertFalse(store.has_foreground())

    def test_settings_keep_icons_wip_and_notifications_without_backend_switch(self):
        store = appstore.AppStore()
        store.appFullName = 'com.micropythonos.appstore'
        store.prefs = object()
        store._icon_pipeline = 'download'
        intents = []
        store.startActivity = intents.append
        store.settings_button_tap(None)
        settings = intents[0].extras['settings']
        keys = [setting['key'] for setting in settings]
        self.assertEqual(keys, ['store_source', 'store_query', 'icon_pipeline', 'hide_wip', 'update_notifications'])

    def test_search_does_not_clear_existing_updates_or_request_background_catalog(self):
        store = appstore.AppStore()
        store._data_loaded = True
        self.manager.updatable_apps = [{'fullname': 'com.test.a'}]
        calls = []
        self.replace(self.manager, 'clear_updates_notification', lambda: calls.append('clear'))
        self.replace(self.manager, 'check_for_updates_now', lambda: calls.append('check'))
        store._store_query_changed('calculator')
        self.assertFalse(store._data_loaded)
        self.assertEqual(self.manager.updatable_apps, [{'fullname': 'com.test.a'}])
        self.assertEqual(calls, [])

    def test_category_options_include_installed_updates_and_catalog_categories(self):
        import lvgl as lv
        from mpos import App
        store = appstore.AppStore()
        store._has_foreground = True
        store._hide_wip = True
        store._wip_apps = []
        store._selected_category = 'All'
        store.apps = [App(name='A', fullname='com.test.a', category='utilities', load_icons=False)]
        screen = lv.obj()
        store.category_dropdown = lv.dropdown(screen)
        try:
            store._update_category_dropdown()
            self.assertIn('Installed', store._category_options)
            self.assertIn('Updates', store._category_options)
            self.assertTrue(any('utilities' in value.lower() for value in store._category_options))
        finally:
            screen.delete()


if __name__ == '__main__':
    unittest.main()
