"""Tests for chat notification logic: foreground, per-chat toggle, open chat."""

import sys
import time
import unittest

sys.path.insert(0, "apps")

from com_micropythonos_nostr.chat_model import KIND_DM, Chat, Message
from com_micropythonos_nostr import chat_notifications
from com_micropythonos_nostr.chat_notifications import (
    is_initial_fetch_silenced,
    post_chat_notification,
)


class _FakeNotify:
    def __init__(self):
        self.calls = []

    def __call__(self, notification):
        self.calls.append(notification)


class _FakePrefs:
    def __init__(self, values):
        self._values = values

    def get_int(self, key, default=0):
        return self._values.get(key, default)


class TestChatNotifications(unittest.TestCase):

    def setUp(self):
        self._orig = {
            "get_foreground_app": chat_notifications.get_foreground_app,
            "SharedPreferences": chat_notifications.SharedPreferences,
            "notify": chat_notifications.NotificationManager.notify,
        }
        self._fake_notify = _FakeNotify()
        chat_notifications.NotificationManager.notify = self._fake_notify
        chat_notifications.get_foreground_app = lambda: None
        chat_notifications.SharedPreferences = lambda app: _FakePrefs({})
        from com_micropythonos_nostr.chat_activity import ChatActivity
        self._chat_activity = ChatActivity
        self._chat_activity.currently_open_chat_id = None

    def tearDown(self):
        chat_notifications.get_foreground_app = self._orig["get_foreground_app"]
        chat_notifications.SharedPreferences = self._orig["SharedPreferences"]
        chat_notifications.NotificationManager.notify = self._orig["notify"]

    def _make_chat(self):
        own = "a" * 64
        peer = "b" * 64
        return Chat.dm(own, peer)

    def _make_message(self):
        return Message(
            event_id="e" * 64,
            ts=1700000000,
            pubkey="b" * 64,
            content="hello",
            kind=KIND_DM,
        )

    def test_posts_notification_when_background(self):
        chat = self._make_chat()
        post_chat_notification("com_micropythonos_nostr", chat, self._make_message())
        self.assertEqual(len(self._fake_notify.calls), 1)
        self.assertEqual(self._fake_notify.calls[0].title, chat.title)

    def test_skips_when_app_in_foreground(self):
        chat = self._make_chat()
        chat_notifications.get_foreground_app = lambda: "com_micropythonos_nostr"
        post_chat_notification("com_micropythonos_nostr", chat, self._make_message())
        self.assertEqual(len(self._fake_notify.calls), 0)

    def test_skips_when_per_chat_notifications_disabled(self):
        chat = self._make_chat()
        chat_notifications.SharedPreferences = lambda app: _FakePrefs(
            {f"notifications:{chat.chat_id}": 0}
        )
        post_chat_notification("com_micropythonos_nostr", chat, self._make_message())
        self.assertEqual(len(self._fake_notify.calls), 0)

    def test_skips_when_chat_already_open(self):
        chat = self._make_chat()
        self._chat_activity.currently_open_chat_id = chat.chat_id
        post_chat_notification("com_micropythonos_nostr", chat, self._make_message())
        self.assertEqual(len(self._fake_notify.calls), 0)

    def test_initial_fetch_silenced_without_history(self):
        chat = self._make_chat()
        chat.last_ts = 0
        manager = type("M", (), {"_initial_fetch_deadline": time.time() + 10, "_silent_initial_chats": set()})()
        self.assertTrue(is_initial_fetch_silenced(chat, manager))
        self.assertIn(chat.chat_id, manager._silent_initial_chats)

    def test_initial_fetch_silenced_while_in_silenced_set(self):
        chat = self._make_chat()
        chat.last_ts = 12345
        silenced = {chat.chat_id}
        manager = type("M", (), {"_initial_fetch_deadline": time.time() + 10, "_silent_initial_chats": silenced})()
        self.assertTrue(is_initial_fetch_silenced(chat, manager))

    def test_initial_fetch_not_silenced_with_history(self):
        chat = self._make_chat()
        chat.last_ts = 12345
        manager = type("M", (), {"_initial_fetch_deadline": time.time() + 10, "_silent_initial_chats": set()})()
        self.assertFalse(is_initial_fetch_silenced(chat, manager))

    def test_initial_fetch_not_silenced_after_deadline(self):
        chat = self._make_chat()
        chat.last_ts = 0
        manager = type("M", (), {"_initial_fetch_deadline": time.time() - 1, "_silent_initial_chats": set()})()
        self.assertFalse(is_initial_fetch_silenced(chat, manager))


if __name__ == "__main__":
    unittest.main()
