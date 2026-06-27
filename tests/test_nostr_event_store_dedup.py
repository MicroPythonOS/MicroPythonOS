"""Regression tests for EventStore deduplication across restarts."""

import os
import shutil
import sys
import unittest

sys.path.append("apps")

from com_micropythonos_nostr.chat_model import KIND_DM, Message
from com_micropythonos_nostr.event_store import EventStore


class TestEventStoreDeduplication(unittest.TestCase):
    """Previously-stored messages must not be treated as new after restart."""

    def setUp(self):
        self.app_name = "com.test.store_dedup"
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

    def test_new_store_recognizes_persisted_event_ids(self):
        chat_id = "dm_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        event_id = "e" * 64

        first_store = EventStore(self.app_name)
        first_store.add_message(
            chat_id,
            Message(
                event_id=event_id,
                ts=1700000000,
                pubkey="a" * 64,
                content="hello",
                kind=KIND_DM,
            ),
            mark_unread=True,
        )
        first_store.flush_index()
        self.assertEqual(first_store.get_chat(chat_id).unread, 1)

        # Simulate restart: a fresh EventStore instance for the same app.
        EventStore._instances.pop(self.app_name, None)
        second_store = EventStore(self.app_name)
        is_new = second_store.add_message(
            chat_id,
            Message(
                event_id=event_id,
                ts=1700000000,
                pubkey="a" * 64,
                content="hello",
                kind=KIND_DM,
            ),
            mark_unread=True,
        )
        self.assertFalse(is_new)
        self.assertEqual(second_store.get_chat(chat_id).unread, 1)

    def test_persisted_and_new_messages_mixed(self):
        chat_id = "dm_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        old_id = "o" * 64
        new_id = "n" * 64

        first_store = EventStore(self.app_name)
        first_store.add_message(
            chat_id,
            Message(
                event_id=old_id,
                ts=1700000000,
                pubkey="a" * 64,
                content="old",
                kind=KIND_DM,
            ),
            mark_unread=True,
        )
        first_store.flush_index()

        EventStore._instances.pop(self.app_name, None)
        second_store = EventStore(self.app_name)
        self.assertFalse(
            second_store.add_message(
                chat_id,
                Message(
                    event_id=old_id,
                    ts=1700000000,
                    pubkey="a" * 64,
                    content="old",
                    kind=KIND_DM,
                ),
                mark_unread=True,
            )
        )
        self.assertTrue(
            second_store.add_message(
                chat_id,
                Message(
                    event_id=new_id,
                    ts=1700000100,
                    pubkey="a" * 64,
                    content="new",
                    kind=KIND_DM,
                ),
                mark_unread=True,
            )
        )
        self.assertEqual(second_store.get_chat(chat_id).unread, 2)


if __name__ == "__main__":
    unittest.main()
