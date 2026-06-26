"""Unit tests for NIP-17 group chat creation and outgoing queue layout."""

import os
import shutil
import sys
import unittest

sys.path.append("apps")

from com_micropythonos_nostr.chat_model import KIND_NIP17_CHAT, Chat, Message
from com_micropythonos_nostr.event_store import EventStore


class TestEventStoreNip17(unittest.TestCase):
    """NIP-17 group chats and outgoing queue participants."""

    def setUp(self):
        self.app_name = "com.test.store_nip17"
        EventStore._instances.pop(self.app_name, None)
        self._cleanup()

    def tearDown(self):
        EventStore._instances.pop(self.app_name, None)
        self._cleanup()

    def _cleanup(self):
        try:
            shutil.rmtree(f"prefs/{self.app_name}")
        except OSError:
            pass

    def test_get_or_create_nip17_group_sets_participants(self):
        store = EventStore(self.app_name)
        participants = ["a" * 64, "b" * 64]
        chat = store.get_or_create_nip17_group(participants, title="Alpha")
        self.assertEqual(chat.kind, KIND_NIP17_CHAT)
        self.assertEqual(chat.title, "Alpha")
        self.assertEqual(sorted(chat.participants), sorted(participants))
        self.assertTrue(chat.chat_id.startswith("nip17_"))

    def test_queue_outgoing_stores_participants(self):
        store = EventStore(self.app_name)
        chat = store.get_or_create_nip17_group(["a" * 64, "b" * 64])
        store.queue_outgoing(
            chat.chat_id,
            "group message",
            kind=KIND_NIP17_CHAT,
            participants=["a" * 64, "b" * 64],
        )
        outbox = store.load_outbox()
        self.assertEqual(len(outbox), 1)
        self.assertEqual(outbox[0]["content"], "group message")
        self.assertEqual(outbox[0]["kind"], KIND_NIP17_CHAT)
        self.assertEqual(sorted(outbox[0]["participants"]), ["a" * 64, "b" * 64])

    def test_queued_message_is_marked_outgoing(self):
        store = EventStore(self.app_name)
        chat = store.get_or_create_nip17_group(["a" * 64, "b" * 64])
        store.queue_outgoing(
            chat.chat_id,
            "queued",
            kind=KIND_NIP17_CHAT,
            participants=["a" * 64, "b" * 64],
        )
        messages = store.load_messages(chat.chat_id)
        self.assertEqual(len(messages), 1)
        self.assertTrue(messages[0].outgoing)
        self.assertTrue(messages[0].queued)

    def test_nip17_group_id_is_stable(self):
        store = EventStore(self.app_name)
        chat1 = store.get_or_create_nip17_group(["b" * 64, "a" * 64])
        chat2 = store.get_or_create_nip17_group(["a" * 64, "b" * 64])
        self.assertEqual(chat1.chat_id, chat2.chat_id)


if __name__ == "__main__":
    unittest.main()
