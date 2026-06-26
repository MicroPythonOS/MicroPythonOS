"""Regression tests for NIP-17 live updates in ChatActivity."""
import unittest

import sys

sys.path.insert(0, "lib")
sys.path.insert(0, "apps/com_micropythonos_nostr")

from apps.com_micropythonos_nostr.chat_activity import ChatActivity
from apps.com_micropythonos_nostr.chat_model import KIND_DM, KIND_NIP17_CHAT


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
    def test_on_event_skips_self_authored_messages(self):
        act = object.__new__(ChatActivity)
        act._manager = _FakeManager(own_pubkey="own123")
        act._chat_id = "dm_own123_peer456"
        act._kind = KIND_DM
        act._store = None
        act._rendered_ids = set()
        appended = []
        act._append_message_row = lambda msg: appended.append(msg)

        own_event = _FakeNostrEvent(public_key="own123", event_id="gw1")
        act._on_event(own_event)

        self.assertEqual(appended, [])


if __name__ == "__main__":
    unittest.main()
