"""Regression tests for NIP-17 and DM live event handling in ChatActivity."""
import unittest

import sys

sys.path.insert(0, "lib")
sys.path.insert(0, "apps/com_micropythonos_nostr")

import asyncio

import apps.com_micropythonos_nostr.chat_activity as chat_activity_module
from apps.com_micropythonos_nostr.chat_activity import ChatActivity
from apps.com_micropythonos_nostr.chat_model import (
    KIND_CHANNEL_MESSAGE,
    KIND_DM,
    KIND_NIP17_CHAT,
    Chat,
    channel_chat_id,
    dm_chat_id,
)


class _FakeManager:
    def __init__(self, own_pubkey=None):
        self.own_pubkey = own_pubkey
        self.registered = []
        self.unregistered = []

    def register_event_handler(self, kind, callback):
        self.registered.append((kind, callback))

    def unregister_event_handler(self, kind, callback):
        self.unregistered.append((kind, callback))

    def get_own_pubkey_hex(self):
        return self.own_pubkey


class _FakeStore:
    def __init__(self):
        self.messages = {}

    def add_message(self, chat_id, message, mark_unread=False):
        self.messages.setdefault(chat_id, []).append(message)
        return True

    def load_messages(self, chat_id, limit=None):
        return self.messages.get(chat_id, [])

    def get_chat(self, chat_id):
        return None


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


class TestChatActivityRegistersNip17Handler(unittest.TestCase):
    def _activity(self, kind, own_pubkey=None):
        act = object.__new__(ChatActivity)
        act._handler_registered = False
        act._kind = kind
        act._manager = _FakeManager(own_pubkey=own_pubkey)
        return act

    def test_dm_chat_also_registers_nip17_handler(self):
        act = self._activity(KIND_DM, own_pubkey="own")
        act._register_handler()
        self.assertTrue(act._handler_registered)
        kinds = [k for k, _ in act._manager.registered]
        self.assertIn(KIND_DM, kinds)
        self.assertIn(KIND_NIP17_CHAT, kinds)
        # Both entries must point to the same callback method
        self.assertEqual(
            act._manager.registered[0][1],
            act._manager.registered[1][1],
        )

    def test_nip17_group_registers_only_nip17_handler(self):
        act = self._activity(KIND_NIP17_CHAT, own_pubkey="own")
        act._register_handler()
        self.assertTrue(act._handler_registered)
        kinds = [k for k, _ in act._manager.registered]
        self.assertEqual(kinds, [KIND_NIP17_CHAT])

    def test_dm_chat_unregisters_both_handlers(self):
        act = self._activity(KIND_DM, own_pubkey="own")
        act._register_handler()
        act._handler_registered = True
        act._unregister_handler()
        self.assertFalse(act._handler_registered)
        kinds = [k for k, _ in act._manager.unregistered]
        self.assertIn(KIND_DM, kinds)
        self.assertIn(KIND_NIP17_CHAT, kinds)


class TestChatActivityIgnoresOwnEvents(unittest.TestCase):
    def _activity(self, own_pubkey, chat_id, kind):
        act = object.__new__(ChatActivity)
        act._manager = _FakeManager(own_pubkey=own_pubkey)
        act._chat_id = chat_id
        act._kind = kind
        act._store = _FakeStore()
        act._rendered_ids = set()
        act._sent_event_ids = set()
        return act

    def test_on_event_skips_echo_of_just_sent_message(self):
        act = self._activity(
            "own123",
            dm_chat_id("own123", "peer456"),
            KIND_DM,
        )
        act._sent_event_ids.add("gw1")
        rendered = []
        act._load_and_render = lambda: rendered.append(True)

        echo = _FakeNostrEvent(
            public_key="own123",
            event_id="gw1",
            kind=KIND_NIP17_CHAT,
            tags=[["p", "peer456"]],
        )
        act._on_event(echo)

        self.assertEqual(rendered, [])

    def test_on_event_persists_and_triggers_render(self):
        """Incoming message is persisted to the store and triggers a re-render."""
        channel_id = "chan42"
        chat_id = channel_chat_id(channel_id)
        act = self._activity("own123", chat_id, KIND_CHANNEL_MESSAGE)
        rendered = []
        act._load_and_render = lambda: rendered.append(True)

        own_channel_event = _FakeNostrEvent(
            public_key="own123",
            event_id="event_from_other_client",
            kind=KIND_CHANNEL_MESSAGE,
            content="from amethyst",
            tags=[["e", channel_id, "", "root"]],
        )
        act._on_event(own_channel_event)

        self.assertEqual(len(rendered), 1)
        stored = act._store.load_messages(chat_id)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].content, "from amethyst")

    def test_on_event_marks_own_nip17_as_outgoing_after_recreation(self):
        """A relay echo from the local key must show as outgoing even when the
        per-instance _sent_event_ids set has been lost (e.g. activity recreated).
        """
        own = "own123"
        peer = "peer456"
        chat_id = dm_chat_id(own, peer)
        act = self._activity(own, chat_id, KIND_DM)
        act._sent_event_ids = set()
        rendered = []
        act._load_and_render = lambda: rendered.append(True)

        echo = _FakeNostrEvent(
            public_key=own,
            event_id="gw1",
            kind=KIND_NIP17_CHAT,
            content="from mpy",
            tags=[["p", peer]],
        )
        act._on_event(echo)

        self.assertEqual(len(rendered), 1)
        stored = act._store.load_messages(chat_id)
        self.assertEqual(len(stored), 1)
        self.assertTrue(stored[0].outgoing)
        self.assertEqual(stored[0].content, "from mpy")


class _FakeSendResult:
    def __init__(self, ids, failed=None):
        self.ids = list(ids)
        self.local_id = self.ids[0] if self.ids else None
        self.published = [("x", i) for i in self.ids]
        self.failed = list(failed or [])


class _AsyncFakeManager(_FakeManager):
    def __init__(self, own_pubkey=None, result=None):
        super().__init__(own_pubkey)
        self.calls = []
        self.result = result or _FakeSendResult(["self_wrap", "peer_wrap"])

    def is_connected(self):
        return True

    async def publish_nip17_message_async(
        self, content, recipients, subject=None, reply_to=None, created_at=None, progress=None
    ):
        self.calls.append({
            "content": content,
            "recipients": list(recipients),
            "subject": subject,
            "created_at": created_at,
        })
        if progress:
            progress(1, 2)
            progress(2, 2)
        return self.result


class _GroupStore(_FakeStore):
    def __init__(self, chat):
        super().__init__()
        self.chat = chat
        self.queued = []
        self.subjects = []

    def get_chat(self, chat_id):
        return self.chat if chat_id == self.chat.chat_id else None

    def queue_outgoing(self, chat_id, content, kind, recipient_pubkey=None,
                       channel_id=None, participants=None, subject=None):
        self.queued.append({
            "chat_id": chat_id, "content": content, "kind": kind,
            "participants": participants, "subject": subject,
        })
        return None

    def update_chat_subject(self, chat_id, subject, ts=0):
        self.subjects.append((chat_id, subject, ts))


class _FakeConnectivity:
    online = True

    @classmethod
    def get(cls):
        return cls

    @classmethod
    def is_online(cls):
        return cls.online


class _FakeWidget:
    def __init__(self):
        self.texts = []

    def set_text(self, text):
        self.texts.append(text)

    def get_text(self):
        return ""

    def has_flag(self, flag):
        return True

    def hide_keyboard(self):
        pass


class TestChatActivityGroupSend(unittest.TestCase):
    """Sending in a NIP-17 group: subject, progress, yielding publish, dedupe."""

    def setUp(self):
        self._orig_connectivity = chat_activity_module.ConnectivityManager
        chat_activity_module.ConnectivityManager = _FakeConnectivity
        _FakeConnectivity.online = True

    def tearDown(self):
        chat_activity_module.ConnectivityManager = self._orig_connectivity

    def _activity(self, chat, own="a" * 64, result=None):
        act = object.__new__(ChatActivity)
        act._kind = KIND_NIP17_CHAT
        act._chat_id = chat.chat_id
        act._peer_pubkey = None
        act._manager = _AsyncFakeManager(own_pubkey=own, result=result)
        act._store = _GroupStore(chat)
        act._sent_event_ids = set()
        act._rendered_ids = set()
        act._input_textarea = _FakeWidget()
        act._keyboard = _FakeWidget()
        act._title_label = _FakeWidget()
        act.labels = []
        act._set_sending_state = lambda label, disabled: act.labels.append(label)
        act.rows = []
        act._append_message_row = lambda message: act.rows.append(message)
        act._request_scroll_to_bottom = lambda: None
        return act

    def test_group_send_passes_subject_shows_progress_and_stores_under_own_wrap(self):
        chat = Chat.nip17_group(["c" * 64, "b" * 64], subject="Room")
        act = self._activity(chat)
        asyncio.run(act._send_async("hello room"))

        call = act._manager.calls[0]
        self.assertEqual(call["content"], "hello room")
        self.assertEqual(call["recipients"], ["c" * 64, "b" * 64])
        self.assertEqual(call["subject"], "Room")
        self.assertTrue(isinstance(call["created_at"], int))
        self.assertIn("Encrypting 1/2", act.labels)
        self.assertIn("Encrypting 2/2", act.labels)
        self.assertEqual(act.labels[-1], "Send")

        stored = act._store.load_messages(chat.chat_id)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].event_id, "self_wrap")
        self.assertTrue(stored[0].outgoing)
        self.assertIn("self_wrap", act._sent_event_ids)
        self.assertIn("peer_wrap", act._sent_event_ids)
        self.assertEqual(len(act.rows), 1)

    def test_group_without_subject_sends_no_subject(self):
        chat = Chat.nip17_group(["b" * 64, "c" * 64])
        act = self._activity(chat)
        asyncio.run(act._send_async("plain"))
        self.assertEqual(act._manager.calls[0]["subject"], None)

    def test_partial_failure_still_stores_message(self):
        chat = Chat.nip17_group(["b" * 64, "c" * 64], subject="Room")
        act = self._activity(chat, result=_FakeSendResult(["self_wrap", "w2"], failed=["c" * 64]))
        asyncio.run(act._send_async("partly"))
        stored = act._store.load_messages(chat.chat_id)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].event_id, "self_wrap")

    def test_offline_group_send_queues_with_subject(self):
        _FakeConnectivity.online = False
        chat = Chat.nip17_group(["b" * 64, "c" * 64], subject="Room")
        act = self._activity(chat)
        asyncio.run(act._send_async("later"))
        self.assertEqual(act._manager.calls, [])
        self.assertEqual(len(act._store.queued), 1)
        self.assertEqual(act._store.queued[0]["subject"], "Room")
        self.assertEqual(act._store.queued[0]["participants"], ["b" * 64, "c" * 64])

    def test_incoming_subject_renames_open_group_chat(self):
        chat = Chat.nip17_group(["b" * 64, "c" * 64], subject="Old")
        act = self._activity(chat)
        act._load_and_render = lambda: None
        event = _FakeNostrEvent(
            public_key="b" * 64,
            event_id="ev_subject",
            content="rename",
            created_at=1700000000,
            tags=[["p", "a" * 64], ["p", "c" * 64], ["subject", "New"]],
        )
        act._on_event(event)
        self.assertEqual(act._store.subjects, [(chat.chat_id, "New", 1700000000)])
        self.assertEqual(act._title_label.texts[-1], "New")


if __name__ == "__main__":
    unittest.main()
