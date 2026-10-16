"""Regression tests for outgoing local events in ChatListActivity."""

import asyncio
import sys
import unittest

sys.path.insert(0, "lib")
sys.path.insert(0, "apps/com_micropythonos_nostr")

import apps.com_micropythonos_nostr.chat_list_activity as chat_list_module
from apps.com_micropythonos_nostr.chat_list_activity import ChatListActivity
from apps.com_micropythonos_nostr.chat_model import (
    KIND_DM,
    KIND_NIP17_CHAT,
    Chat,
    dm_chat_id,
    nip17_group_chat_id,
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
    outbox_flushing = False

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

    def get_or_create_nip17_group(self, participants, title=None, subject=None):
        chat_id = nip17_group_chat_id(participants)
        if chat_id not in self.chats:
            self.chats[chat_id] = Chat.nip17_group(participants, title=title, subject=subject)
        return self.chats[chat_id]

    def update_chat_subject(self, chat_id, subject, ts=0):
        self.subjects = getattr(self, "subjects", [])
        self.subjects.append((chat_id, subject, ts))

    def load_outbox(self):
        return list(getattr(self, "outbox", []))

    def replace_message(self, chat_id, old_event_id, new_message):
        self.replaced = getattr(self, "replaced", [])
        self.replaced.append((chat_id, old_event_id, new_message))
        return True

    def remove_outbox_item(self, placeholder_id):
        before = len(self.outbox)
        self.outbox = [i for i in self.outbox if i.get("placeholder_id") != placeholder_id]
        return len(self.outbox) != before

    def clear_outbox(self):
        self.outbox = []


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


class _SendResult:
    def __init__(self, ids):
        self.ids = list(ids)
        self.local_id = self.ids[0]
        self.published = [("x", i) for i in self.ids]
        self.failed = []


class _PublishingManager(_FakeManager):
    def __init__(self, own_pubkey=None, fail_on_content=None):
        super().__init__(own_pubkey)
        self.nip17_calls = []
        self.fail_on_content = fail_on_content

    def is_connected(self):
        return True

    async def publish_nip17_message_async(
        self, content, recipients, subject=None, reply_to=None, created_at=None,
        progress=None, on_local_id=None,
    ):
        self.nip17_calls.append({
            "content": content, "recipients": list(recipients),
            "subject": subject, "created_at": created_at,
        })
        await asyncio.sleep_ms(0)
        if content == self.fail_on_content:
            raise RuntimeError("NIP-17 message could not be published to anyone")
        return _SendResult(["self_wrap_%d" % len(self.nip17_calls), "peer_wrap"])


class _FakeConnectivity:
    @classmethod
    def get(cls):
        return cls

    @classmethod
    def is_online(cls):
        return True


class TestChatListActivityGroups(unittest.TestCase):
    """Group subjects on incoming events, outbox flush, and row titles."""

    def _activity(self, own_pubkey, manager=None):
        act = object.__new__(ChatListActivity)
        act._manager = manager or _FakeManager(own_pubkey=own_pubkey)
        act._store = _FakeStore()
        act._handlers_registered = False
        act._chat_list = None
        act.has_foreground = lambda: False
        act._post_notification = lambda chat, msg: None
        act._refresh_chat_list = lambda: None
        return act

    def test_new_group_from_event_takes_its_subject(self):
        own = "a" * 64
        act = self._activity(own)
        event = _FakeNostrEvent(
            public_key="b" * 64,
            event_id="g1",
            content="hi",
            created_at=1700000000,
            tags=[["p", own], ["p", "c" * 64], ["subject", "Room"]],
        )
        act._on_event(event)
        chat = act._store.get_chat(nip17_group_chat_id(["b" * 64, "c" * 64]))
        self.assertIsNotNone(chat)
        self.assertEqual(chat.subject, "Room")
        self.assertEqual(chat.title, "Room")

    def test_newer_subject_renames_existing_group(self):
        own = "a" * 64
        act = self._activity(own)
        chat = act._store.get_or_create_nip17_group(["b" * 64, "c" * 64], subject="Old")
        event = _FakeNostrEvent(
            public_key="c" * 64,
            event_id="g2",
            content="rename",
            created_at=1700000001,
            tags=[["p", own], ["p", "b" * 64], ["subject", "New"]],
        )
        act._on_event(event)
        self.assertEqual(getattr(act._store, "subjects", []), [(chat.chat_id, "New", 1700000001)])

    def _outbox_item(self, n, content):
        return {
            "placeholder_id": "out:x:%d" % n, "ts": 1700000000 + n, "chat_id": "nip17_x",
            "content": content, "kind": KIND_NIP17_CHAT, "recipient_pubkey": None,
            "channel_id": None, "participants": ["b" * 64, "c" * 64], "subject": "Room",
        }

    def test_outbox_flush_sends_subject_and_keeps_own_wrap_id(self):
        own = "a" * 64
        manager = _PublishingManager(own_pubkey=own)
        act = self._activity(own, manager=manager)
        act._store.outbox = [self._outbox_item(1, "queued")]
        asyncio.run(act._flush_outbox_async())
        self.assertEqual(len(manager.nip17_calls), 1)
        self.assertEqual(manager.nip17_calls[0]["subject"], "Room")
        self.assertEqual(manager.nip17_calls[0]["created_at"], 1700000001)
        self.assertEqual(manager.nip17_calls[0]["recipients"], ["b" * 64, "c" * 64])
        _chat_id, placeholder, new_message = act._store.replaced[0]
        self.assertEqual(placeholder, "out:x:1")
        self.assertEqual(new_message.event_id, "self_wrap_1")
        self.assertEqual(act._store.outbox, [])
        self.assertFalse(act._store.outbox_flushing)

    def test_outbox_flush_drops_each_item_as_it_is_published(self):
        # A failing second item must not make the next reconnect re-send (and
        # re-wrap, with new ids) the first one.
        own = "a" * 64
        manager = _PublishingManager(own_pubkey=own, fail_on_content="bad")
        act = self._activity(own, manager=manager)
        act._store.outbox = [
            self._outbox_item(1, "good"), self._outbox_item(2, "bad"), self._outbox_item(3, "later"),
        ]
        asyncio.run(act._flush_outbox_async())
        self.assertEqual([c["content"] for c in manager.nip17_calls], ["good", "bad"])
        self.assertEqual([i["content"] for i in act._store.outbox], ["bad", "later"])
        self.assertEqual(len(act._store.replaced), 1)
        self.assertFalse(act._store.outbox_flushing)

    def _flush_requests(self, *activities):
        """Ask each activity to flush, in order, before any task runs."""
        created = []
        orig_connectivity = chat_list_module.ConnectivityManager
        orig_create_task = chat_list_module.TaskManager.create_task
        chat_list_module.ConnectivityManager = _FakeConnectivity
        chat_list_module.TaskManager.create_task = classmethod(
            lambda cls, coro: created.append(coro)
        )
        try:
            for act in activities:
                act._flush_outbox_if_online()
        finally:
            chat_list_module.ConnectivityManager = orig_connectivity
            chat_list_module.TaskManager.create_task = orig_create_task
        return created

    def test_flush_if_online_runs_as_a_task_once(self):
        own = "a" * 64
        manager = _PublishingManager(own_pubkey=own)
        act = self._activity(own, manager=manager)
        act._store.outbox = [self._outbox_item(1, "queued")]
        created = self._flush_requests(act, act)
        self.assertEqual(len(created), 1)
        asyncio.run(created[0])
        self.assertEqual(len(manager.nip17_calls), 1)

    def test_chat_lists_sharing_a_store_flush_it_once(self):
        own = "a" * 64
        manager = _PublishingManager(own_pubkey=own)
        first = self._activity(own, manager=manager)
        second = self._activity(own, manager=manager)
        second._store = first._store
        first._store.outbox = [self._outbox_item(1, "queued")]
        created = self._flush_requests(first, second)
        self.assertEqual(len(created), 1)
        asyncio.run(created[0])
        self.assertEqual(len(manager.nip17_calls), 1)

    def test_flush_can_run_again_after_the_previous_one_ends(self):
        own = "a" * 64
        manager = _PublishingManager(own_pubkey=own)
        act = self._activity(own, manager=manager)
        act._store.outbox = [self._outbox_item(1, "first")]
        asyncio.run(self._flush_requests(act)[0])
        act._store.outbox = [self._outbox_item(2, "second")]
        created = self._flush_requests(act)
        self.assertEqual(len(created), 1)
        asyncio.run(created[0])
        self.assertEqual([c["content"] for c in manager.nip17_calls], ["first", "second"])

    def test_group_row_shows_subject_else_members(self):
        act = self._activity("a" * 64)
        with_subject = Chat.nip17_group(["b" * 64, "c" * 64], subject="Room")
        self.assertTrue(act._format_chat_row(with_subject, 0).startswith("Group: Room"))
        without = Chat.nip17_group(["b" * 64, "c" * 64])
        row = act._format_chat_row(without, 0)
        self.assertTrue(row.startswith("Group: npub1"))
        self.assertIn(", npub1", row.split("\n")[0])


if __name__ == "__main__":
    unittest.main()
