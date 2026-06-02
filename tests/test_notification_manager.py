import unittest

from mpos import Intent
from mpos.notification_manager import NotificationManager, Notification


class _FakeEditor:
    def __init__(self, prefs):
        self._prefs = prefs
        self._pending = dict(prefs.data)

    def put_list(self, key, value):
        self._pending[key] = list(value)
        return self

    def remove_all(self):
        self._pending = {}
        return self

    def commit(self):
        self._prefs.data = dict(self._pending)
        return True


class _FakePrefs:
    def __init__(self, initial_data=None):
        self.data = initial_data or {}

    def get_list(self, key, default=None):
        if key in self.data:
            return list(self.data[key])
        return [] if default is None else default

    def edit(self):
        return _FakeEditor(self)


class TestNotificationManager(unittest.TestCase):
    def setUp(self):
        self.fake_prefs = _FakePrefs({"notifications": []})
        NotificationManager._reset_for_tests(clear_storage=False)
        NotificationManager._prefs = self.fake_prefs

    def tearDown(self):
        NotificationManager._reset_for_tests(clear_storage=False)

    def test_notify_persists_new_notification(self):
        n = Notification(
            notification_id="test.one",
            title="Hello",
            text="World",
            priority=Notification.PRIORITY_DEFAULT,
        )
        NotificationManager.notify(n)

        notifications = NotificationManager.get_notifications()
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0].notification_id, "test.one")
        # Debounce: either persisted already (if LVGL timer fired synchronously, e.g. in unit-test
        # fallback) or a write is pending.  Either way the notification must be in memory.
        wrote = NotificationManager._persist_write_count
        pending = NotificationManager._pending_persist
        self.assertTrue(wrote >= 1 or pending, "Expected a write or a pending write after notify()")

    def test_notify_existing_updates_timestamp_without_persist(self):
        n1 = Notification(notification_id="same.id", title="Title", text="Text")
        NotificationManager.notify(n1)
        # Flush any pending debounce so we have a clean baseline
        NotificationManager._do_persist()
        NotificationManager._pending_persist = False
        first_writes = NotificationManager._persist_write_count

        existing = NotificationManager.get_notification("same.id")
        first_updated = existing.updated_at

        n2 = Notification(notification_id="same.id", title="Title", text="Text")
        NotificationManager.notify(n2)

        updated = NotificationManager.get_notification("same.id")
        self.assertIsNotNone(updated)
        self.assertGreaterEqual(updated.updated_at, first_updated)
        # Same-ID update must NOT trigger any persist at all
        self.assertEqual(NotificationManager._persist_write_count, first_writes)
        self.assertFalse(NotificationManager._pending_persist)

    def test_sort_by_priority_then_recency(self):
        NotificationManager.notify(
            Notification(
                notification_id="low.old",
                title="Low",
                priority=Notification.PRIORITY_LOW,
            )
        )
        NotificationManager.notify(
            Notification(
                notification_id="high.one",
                title="High",
                priority=Notification.PRIORITY_HIGH,
            )
        )
        NotificationManager.notify(
            Notification(
                notification_id="high.two",
                title="High2",
                priority=Notification.PRIORITY_HIGH,
            )
        )

        ordered = NotificationManager.get_notifications()
        self.assertEqual(ordered[0].notification_id, "high.two")
        self.assertEqual(ordered[1].notification_id, "high.one")
        self.assertEqual(ordered[2].notification_id, "low.old")

    def test_loads_from_persistence_on_boot(self):
        self.fake_prefs.data = {
            "notifications": [
                {
                    "notification_id": "persisted.one",
                    "icon_symbol": "*",
                    "title": "Persisted",
                    "text": "Kept",
                    "priority": Notification.PRIORITY_HIGH,
                    "intent": {
                        "action": "main",
                        "data": None,
                        "extras": {"k": 1},
                        "flags": {"clear_top": True},
                        "app_fullname": "com.example.app",
                    },
                    "auto_cancel": True,
                    "app_fullname": "com.example.app",
                    "created_at": 1,
                    "updated_at": 2,
                }
            ]
        }

        NotificationManager._initialized = False
        NotificationManager._notifications = {}
        loaded = NotificationManager.get_notifications()

        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].notification_id, "persisted.one")
        self.assertEqual(loaded[0].title, "Persisted")
        self.assertIsInstance(loaded[0].intent, Intent)
        self.assertEqual(loaded[0].intent.action, "main")
        self.assertEqual(loaded[0].intent.app_fullname, "com.example.app")

    def test_trigger_auto_cancel_and_app_fallback(self):
        from mpos.content.app_manager import AppManager

        started = []
        old_start_app = AppManager.start_app
        AppManager.start_app = staticmethod(lambda fullname: started.append(fullname) or True)
        try:
            NotificationManager.notify(
                Notification(
                    notification_id="open.app",
                    title="Open",
                    app_fullname="com.micropythonos.osupdate",
                    auto_cancel=True,
                )
            )

            result = NotificationManager.trigger("open.app")
            self.assertTrue(result)
            self.assertEqual(started, ["com.micropythonos.osupdate"])
            self.assertIsNone(NotificationManager.get_notification("open.app"))
        finally:
            AppManager.start_app = old_start_app


if __name__ == "__main__":
    unittest.main()
