"""Unit tests for NIP-17 chat id routing in chat_model.py."""

import sys
import unittest

sys.path.append("apps")

from com_micropythonos_nostr.chat_model import (
    KIND_DM,
    KIND_NIP17_CHAT,
    Chat,
    chat_id_for_event,
    dm_chat_id,
    nip17_group_chat_id,
    participants_from_nip17_event,
    subject_from_nip17_event,
)


class _FakeEvent:
    def __init__(self, kind, pubkey, tags, content=""):
        self.kind = kind
        self.public_key = pubkey
        self.pubkey = pubkey
        self.tags = tags
        self.content = content


class TestChatModelNip17(unittest.TestCase):
    """Routing NIP-17 kind 14 events to DM or group chat ids."""

    def test_one_to_one_nip17_maps_to_dm_chat_id(self):
        own = "a" * 64
        peer = "b" * 64
        event = _FakeEvent(
            KIND_NIP17_CHAT,
            peer,
            [["p", own]],
        )
        chat_id = chat_id_for_event(event, own)
        self.assertEqual(chat_id, dm_chat_id(own, peer))

    def test_group_nip17_maps_to_nip17_group_id(self):
        own = "a" * 64
        peer1 = "b" * 64
        peer2 = "c" * 64
        event = _FakeEvent(
            KIND_NIP17_CHAT,
            peer1,
            [["p", own], ["p", peer2]],
        )
        chat_id = chat_id_for_event(event, own)
        expected_participants = sorted([peer1, peer2])
        self.assertEqual(chat_id, nip17_group_chat_id(expected_participants))

    def test_participants_excludes_own_pubkey(self):
        own = "a" * 64
        peer1 = "b" * 64
        peer2 = "c" * 64
        event = _FakeEvent(
            KIND_NIP17_CHAT,
            peer1,
            [["p", own], ["p", peer2]],
        )
        participants = participants_from_nip17_event(event, own)
        self.assertEqual(participants, sorted([peer1, peer2]))

    def test_subject_from_event(self):
        event = _FakeEvent(
            KIND_NIP17_CHAT,
            "b" * 64,
            [["p", "a" * 64], ["subject", "Project X"]],
        )
        self.assertEqual(subject_from_nip17_event(event), "Project X")

    def test_chat_nip17_group_title_defaults_to_participants(self):
        chat = Chat.nip17_group(["b" * 64, "c" * 64])
        self.assertEqual(chat.kind, KIND_NIP17_CHAT)
        self.assertIn("bbbbbbbb", chat.title)
        self.assertIn("cccccccc", chat.title)

    def test_chat_nip17_group_keeps_explicit_title(self):
        chat = Chat.nip17_group(["b" * 64], title="Direct NIP-17")
        self.assertEqual(chat.title, "Direct NIP-17")


if __name__ == "__main__":
    unittest.main()
