"""Unit tests for NIP-17 chat id routing in chat_model.py."""

import sys
import unittest

sys.path.append("apps")

from com_micropythonos_nostr.chat_model import (
    KIND_DM,
    KIND_NIP17_CHAT,
    MAX_GROUP_MEMBERS,
    Chat,
    apply_nip17_subject,
    chat_id_for_event,
    dm_chat_id,
    nip17_group_chat_id,
    normalize_group_members,
    participants_from_nip17_event,
    subject_from_nip17_event,
)


class _FakeEvent:
    def __init__(self, kind, pubkey, tags, content="", created_at=0):
        self.kind = kind
        self.public_key = pubkey
        self.pubkey = pubkey
        self.tags = tags
        self.content = content
        self.created_at = created_at


class _FakeStore:
    def __init__(self):
        self.subjects = []

    def update_chat_subject(self, chat_id, subject, ts=0):
        self.subjects.append((chat_id, subject, ts))


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
        self.assertTrue(chat.title.startswith("npub1"))
        self.assertIn(", npub1", chat.title)

    def test_chat_nip17_group_keeps_explicit_title(self):
        chat = Chat.nip17_group(["b" * 64], title="Direct NIP-17")
        self.assertEqual(chat.title, "Direct NIP-17")


class TestGroupMemberNormalisation(unittest.TestCase):
    """Member lists typed into the 'Group' mode of NewChatActivity."""

    own = "a" * 64

    def test_strips_own_key_dedupes_and_sorts(self):
        raw = "{c}, {b}\n{a},{c}".format(a="a" * 64, b="b" * 64, c="c" * 64)
        members, error = normalize_group_members(raw, self.own)
        self.assertEqual(error, None)
        self.assertEqual(members, ["b" * 64, "c" * 64])

    def test_accepts_npub_tokens(self):
        from nostr.key import PublicKey

        npub = PublicKey(bytes.fromhex("b" * 64)).bech32()
        members, error = normalize_group_members("%s\n%s" % (npub, "c" * 64), self.own)
        self.assertEqual(error, None)
        self.assertEqual(members, ["b" * 64, "c" * 64])

    def test_rejects_unparseable_token(self):
        members, error = normalize_group_members("%s, not-a-key" % ("b" * 64), self.own)
        self.assertEqual(members, None)
        self.assertIn("not-a-key", error)

    def test_resolves_names_through_callback(self):
        def resolve(name):
            return ["d" * 64] if name == "Dave" else []

        members, error = normalize_group_members(
            "Dave, %s" % ("b" * 64), self.own, resolve_name=resolve
        )
        self.assertEqual(error, None)
        self.assertEqual(members, ["b" * 64, "d" * 64])

    def test_ambiguous_name_is_an_error(self):
        members, error = normalize_group_members(
            "Dave, %s" % ("b" * 64), self.own, resolve_name=lambda n: ["d" * 64, "e" * 64]
        )
        self.assertEqual(members, None)
        self.assertIn("Dave", error)

    def test_caps_member_count_with_a_clear_message(self):
        hexes = [("%02x" % i) * 32 for i in range(1, MAX_GROUP_MEMBERS + 2)]
        members, error = normalize_group_members(",".join(hexes), self.own)
        self.assertEqual(members, None)
        self.assertIn(str(MAX_GROUP_MEMBERS), error)
        members, error = normalize_group_members(",".join(hexes[:MAX_GROUP_MEMBERS]), self.own)
        self.assertEqual(error, None)
        self.assertEqual(len(members), MAX_GROUP_MEMBERS)

    def test_needs_two_other_members(self):
        members, error = normalize_group_members("%s, %s" % (self.own, "b" * 64), self.own)
        self.assertEqual(members, None)
        self.assertTrue(error)
        members, error = normalize_group_members("", self.own)
        self.assertEqual(members, None)
        self.assertTrue(error)


class TestChatSubject(unittest.TestCase):
    """NIP-17 subject: 'The newest `subject` in the chat room is the subject
    of the conversation.'"""

    def test_group_with_subject_uses_it_as_title(self):
        chat = Chat.nip17_group(["b" * 64, "c" * 64], subject="Weekend")
        self.assertEqual(chat.subject, "Weekend")
        self.assertEqual(chat.title, "Weekend")
        self.assertEqual(chat.display_title(), "Weekend")

    def test_subject_round_trips_through_dict(self):
        chat = Chat.nip17_group(["b" * 64, "c" * 64], subject="Weekend")
        chat.subject_ts = 123
        again = Chat.from_dict(chat.chat_id, chat.to_dict())
        self.assertEqual(again.subject, "Weekend")
        self.assertEqual(again.subject_ts, 123)
        self.assertEqual(again.title, "Weekend")
        old = Chat.from_dict(chat.chat_id, {"kind": KIND_NIP17_CHAT, "participants": ["b" * 64, "c" * 64]})
        self.assertEqual(old.subject, None)

    def test_display_title_without_subject_lists_members(self):
        chat = Chat.nip17_group(["b" * 64, "c" * 64])
        title = chat.display_title()
        self.assertTrue(title.startswith("npub1"))
        self.assertIn(", npub1", title)

    def test_apply_subject_only_from_newest_message(self):
        store = _FakeStore()
        chat = Chat.nip17_group(["b" * 64, "c" * 64], subject="Old")
        chat.subject_ts = 200
        stale = _FakeEvent(KIND_NIP17_CHAT, "b" * 64, [["p", "a" * 64], ["subject", "Older"]], created_at=100)
        self.assertFalse(apply_nip17_subject(store, chat, stale))
        self.assertEqual(store.subjects, [])
        newer = _FakeEvent(KIND_NIP17_CHAT, "b" * 64, [["p", "a" * 64], ["subject", "New"]], created_at=300)
        self.assertTrue(apply_nip17_subject(store, chat, newer))
        self.assertEqual(store.subjects, [(chat.chat_id, "New", 300)])
        self.assertEqual(chat.title, "New")
        self.assertEqual(chat.subject, "New")

    def test_apply_subject_ignores_same_subject_and_dm_chats(self):
        store = _FakeStore()
        chat = Chat.nip17_group(["b" * 64, "c" * 64], subject="Same")
        same = _FakeEvent(KIND_NIP17_CHAT, "b" * 64, [["p", "a" * 64], ["subject", "Same"]], created_at=999)
        self.assertFalse(apply_nip17_subject(store, chat, same))
        dm = Chat.dm("a" * 64, "b" * 64)
        renamed = _FakeEvent(KIND_NIP17_CHAT, "b" * 64, [["p", "a" * 64], ["subject", "Hey"]], created_at=999)
        self.assertFalse(apply_nip17_subject(store, dm, renamed))
        self.assertEqual(store.subjects, [])


if __name__ == "__main__":
    unittest.main()
