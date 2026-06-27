"""Regression tests for the DM subscription since= calculation."""

import sys
import unittest

sys.path.insert(0, "lib")
sys.path.insert(0, "apps/com_micropythonos_nostr")

from com_micropythonos_nostr.chat_list_activity import ChatListActivity
from com_micropythonos_nostr.chat_model import (
    KIND_CHANNEL_MESSAGE,
    KIND_DM,
    KIND_NIP17_CHAT,
    Chat,
    channel_chat_id,
    dm_chat_id,
    nip17_group_chat_id,
)


class TestDmSubscriptionSince(unittest.TestCase):
    """The global DM subscription window must be small, not the oldest chat."""

    def test_fresh_install_uses_lookback_window(self):
        now = 1700000000
        chats = []
        since = ChatListActivity._dm_subscription_since(now, chats)
        self.assertEqual(since, now - 24 * 60 * 60)

    def test_newest_chat_drives_the_window(self):
        now = 1700000000
        chats = [
            Chat.dm("a" * 64, "b" * 64),
            Chat.dm("a" * 64, "c" * 64),
        ]
        chats[0].last_ts = now - 3600
        chats[1].last_ts = now - 30
        since = ChatListActivity._dm_subscription_since(now, chats)
        # Newest activity minus overlap, not the oldest.
        self.assertEqual(since, now - 30 - 60)

    def test_window_never_older_than_lookback(self):
        now = 1700000000
        chats = [Chat.dm("a" * 64, "b" * 64)]
        chats[0].last_ts = now - 48 * 3600
        since = ChatListActivity._dm_subscription_since(now, chats)
        self.assertEqual(since, now - 24 * 60 * 60)

    def test_channel_chats_are_ignored(self):
        now = 1700000000
        chats = [Chat.channel("chan" * 16)]
        chats[0].last_ts = now - 10
        since = ChatListActivity._dm_subscription_since(now, chats)
        self.assertEqual(since, now - 24 * 60 * 60)

    def test_nip17_chats_are_included(self):
        now = 1700000000
        chats = [Chat.nip17_group(["a" * 64, "b" * 64])]
        chats[0].last_ts = now - 120
        since = ChatListActivity._dm_subscription_since(now, chats)
        self.assertEqual(since, now - 120 - 60)


if __name__ == "__main__":
    unittest.main()
