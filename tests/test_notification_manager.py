import sys
import unittest

from mpos import Intent
from mpos.notification_manager import (
    DEFAULT_NOTIFICATION_SOUND,
    NOTIFICATION_SOUND_OPTIONS,
    Notification,
    NotificationManager,
)

_NONE_SOUND = NOTIFICATION_SOUND_OPTIONS[0][1]
_SCALE_UP_SOUND = NOTIFICATION_SOUND_OPTIONS[2][1]
_SUPERHAPPY_SOUND = NOTIFICATION_SOUND_OPTIONS[3][1]


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

    def get_string(self, key, default=None):
        return self.data.get(key, default)

    def get_list(self, key, default=None):
        if key in self.data:
            return list(self.data[key])
        return [] if default is None else default

    def edit(self):
        return _FakeEditor(self)


class _FakeOutput:
    def __init__(self, kind):
        self.kind = kind


class _FakePlayer:
    def start(self):
        pass


class _FakeAudioManager:
    STREAM_NOTIFICATION = 1
    _outputs = []
    _calls = []

    @classmethod
    def get_outputs(cls):
        return cls._outputs

    @classmethod
    def player(cls, **kwargs):
        cls._calls.append(kwargs)
        return _FakePlayer()


class TestNotificationManager(unittest.TestCase):
    def setUp(self):
        self.fake_prefs = _FakePrefs({"notifications": []})
        NotificationManager._reset_for_tests(clear_storage=False)
        NotificationManager._prefs = self.fake_prefs
        NotificationManager._settings_prefs = _FakePrefs({"notification_sound": DEFAULT_NOTIFICATION_SOUND})
        self._orig_audio_manager = sys.modules["mpos.notification_manager"].AudioManager
        sys.modules["mpos.notification_manager"].AudioManager = _FakeAudioManager
        _FakeAudioManager._outputs = []
        _FakeAudioManager._calls = []

    def tearDown(self):
        sys.modules["mpos.notification_manager"].AudioManager = self._orig_audio_manager
        NotificationManager._reset_for_tests(clear_storage=False)

    def _set_outputs(self, *outputs):
        _FakeAudioManager._outputs = list(outputs)

    def _last_sound_call(self):
        if not _FakeAudioManager._calls:
            return None
        return _FakeAudioManager._calls[-1]

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

    def test_notification_sound_defaults_to_coin(self):
        self._set_outputs(_FakeOutput("buzzer"))
        NotificationManager.notify(Notification(notification_id="sound.default", title="Default"))
        call = self._last_sound_call()
        self.assertIsNotNone(call)
        self.assertEqual(call["rtttl"], DEFAULT_NOTIFICATION_SOUND)
        self.assertEqual(call["stream_type"], _FakeAudioManager.STREAM_NOTIFICATION)
        self.assertEqual(call["volume"], 60)

    def test_notification_sound_none_is_silent(self):
        NotificationManager._settings_prefs = _FakePrefs({"notification_sound": _NONE_SOUND})
        self._set_outputs(_FakeOutput("buzzer"))
        NotificationManager.notify(Notification(notification_id="sound.none", title="Silent"))
        self.assertIsNone(self._last_sound_call())

    def test_notification_sound_scale_up(self):
        NotificationManager._settings_prefs = _FakePrefs({"notification_sound": _SCALE_UP_SOUND})
        self._set_outputs(_FakeOutput("buzzer"))
        NotificationManager.notify(Notification(notification_id="sound.scale", title="Scale"))
        self.assertEqual(self._last_sound_call()["rtttl"], _SCALE_UP_SOUND)

    def test_notification_sound_superhappy(self):
        NotificationManager._settings_prefs = _FakePrefs({"notification_sound": _SUPERHAPPY_SOUND})
        self._set_outputs(_FakeOutput("buzzer"))
        NotificationManager.notify(Notification(notification_id="sound.happy", title="Happy"))
        self.assertEqual(self._last_sound_call()["rtttl"], _SUPERHAPPY_SOUND)

    def test_notification_sound_no_buzzer_is_silent(self):
        self._set_outputs(_FakeOutput("i2s"))
        NotificationManager.notify(Notification(notification_id="sound.nobuzzer", title="No buzzer"))
        self.assertIsNone(self._last_sound_call())


if __name__ == "__main__":
    unittest.main()
