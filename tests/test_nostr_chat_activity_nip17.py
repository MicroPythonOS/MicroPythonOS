"""Regression tests for NIP-17 and DM live event handling in ChatActivity."""
import unittest

import sys

sys.path.insert(0, "lib")
sys.path.insert(0, "apps/com_micropythonos_nostr")

from apps.com_micropythonos_nostr.chat_activity import ChatActivity
from apps.com_micropythonos_nostr.chat_model import (
    KIND_CHANNEL_MESSAGE,
    KIND_DM,
    KIND_NIP17_CHAT,
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


if __name__ == "__main__":
    unittest.main()
