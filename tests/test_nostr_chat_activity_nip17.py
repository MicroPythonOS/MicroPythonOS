"""Regression tests for NIP-17 live updates in ChatActivity."""
import unittest

import sys

sys.path.insert(0, "lib")
sys.path.insert(0, "apps/com_micropythonos_nostr")

from apps.com_micropythonos_nostr.chat_activity import ChatActivity
from apps.com_micropythonos_nostr.chat_model import KIND_DM, KIND_NIP17_CHAT


class _FakeManager:
    def __init__(self):
        self.registered = []
        self.unregistered = []

    def register_event_handler(self, kind, callback):
        self.registered.append((kind, callback))

    def unregister_event_handler(self, kind, callback):
        self.unregistered.append((kind, callback))


class TestChatActivityRegistersNip17Handler(unittest.TestCase):
    def _activity(self, kind):
        act = object.__new__(ChatActivity)
        act._handler_registered = False
        act._kind = kind
        act._manager = _FakeManager()
        return act

    def test_dm_chat_also_registers_nip17_handler(self):
        act = self._activity(KIND_DM)
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
        act = self._activity(KIND_NIP17_CHAT)
        act._register_handler()
        self.assertTrue(act._handler_registered)
        kinds = [k for k, _ in act._manager.registered]
        self.assertEqual(kinds, [KIND_NIP17_CHAT])

    def test_dm_chat_unregisters_both_handlers(self):
        act = self._activity(KIND_DM)
        act._register_handler()
        act._handler_registered = True
        act._unregister_handler()
        self.assertFalse(act._handler_registered)
        kinds = [k for k, _ in act._manager.unregistered]
        self.assertIn(KIND_DM, kinds)
        self.assertIn(KIND_NIP17_CHAT, kinds)


if __name__ == "__main__":
    unittest.main()
