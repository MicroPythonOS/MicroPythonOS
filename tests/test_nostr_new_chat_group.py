"""NewChatActivity 'Group' mode logic (no LVGL): member normalisation, subject, errors."""

import sys
import unittest

sys.path.insert(0, "lib")
sys.path.insert(0, "apps/com_micropythonos_nostr")

from apps.com_micropythonos_nostr.chat_model import (
    KIND_NIP17_CHAT,
    MAX_GROUP_MEMBERS,
    Chat,
    nip17_group_chat_id,
)
from apps.com_micropythonos_nostr.new_chat_activity import NewChatActivity


class _FakeLabel:
    def __init__(self):
        self.text = ""
        self.hidden = True

    def set_text(self, text):
        self.text = text

    def add_flag(self, flag):
        self.hidden = True

    def remove_flag(self, flag):
        self.hidden = False


class _FakeManager:
    def __init__(self, own):
        self.own = own

    def get_own_pubkey_hex(self):
        return self.own


class _FakeStore:
    def __init__(self):
        self.chats = {}
        self.subjects = []
        self.dms = []

    def get_or_create_nip17_group(self, participants, title=None, subject=None):
        chat_id = nip17_group_chat_id(participants)
        if chat_id not in self.chats:
            self.chats[chat_id] = Chat.nip17_group(participants, title=title, subject=subject)
        return self.chats[chat_id]

    def update_chat_subject(self, chat_id, subject, ts=0):
        self.subjects.append((chat_id, subject))
        chat = self.chats[chat_id]
        chat.subject = subject
        chat.title = subject

    def get_or_create_dm(self, own, peer):
        self.dms.append((own, peer))
        return Chat.dm(own, peer)

    def flush_index(self):
        pass


class TestNewChatActivityGroup(unittest.TestCase):
    own = "a" * 64

    def _activity(self, resolver=None):
        act = object.__new__(NewChatActivity)
        act._manager = _FakeManager(self.own)
        act._store = _FakeStore()
        act._error_label = _FakeLabel()
        act.navigated = []
        act._navigate_to_chat = lambda chat: act.navigated.append(chat)
        if resolver is not None:
            act._resolve_member_name = resolver
        else:
            act._resolve_member_name = lambda name: []
        return act

    def test_creates_group_with_subject_and_sorted_members(self):
        act = self._activity()
        raw = "{c}\n{b}, {a}".format(a=self.own, b="b" * 64, c="c" * 64)
        chat = act._start_group(raw, "Weekend")
        self.assertIsNotNone(chat)
        self.assertEqual(chat.kind, KIND_NIP17_CHAT)
        self.assertEqual(chat.participants, ["b" * 64, "c" * 64])
        self.assertEqual(chat.subject, "Weekend")
        self.assertEqual(chat.title, "Weekend")
        self.assertEqual(act.navigated, [chat])
        self.assertEqual(act._error_label.text, "")

    def test_bad_member_shows_error_and_does_not_navigate(self):
        act = self._activity()
        chat = act._start_group("%s, garbage" % ("b" * 64), "x")
        self.assertEqual(chat, None)
        self.assertIn("garbage", act._error_label.text)
        self.assertEqual(act.navigated, [])

    def test_too_many_members_shows_cap_message(self):
        act = self._activity()
        raw = ",".join(("%02x" % i) * 32 for i in range(1, MAX_GROUP_MEMBERS + 2))
        self.assertEqual(act._start_group(raw, ""), None)
        self.assertIn(str(MAX_GROUP_MEMBERS), act._error_label.text)

    def test_new_subject_renames_existing_group(self):
        act = self._activity()
        existing = act._store.get_or_create_nip17_group(["b" * 64, "c" * 64], subject="Old")
        chat = act._start_group("%s,%s" % ("b" * 64, "c" * 64), "New")
        self.assertEqual(chat.chat_id, existing.chat_id)
        self.assertEqual(act._store.subjects, [(existing.chat_id, "New")])
        self.assertEqual(chat.title, "New")

    def test_blank_subject_keeps_existing_subject(self):
        act = self._activity()
        existing = act._store.get_or_create_nip17_group(["b" * 64, "c" * 64], subject="Old")
        chat = act._start_group("%s,%s" % ("b" * 64, "c" * 64), "   ")
        self.assertEqual(chat.chat_id, existing.chat_id)
        self.assertEqual(act._store.subjects, [])
        self.assertEqual(chat.subject, "Old")

    def test_names_resolve_through_profile_lookup(self):
        act = self._activity(resolver=lambda name: ["d" * 64] if name == "Dave" else [])
        chat = act._start_group("Dave, %s" % ("b" * 64), "Named")
        self.assertEqual(chat.participants, ["b" * 64, "d" * 64])

    def test_dm_mode_with_several_npubs_makes_normalised_group(self):
        act = self._activity()
        chat = act._start_dm("{c}, {b}, {a}".format(a=self.own, b="b" * 64, c="c" * 64))
        self.assertEqual(chat.participants, ["b" * 64, "c" * 64])
        self.assertEqual(chat.subject, None)
        self.assertEqual(act._store.dms, [])

    def test_dm_mode_with_one_npub_makes_dm(self):
        act = self._activity()
        chat = act._start_dm("b" * 64)
        self.assertEqual(act._store.dms, [(self.own, "b" * 64)])
        self.assertEqual(chat.peer_pubkey, "b" * 64)


if __name__ == "__main__":
    unittest.main()
