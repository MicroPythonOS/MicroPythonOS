"""Unit tests for NIP-17 group chat creation, outgoing queue layout, the
file names of large rooms and the dedupe of a flushed message's relay echo."""

import os
import shutil
import sys
import unittest

sys.path.append("apps")

from com_micropythonos_nostr.chat_model import (
    KIND_NIP17_CHAT,
    MAX_GROUP_MEMBERS,
    Chat,
    Message,
    nip17_group_chat_id,
)
from com_micropythonos_nostr.event_store import (
    HASHED_CHAT_FILE_PREFIX,
    MAX_VERBATIM_CHAT_FILENAME,
    EventStore,
)


def _members(n):
    return [("%02x" % i) * 32 for i in range(1, n + 1)]


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

    def test_get_or_create_nip17_group_stores_subject(self):
        store = EventStore(self.app_name)
        chat = store.get_or_create_nip17_group(["a" * 64, "b" * 64], subject="Alpha")
        self.assertEqual(chat.subject, "Alpha")
        self.assertEqual(chat.title, "Alpha")
        again = store.get_chat(chat.chat_id)
        self.assertEqual(again.subject, "Alpha")

    def test_update_chat_subject_sets_title_subject_and_ts(self):
        store = EventStore(self.app_name)
        chat = store.get_or_create_nip17_group(["a" * 64, "b" * 64])
        store.update_chat_subject(chat.chat_id, "Renamed", ts=42)
        again = store.get_chat(chat.chat_id)
        self.assertEqual(again.subject, "Renamed")
        self.assertEqual(again.title, "Renamed")
        self.assertEqual(again.subject_ts, 42)

    def test_queue_outgoing_stores_subject(self):
        store = EventStore(self.app_name)
        chat = store.get_or_create_nip17_group(["a" * 64, "b" * 64], subject="Alpha")
        store.queue_outgoing(
            chat.chat_id,
            "queued with subject",
            kind=KIND_NIP17_CHAT,
            participants=["a" * 64, "b" * 64],
            subject="Alpha",
        )
        outbox = store.load_outbox()
        self.assertEqual(outbox[0]["subject"], "Alpha")

    def test_nip17_group_id_is_stable(self):
        store = EventStore(self.app_name)
        chat1 = store.get_or_create_nip17_group(["b" * 64, "a" * 64])
        chat2 = store.get_or_create_nip17_group(["a" * 64, "b" * 64])
        self.assertEqual(chat1.chat_id, chat2.chat_id)


class TestGroupChatFilePaths(unittest.TestCase):
    """A room id is "nip17_" + every member's hex pubkey, 271 chars from 4
    members on, while file names are capped at 255 bytes (LittleFS, FAT,
    APFS). Large rooms are stored under a hash of the id; small rooms, DMs
    and channels keep their verbatim file names."""

    def setUp(self):
        self.app_name = "com.test.store_group_paths"
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

    def _message(self, event_id="e1"):
        return Message(
            event_id=event_id, ts=1700000000, pubkey="b" * 64, content="hi", kind=KIND_NIP17_CHAT
        )

    def test_small_rooms_keep_verbatim_file_names(self):
        store = EventStore(self.app_name)
        for n in (2, 3):
            chat = store.get_or_create_nip17_group(_members(n))
            self.assertTrue(len(chat.chat_id) <= MAX_VERBATIM_CHAT_FILENAME)
            self.assertTrue(store._chat_path(chat.chat_id).endswith(chat.chat_id + ".jsonl"))
            self.assertTrue(store.add_message(chat.chat_id, self._message("e%d" % n)))
        dm = store.get_or_create_dm("a" * 64, "b" * 64)
        self.assertTrue(store._chat_path(dm.chat_id).endswith(dm.chat_id + ".jsonl"))

    def test_four_member_room_persists_a_message(self):
        store = EventStore(self.app_name)
        chat = store.get_or_create_nip17_group(_members(4))
        self.assertTrue(len(chat.chat_id) > 255)
        self.assertTrue(store.add_message(chat.chat_id, self._message()))
        self.assertEqual([m.content for m in store.load_messages(chat.chat_id)], ["hi"])
        name = store._chat_path(chat.chat_id).split("/")[-1]
        self.assertTrue(name.startswith(HASHED_CHAT_FILE_PREFIX))
        self.assertTrue(len(name) < 100)

    def test_max_member_room_queues_an_offline_message(self):
        store = EventStore(self.app_name)
        members = _members(MAX_GROUP_MEMBERS)
        chat = store.get_or_create_nip17_group(members, subject="Room")
        queued = store.queue_outgoing(
            chat.chat_id, "later", KIND_NIP17_CHAT, participants=members, subject="Room"
        )
        self.assertTrue(queued.queued)
        self.assertEqual(len(store.load_outbox()), 1)
        self.assertEqual(len(store.load_messages(chat.chat_id)), 1)

    def test_max_member_room_survives_a_restart(self):
        store = EventStore(self.app_name)
        chat = store.get_or_create_nip17_group(_members(MAX_GROUP_MEMBERS))
        store.add_message(chat.chat_id, self._message())
        store.flush_index()
        EventStore._instances.pop(self.app_name, None)
        fresh = EventStore(self.app_name)
        self.assertEqual(len(fresh.load_messages(chat.chat_id)), 1)
        # The dedup cache is rebuilt from disk, hashed file names included.
        self.assertFalse(fresh.add_message(chat.chat_id, self._message()))
        # The chat list summary is rebuilt through the index, not the file name.
        again = fresh.get_chat(chat.chat_id)
        self.assertEqual(again.last_preview, "hi")

    def test_summary_rebuild_finds_a_hashed_file_after_an_index_lag(self):
        store = EventStore(self.app_name)
        chat = store.get_or_create_nip17_group(_members(5))
        store.add_message(chat.chat_id, self._message())
        # Simulate the index lagging behind the JSONL file (hard reset before a
        # flush): persist the chat entry without its last_ts/preview.
        entry = store._index["chats"][chat.chat_id]
        entry["last_ts"] = 0
        entry["last_preview"] = ""
        store._index_dirty = True
        store.flush_index()
        EventStore._instances.pop(self.app_name, None)
        fresh = EventStore(self.app_name)
        self.assertEqual(fresh.get_chat(chat.chat_id).last_ts, 1700000000)


class TestOutboxFlushDedup(unittest.TestCase):
    """Every NIP-17 message is also gift-wrapped to the sender, so the relay
    echoes the sender's wrap back; a message published from the outbox is
    stored under that wrap id and the echo must deduplicate."""

    def setUp(self):
        self.app_name = "com.test.store_outbox_echo"
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

    def _queue(self, store, chat, content):
        return store.queue_outgoing(
            chat.chat_id, content, KIND_NIP17_CHAT, participants=chat.participants, subject="Room"
        )

    def test_echo_of_flushed_message_is_not_new_and_does_not_bump_unread(self):
        store = EventStore(self.app_name)
        own = "a" * 64
        chat = store.get_or_create_nip17_group(["b" * 64, "c" * 64], subject="Room")
        placeholder = self._queue(store, chat, "queued")

        published = Message(
            event_id="ownwrap1", ts=placeholder.ts, pubkey=own, content="queued",
            kind=KIND_NIP17_CHAT, outgoing=True, queued=False,
        )
        self.assertTrue(store.replace_message(chat.chat_id, placeholder.event_id, published))

        echo = Message(
            event_id="ownwrap1", ts=placeholder.ts, pubkey=own, content="queued",
            kind=KIND_NIP17_CHAT, outgoing=True,
        )
        self.assertFalse(store.add_message(chat.chat_id, echo, mark_unread=True))
        self.assertEqual(store.get_chat(chat.chat_id).unread, 0)
        self.assertEqual(len(store.load_messages(chat.chat_id)), 1)
        with open(store._chat_path(chat.chat_id)) as f:
            lines = [line for line in f.read().split("\n") if line.strip()]
        self.assertEqual(len(lines), 1)

    def test_remove_outbox_item_keeps_the_others(self):
        store = EventStore(self.app_name)
        chat = store.get_or_create_nip17_group(["b" * 64, "c" * 64], subject="Room")
        first = self._queue(store, chat, "one")
        store.queue_outgoing(chat.chat_id, "two", KIND_NIP17_CHAT, participants=chat.participants)
        self.assertTrue(store.remove_outbox_item(first.event_id))
        self.assertEqual([i["content"] for i in store.load_outbox()], ["two"])
        self.assertFalse(store.remove_outbox_item("out:nope"))
        self.assertTrue(store.remove_outbox_item(store.load_outbox()[0]["placeholder_id"]))
        self.assertEqual(store.load_outbox(), [])

    def test_two_messages_queued_in_the_same_second_get_distinct_placeholders(self):
        store = EventStore(self.app_name)
        chat = store.get_or_create_nip17_group(["b" * 64, "c" * 64])
        first = self._queue(store, chat, "one")
        second = self._queue(store, chat, "two")
        self.assertTrue(first.event_id != second.event_id)
        self.assertEqual([m.content for m in store.load_messages(chat.chat_id)], ["one", "two"])
        self.assertEqual(
            [i["placeholder_id"] for i in store.load_outbox()], [first.event_id, second.event_id]
        )

    def test_remove_message_forgets_the_id(self):
        store = EventStore(self.app_name)
        chat = store.get_or_create_nip17_group(["b" * 64, "c" * 64])
        message = Message(
            event_id="ownwrap2", ts=1700000000, pubkey="a" * 64, content="x",
            kind=KIND_NIP17_CHAT, outgoing=True,
        )
        store.add_message(chat.chat_id, message)
        self.assertTrue(store.remove_message(chat.chat_id, "ownwrap2"))
        self.assertEqual(store.load_messages(chat.chat_id), [])
        self.assertFalse(store.remove_message(chat.chat_id, "ownwrap2"))
        # Storing it again is allowed: the id was forgotten.
        self.assertTrue(store.add_message(chat.chat_id, message))


if __name__ == "__main__":
    unittest.main()
