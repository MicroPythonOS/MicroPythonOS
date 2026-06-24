"""Unit tests for the generic NostrManager and NostrEvent helpers."""

import sys
import unittest

# The module under test lives in the nostr app's assets directory.
sys.path.append("apps/com.micropythonos.nostr/assets")

from nostr.key import PrivateKey, PublicKey
from nostr_service import (
    NostrEvent,
    NostrManager,
    _parse_nsec,
    _pubkey_to_hex,
)


class _FakeEvent:
    """Minimal stand-in for a nostr.event.Event."""

    def __init__(self, event_id, pubkey, created_at, kind, content, tags=None):
        self.id = event_id
        self.public_key = pubkey
        self.created_at = created_at
        self.kind = kind
        self.content = content
        self.tags = tags or []


class _FakeRelayManager:
    """Captures events published by NostrManager without touching the network."""

    def __init__(self):
        self.published = []

    def publish_event(self, event):
        self.published.append(event)


class TestNostrServiceHelpers(unittest.TestCase):
    """Low-level key/nsec/npub conversion helpers."""

    def test_parse_nsec_from_bech32(self):
        key = PrivateKey()
        parsed = _parse_nsec(key.bech32())
        self.assertEqual(parsed.public_key.hex(), key.public_key.hex())

    def test_parse_nsec_from_hex(self):
        key = PrivateKey()
        parsed = _parse_nsec(key.raw_secret.hex())
        self.assertEqual(parsed.public_key.hex(), key.public_key.hex())

    def test_pubkey_to_hex_returns_hex_unchanged(self):
        key = PrivateKey()
        self.assertEqual(_pubkey_to_hex(key.public_key.hex()), key.public_key.hex())

    def test_pubkey_to_hex_decodes_npub(self):
        key = PrivateKey()
        npub = key.public_key.bech32()
        self.assertEqual(_pubkey_to_hex(npub), key.public_key.hex())


class TestNostrManagerIdentity(unittest.TestCase):
    """Configuring the user's identity and default relays."""

    def setUp(self):
        self.mgr = NostrManager.get_instance()
        # Reset per-test state so subscriptions don't leak between tests.
        self.mgr._subscriptions = []
        self.mgr._subscription_ids = {}
        self.mgr._default_relays = []
        self.mgr._nostr_configured = False
        self.mgr._nostr_private_key = None

    def _fresh_nsec(self):
        return PrivateKey().bech32()

    def test_configure_identity_sets_private_key(self):
        nsec = self._fresh_nsec()
        self.mgr.configure_identity(nsec)
        self.assertTrue(self.mgr._nostr_configured)
        self.assertIsNotNone(self.mgr._nostr_private_key)
        self.assertEqual(self.mgr._nostr_private_key.bech32(), nsec)

    def test_configure_identity_accepts_single_relay_string(self):
        nsec = self._fresh_nsec()
        self.mgr.configure_identity(nsec, relays="wss://relay.example.com")
        self.assertEqual(self.mgr._default_relays, ["wss://relay.example.com"])

    def test_configure_identity_accepts_relay_list(self):
        nsec = self._fresh_nsec()
        relays = ["wss://a.example", "wss://b.example"]
        self.mgr.configure_identity(nsec, relays=relays)
        self.assertEqual(self.mgr._default_relays, relays)

    def test_configure_identity_skips_blank_relays(self):
        nsec = self._fresh_nsec()
        self.mgr.configure_identity(nsec, relays=["", "wss://a.example", ""])
        self.assertEqual(self.mgr._default_relays, ["wss://a.example"])

    def test_configure_identity_treats_empty_relay_string_as_no_relays(self):
        nsec = self._fresh_nsec()
        self.mgr.configure_identity(nsec, relays="")
        self.assertEqual(self.mgr._default_relays, [])


class TestNostrManagerSubscriptions(unittest.TestCase):
    """Building the right filters for channels, profiles and DMs."""

    def setUp(self):
        self.mgr = NostrManager.get_instance()
        self.mgr._subscriptions = []
        self.mgr._subscription_ids = {}
        self.mgr._default_relays = []
        self.mgr._nostr_configured = False
        self.mgr._nostr_private_key = None
        self.mgr.configure_identity(PrivateKey().bech32())

    def _subscription_json(self, index=0):
        return self.mgr._subscriptions[index].filters.to_json_array()[0]

    def test_subscribe_channel_creates_nip28_filter(self):
        channel_id = "f" * 64
        self.mgr.subscribe_channel(channel_id)
        self.assertEqual(len(self.mgr._subscriptions), 1)
        sub = self.mgr._subscriptions[0]
        self.assertEqual(sub.name, "channel-" + channel_id[:8])
        filt = self._subscription_json()
        self.assertEqual(filt.get("kinds"), [42])
        self.assertEqual(filt.get("#e"), [channel_id])

    def test_subscribe_channel_uses_custom_name(self):
        channel_id = "f" * 64
        self.mgr.subscribe_channel(channel_id, name="my-channel")
        self.assertEqual(self.mgr._subscriptions[0].name, "my-channel")

    def test_subscribe_profile_creates_author_filter(self):
        key = PrivateKey()
        self.mgr.subscribe_profile(key.public_key.bech32())
        self.assertEqual(len(self.mgr._subscriptions), 1)
        filt = self._subscription_json()
        self.assertEqual(filt.get("authors"), [key.public_key.hex()])

    def test_subscribe_profile_accepts_hex_pubkey(self):
        key = PrivateKey()
        self.mgr.subscribe_profile(key.public_key.hex())
        filt = self._subscription_json()
        self.assertEqual(filt.get("authors"), [key.public_key.hex()])

    def test_subscribe_dms_requires_identity(self):
        other = NostrManager()
        other._nostr_private_key = None
        try:
            other.subscribe_dms()
        except RuntimeError:
            return
        self.fail("subscribe_dms should require an identity key")

    def test_subscribe_dms_creates_pubkey_ref_filter(self):
        own_hex = self.mgr._nostr_private_key.public_key.hex()
        self.mgr.subscribe_dms()
        self.assertEqual(len(self.mgr._subscriptions), 1)
        sub = self.mgr._subscriptions[0]
        self.assertEqual(sub.name, "dms")
        filt = self._subscription_json()
        self.assertEqual(filt.get("kinds"), [4])
        self.assertEqual(filt.get("#p"), [own_hex])

    def test_add_subscription_replaces_same_name(self):
        channel_id = "f" * 64
        self.mgr.subscribe_channel(channel_id, name="shared")
        self.mgr.subscribe_channel("a" * 64, name="shared")
        self.assertEqual(len(self.mgr._subscriptions), 1)
        filt = self._subscription_json()
        self.assertEqual(filt.get("#e"), ["a" * 64])

    def test_callback_is_stored_on_subscription(self):
        cb = lambda e: e
        self.mgr.subscribe_channel("f" * 64, callback=cb)
        self.assertEqual(self.mgr._subscriptions[0].callback, cb)


class TestNostrManagerPublish(unittest.TestCase):
    """Publishing NIP-28 channel messages."""

    def setUp(self):
        self.mgr = NostrManager.get_instance()
        self.mgr._subscriptions = []
        self.mgr._subscription_ids = {}
        self.mgr._default_relays = []
        self.mgr._nostr_configured = False
        self.mgr._nostr_private_key = None
        self.mgr.relay_manager = None
        self.mgr.configure_identity(PrivateKey().bech32())
        self.mgr.relay_manager = _FakeRelayManager()

    def test_publish_requires_identity(self):
        other = NostrManager()
        other.relay_manager = _FakeRelayManager()
        try:
            other.publish_channel_message("f" * 64, "hello")
        except RuntimeError:
            return
        self.fail("publish_channel_message should require an identity key")

    def test_publish_rejects_empty_content(self):
        try:
            self.mgr.publish_channel_message("f" * 64, "")
        except ValueError:
            return
        self.fail("publish_channel_message should reject empty content")

    def test_publish_requires_relay_manager(self):
        self.mgr.relay_manager = None
        try:
            self.mgr.publish_channel_message("f" * 64, "hello")
        except RuntimeError:
            return
        self.fail("publish_channel_message should require a relay manager")

    def test_publish_channel_message_signs_kind42_event(self):
        channel_id = "c" * 64
        content = "Hello channel!"
        self.mgr.publish_channel_message(channel_id, content)
        self.assertEqual(len(self.mgr.relay_manager.published), 1)
        event = self.mgr.relay_manager.published[0]
        self.assertEqual(event.kind, 42)
        self.assertEqual(event.content, content)
        self.assertEqual(event.public_key, self.mgr._nostr_private_key.public_key.hex())
        self.assertIsNotNone(event.created_at)
        self.assertTrue(isinstance(event.created_at, int))
        self.assertTrue(len(event.signature) > 0)
        self.assertEqual(event.tags, [["e", channel_id, "", "root"]])


class TestNostrEventFormatting(unittest.TestCase):
    """Rendering and decryption of events."""

    def test_regular_event_format_includes_kind_and_content(self):
        event = _FakeEvent(
            event_id="b" * 64,
            pubkey="c" * 64,
            created_at=1780516202,
            kind=1,
            content="hello",
        )
        rendered = str(NostrEvent(event))
        self.assertTrue("TEXT_NOTE" in rendered)
        self.assertTrue("hello" in rendered)

    def test_channel_message_format(self):
        event = _FakeEvent(
            event_id="b" * 64,
            pubkey="d" * 64,
            created_at=1780516202,
            kind=42,
            content="Hello World!",
        )
        rendered = str(NostrEvent(event))
        self.assertTrue(rendered.startswith("["))
        self.assertTrue("Hello World!" in rendered)
        self.assertTrue("dddddddddddddddd" in rendered)

    def test_dm_event_is_decrypted_with_private_key(self):
        alice = PrivateKey()
        bob = PrivateKey()
        plaintext = "secret message"
        ciphertext = alice.encrypt_message(plaintext, bob.public_key.hex())
        event = _FakeEvent(
            event_id="e" * 64,
            pubkey=alice.public_key.hex(),
            created_at=1780516202,
            kind=4,
            content=ciphertext,
        )
        nevent = NostrEvent(event, private_key=bob)
        self.assertEqual(nevent.decrypted_content, plaintext)
        self.assertTrue("secret message" in str(nevent))


if __name__ == "__main__":
    unittest.main()
