import os
import sys
import unittest

sys.path.append("apps")

from com_micropythonos_nostr.chat_model import KIND_DM, Message
from com_micropythonos_nostr.event_store import EventStore


class TestEventStoreDmIndexRebuild(unittest.TestCase):
    """DMs with persisted messages must be listed even when index.last_ts is stale."""

    def setUp(self):
        self.app_name = "com.test.dm_index_rebuild"
        EventStore._instances.pop(self.app_name, None)
        self._cleanup()

    def tearDown(self):
        EventStore._instances.pop(self.app_name, None)
        self._cleanup()

    def _cleanup(self):
        import shutil
        try:
            shutil.rmtree(f"prefs/{self.app_name}")
        except OSError:
            pass

    def test_stale_index_rebuilds_from_messages(self):
        store = EventStore(self.app_name)
        chat = store.get_or_create_dm("a" * 64, "b" * 64)
        chat_id = chat.chat_id

        # Persist a message but simulate a hard reset that did not flush metadata.
        store.add_message(
            chat_id,
            Message(event_id="e1", ts=1700000000, pubkey="b" * 64, content="hello", kind=KIND_DM),
            mark_unread=False,
        )
        store.flush_index()

        # Corrupt the index back to "stale" (as after a crash before flush).
        store._index["chats"][chat_id]["last_ts"] = 0
        store._index["chats"][chat_id]["last_preview"] = ""
        store.flush_index()

        # Creating a fresh store reads the corrupt index and must rebuild from disk.
        EventStore._instances.pop(self.app_name, None)
        fresh = EventStore(self.app_name)
        chats = fresh.get_chats()
        self.assertEqual(len(chats), 1)
        self.assertEqual(chats[0].chat_id, chat_id)
        self.assertEqual(chats[0].last_ts, 1700000000)
        self.assertEqual(chats[0].last_preview, "hello")
