"""Tests for nostr_initializer subscription window logic."""

import sys
import unittest

sys.path.insert(0, "lib")
sys.path.insert(0, "apps/com_micropythonos_nostr")

from nostr.key import PrivateKey

from com_micropythonos_nostr import nostr_initializer
from com_micropythonos_nostr.chat_model import Chat, KIND_DM
from com_micropythonos_nostr.nostr_initializer import configure_nostr_manager


class _FakePrefs:
    def __init__(self, nsec=None, relay=None):
        self._data = {
            "nostr_nsec": nsec,
            "nostr_relay": relay,
        }

    def get_string(self, key):
        return self._data.get(key)


class _FakeManager:
    def __init__(self):
        self.running = False
        self.calls = []

    def is_running(self):
        return self.running

    def start(self):
        self.running = True
        self.calls.append(("start", None))

    def configure_identity(self, nsec, relays):
        self.calls.append(("configure_identity", {"nsec": nsec, "relays": relays}))

    def subscribe_dms(self, since, limit):
        self.calls.append(("subscribe_dms", {"since": since, "limit": limit}))

    def subscribe_nip17_dms(self, since, limit):
        self.calls.append(("subscribe_nip17_dms", {"since": since, "limit": limit}))

    def subscribe_channel(self, channel_id, name=None, since=None, limit=None):
        self.calls.append(("subscribe_channel", {
            "channel_id": channel_id,
            "name": name,
            "since": since,
            "limit": limit,
        }))


class _FakeStore:
    def __init__(self, chats=None):
        self._chats = list(chats) if chats else []

    def get_chats(self):
        return self._chats


class TestConfigureNostrManager(unittest.TestCase):
    def setUp(self):
        self.original_current_nostr_ts = nostr_initializer._current_nostr_ts
        self.now = 1_800_000_000
        nostr_initializer._current_nostr_ts = lambda: self.now

    def tearDown(self):
        nostr_initializer._current_nostr_ts = self.original_current_nostr_ts

    def _make_nsec(self):
        return PrivateKey().bech32()

    def test_nip17_subscription_uses_wide_window_despite_recent_chat(self):
        """Even with a very recent DM chat, NIP-17 gift-wraps need a 3-day window
        because their created_at timestamps are randomized within a 2-day window.
        """
        own = PrivateKey()
        peer = "a" * 64
        chat = Chat.dm(own.public_key.hex(), peer)
        chat.last_ts = self.now - 120  # activity 2 minutes ago

        store = _FakeStore(chats=[chat])
        manager = _FakeManager()
        prefs = _FakePrefs(nsec=self._make_nsec(), relay="wss://relay.example")

        configure_nostr_manager(prefs, manager, store=store)

        dm_call = [c for c in manager.calls if c[0] == "subscribe_dms"][0]
        nip17_call = [c for c in manager.calls if c[0] == "subscribe_nip17_dms"][0]

        # DM subscription stays tight because NIP-04 messages are not randomized.
        self.assertEqual(dm_call[1]["since"], self.now - 120 - 60)
        self.assertEqual(dm_call[1]["limit"], 200)

        # NIP-17 subscription must use the fixed 3-day lookback, not the
        # chat-history-driven dm_since.
        self.assertEqual(
            nip17_call[1]["since"],
            self.now - nostr_initializer.NIP17_LOOKBACK_WINDOW_SECONDS,
        )
        self.assertEqual(nip17_call[1]["limit"], 50)

    def test_nip17_subscription_uses_three_day_window_without_history(self):
        manager = _FakeManager()
        prefs = _FakePrefs(nsec=self._make_nsec(), relay="wss://relay.example")

        configure_nostr_manager(prefs, manager, store=None)

        nip17_call = [c for c in manager.calls if c[0] == "subscribe_nip17_dms"][0]
        self.assertEqual(
            nip17_call[1]["since"],
            self.now - nostr_initializer.NIP17_LOOKBACK_WINDOW_SECONDS,
        )
        self.assertEqual(nip17_call[1]["limit"], 50)


if __name__ == "__main__":
    unittest.main()
