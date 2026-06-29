"""Regression tests for outgoing local events in ChatListActivity."""

import sys
import unittest

sys.path.insert(0, "lib")
sys.path.insert(0, "apps/com_micropythonos_nostr")

from apps.com_micropythonos_nostr.chat_list_activity import ChatListActivity
from apps.com_micropythonos_nostr.chat_model import (
    KIND_DM,
    KIND_NIP17_CHAT,
    Chat,
    dm_chat_id,
)


class _FakeManager:
    def __init__(self, own_pubkey=None):
        self.own_pubkey = own_pubkey
        self.registered = []

    def register_event_handler(self, kind, callback):
        self.registered.append((kind, callback))

    def unregister_event_handler(self, kind, callback):
        pass

    def get_own_pubkey_hex(self):
        return self.own_pubkey


class _FakeStore:
    def __init__(self, chats=None):
        self.chats = dict(chats) if chats else {}
        self.added = []

    def get_chat(self, chat_id):
        return self.chats.get(chat_id)

    def get_or_create_dm(self, own, peer):
        chat_id = dm_chat_id(own, peer)
        if chat_id not in self.chats:
            self.chats[chat_id] = Chat.dm(own, peer)
        return self.chats[chat_id]

    def add_message(self, chat_id, message, mark_unread=False):
        self.added.append((chat_id, message, mark_unread))
        return True

    def update_chat(self, chat):
        self.chats[chat.chat_id] = chat

    def flush_index(self):
        pass


class _FakeNostrEvent:
    def __init__(self, public_key, event_id="eid", kind=KIND_NIP17_CHAT,
                 content="hi", created_at=1234567890, tags=None):
        self.public_key = public_key
        self.content = content
        self.created_at = created_at
        self.kind = kind
        self.tags = tags or []
        self.event = self
        self.event_id = event_id
        self.id = event_id

    def get_display_content(self):
        return self.content


class TestChatListActivityOutgoing(unittest.TestCase):
    def _activity(self, own_pubkey):
        act = object.__new__(ChatListActivity)
        act._manager = _FakeManager(own_pubkey=own_pubkey)
        act._store = _FakeStore()
        act._handlers_registered = False
        act._chat_list = None
        act.has_foreground = lambda: False
        act._post_notification = lambda chat, msg: None
        act._refresh_chat_list = lambda: None
        return act

    def test_own_nip17_event_is_marked_outgoing(self):
        own = "own123"
        peer = "peer456"
        chat_id = dm_chat_id(own, peer)
        act = self._activity(own)

        event = _FakeNostrEvent(
            public_key=own,
            event_id="own_event_1",
            kind=KIND_NIP17_CHAT,
            content="from mpy",
            tags=[["p", peer]],
        )
        act._on_event(event)

        self.assertEqual(len(act._store.added), 1)
        _chat_id, message, _mark_unread = act._store.added[0]
        self.assertEqual(_chat_id, chat_id)
        self.assertTrue(message.outgoing)
        self.assertEqual(message.content, "from mpy")

    def test_own_nip17_event_does_not_post_notification(self):
        own = "own123"
        peer = "peer456"
        act = self._activity(own)
        act.has_foreground = lambda: False
        notifications = []
        act._post_notification = lambda chat, msg: notifications.append((chat, msg))

        event = _FakeNostrEvent(
            public_key=own,
            event_id="own_event_2",
            kind=KIND_NIP17_CHAT,
            content="from mpy",
            tags=[["p", peer]],
        )
        act._on_event(event)

        self.assertEqual(notifications, [])

    def test_peer_nip17_event_is_not_marked_outgoing(self):
        own = "own123"
        peer = "peer456"
        act = self._activity(own)

        event = _FakeNostrEvent(
            public_key=peer,
            event_id="peer_event_1",
            kind=KIND_NIP17_CHAT,
            content="from phone",
            tags=[["p", own]],
        )
        act._on_event(event)

        self.assertEqual(len(act._store.added), 1)
        _chat_id, message, _mark_unread = act._store.added[0]
        self.assertFalse(message.outgoing)


if __name__ == "__main__":
    unittest.main()
