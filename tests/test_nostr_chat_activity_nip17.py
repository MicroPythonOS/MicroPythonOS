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
    Message,
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
        # Like EventStore: a known id is not stored twice.
        if any(m.event_id == message.event_id for m in self.messages.get(chat_id, [])):
            return False
        self.messages.setdefault(chat_id, []).append(message)
        return True

    def remove_message(self, chat_id, event_id):
        before = len(self.messages.get(chat_id, []))
        self.messages[chat_id] = [m for m in self.messages.get(chat_id, []) if m.event_id != event_id]
        return len(self.messages[chat_id]) != before

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
    def __init__(self, ids, failed=None, local_id=None):
        self.ids = list(ids)
        self.local_id = local_id or (self.ids[0] if self.ids else None)
        self.published = [("x", i) for i in self.ids]
        self.failed = list(failed or [])


class _AsyncFakeManager(_FakeManager):
    """Mimics NostrManager.publish_nip17_message_async: reports the sender's
    wrap id through on_local_id before "publishing", yields once per wrap and
    lets a test hook run inside that yield (where the relay echo arrives)."""

    def __init__(self, own_pubkey=None, result=None):
        super().__init__(own_pubkey)
        self.calls = []
        self.result = result or _FakeSendResult(["self_wrap", "peer_wrap"])
        self.during_send = None  # callable run while the send is in flight
        self.raise_after_local_id = None

    def is_connected(self):
        return True

    async def publish_nip17_message_async(
        self, content, recipients, subject=None, reply_to=None, created_at=None,
        progress=None, on_local_id=None,
    ):
        self.calls.append({
            "content": content,
            "recipients": list(recipients),
            "subject": subject,
            "created_at": created_at,
        })
        total = len(self.result.ids) + len(self.result.failed)
        if progress:
            progress(1, total)
        if on_local_id:
            on_local_id(self.result.local_id)
        if self.raise_after_local_id:
            raise self.raise_after_local_id
        await asyncio.sleep_ms(0)
        if self.during_send:
            self.during_send()
        if progress:
            for i in range(2, total + 1):
                progress(i, total)
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
        placeholder = Message(
            event_id="out:%s" % len(self.queued), ts=1, pubkey="", content=content,
            kind=kind, outgoing=True, queued=True,
        )
        self.add_message(chat_id, placeholder)
        return placeholder

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


class _DeletedWidget:
    """What an LVGL widget is after the screen was cleaned: every call raises."""

    def set_text(self, text):
        raise RuntimeError("Referenced object was deleted!")

    def get_text(self):
        raise RuntimeError("Referenced object was deleted!")

    def has_flag(self, flag):
        raise RuntimeError("Referenced object was deleted!")

    def hide_keyboard(self):
        raise RuntimeError("Referenced object was deleted!")


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
        act._has_foreground = True
        act._input_textarea = _FakeWidget()
        act._keyboard = _FakeWidget()
        act._title_label = _FakeWidget()
        act.labels = []
        act._set_sending_state = lambda label, disabled: act.labels.append(label)
        act.rows = []

        def append_row(message):
            act._rendered_ids.add(message.event_id)
            act.rows.append(message)

        def load_and_render():
            # Mirrors ChatActivity._load_and_render without LVGL.
            act.rows = []
            act._rendered_ids = set()
            for msg in act._store.load_messages(chat.chat_id):
                append_row(msg)

        act._append_message_row = append_row
        act._load_and_render = load_and_render
        act._request_scroll_to_bottom = lambda: None
        return act

    def _echo(self, act, chat, content, event_id="self_wrap", created_at=1700000000):
        """The relay's echo of the sender's own gift wrap, as _on_event sees it."""
        act._on_event(_FakeNostrEvent(
            public_key="a" * 64,
            event_id=event_id,
            content=content,
            created_at=created_at,
            tags=[["p", m] for m in chat.participants],
        ))

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

    def test_local_copy_is_stored_and_known_before_the_wraps_go_out(self):
        chat = Chat.nip17_group(["b" * 64, "c" * 64], subject="Room")
        act = self._activity(chat)
        state = {}

        def during_send():
            # Inside the first yield: the own wrap is built (and its id
            # reported) but the recipients' wraps are still being encrypted.
            state["known"] = "self_wrap" in act._sent_event_ids
            state["stored"] = [m.event_id for m in act._store.load_messages(chat.chat_id)]

        act._manager.during_send = during_send
        asyncio.run(act._send_async("hello room"))
        self.assertTrue(state["known"])
        self.assertEqual(state["stored"], ["self_wrap"])

    def test_own_wrap_echo_during_send_is_rendered_once(self):
        # Reviewer's repro: the relay echoes the sender's wrap while the send
        # still yields between the other wraps.
        chat = Chat.nip17_group(["b" * 64, "c" * 64], subject="Room")
        act = self._activity(chat)
        act._manager.during_send = lambda: self._echo(act, chat, "hello room")
        asyncio.run(act._send_async("hello room"))

        stored = act._store.load_messages(chat.chat_id)
        self.assertEqual([m.event_id for m in stored], ["self_wrap"])
        self.assertTrue(stored[0].outgoing)
        self.assertEqual(
            [m.event_id for m in act.rows], ["self_wrap"],
            "message rendered more than once: %s" % [m.event_id for m in act.rows],
        )

    def test_leaving_the_chat_during_a_send_keeps_the_message_and_skips_the_widgets(self):
        chat = Chat.nip17_group(["b" * 64, "c" * 64], subject="Room")
        act = self._activity(chat)

        def leave():
            # Back press mid-send: onPause clears the foreground flag and the
            # screen (with every widget) is deleted.
            act._has_foreground = False
            act._input_textarea = _DeletedWidget()
            act._keyboard = _DeletedWidget()
            act._append_message_row = lambda message: (_ for _ in ()).throw(
                RuntimeError("Referenced object was deleted!")
            )

        act._manager.during_send = leave
        asyncio.run(act._send_async("gone"))

        stored = act._store.load_messages(chat.chat_id)
        self.assertEqual([m.event_id for m in stored], ["self_wrap"])
        self.assertIn("self_wrap", act._sent_event_ids)
        # The progress/state labels stop once the screen is gone.
        self.assertFalse("Send" in act.labels[1:])

    def test_total_publish_failure_queues_the_message_once(self):
        chat = Chat.nip17_group(["b" * 64, "c" * 64], subject="Room")
        act = self._activity(chat)
        act._manager.raise_after_local_id = RuntimeError("could not be published to anyone")
        asyncio.run(act._send_async("later"))

        self.assertEqual(len(act._store.queued), 1)
        stored = act._store.load_messages(chat.chat_id)
        # Only the queued placeholder remains; the optimistic copy under the
        # never-published wrap id is gone and its id is forgotten.
        self.assertEqual(len(stored), 1)
        self.assertTrue(stored[0].queued)
        self.assertFalse("self_wrap" in act._sent_event_ids)

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
