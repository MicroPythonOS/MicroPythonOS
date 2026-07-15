"""Unit tests for the generic NostrManager and NostrEvent helpers."""

import sys
import unittest

# The module under test lives in the renamed nostr app root (a flat package).
sys.path.append("apps")

from nostr.key import PrivateKey, PublicKey
from com_micropythonos_nostr.nostr_service import (
    KIND_DM_RELAY_LIST,
    KIND_NIP17_CHAT,
    KIND_NIP17_GIFT_WRAP,
    KIND_RELAY_LIST,
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


class _FakeRelay:
    def __init__(self, url):
        self.url = url
        self.connected = False
        self.error_counter = 0
        self.published = []

    def publish(self, message):
        self.published.append(message)


class _FakeRelayManagerForSync:
    """Tracks add_relay/open_connections/publish_message for _sync_relays tests."""

    def __init__(self, urls=None):
        self.relays = {}
        for url in (urls or []):
            self.add_relay(url)
        self.published = []
        self.subscriptions_added = []

    def add_relay(self, url):
        self.relays[url] = _FakeRelay(url)

    async def open_connections(self, ssl_options=None, proxy=None):
        for relay in self.relays.values():
            relay.connected = True

    def connected_or_errored_relays(self):
        return sum(1 for r in self.relays.values() if r.connected or r.error_counter > 0)

    def publish_message(self, message):
        self.published.append(message)

    def add_subscription(self, sub_id, filters):
        self.subscriptions_added.append((sub_id, filters))


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
        self.mgr.subscribe_metadata(key.public_key.bech32())
        self.assertEqual(len(self.mgr._subscriptions), 1)
        filt = self._subscription_json()
        self.assertEqual(filt.get("authors"), [key.public_key.hex()])

    def test_subscribe_profile_accepts_hex_pubkey(self):
        key = PrivateKey()
        self.mgr.subscribe_metadata(key.public_key.hex())
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
        self.mgr.connected = False
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

    def test_publish_dm_signs_kind4_encrypted_event(self):
        recipient = PrivateKey()
        content = "secret dm"
        self.mgr.publish_dm(recipient.public_key.hex(), content)
        self.assertEqual(len(self.mgr.relay_manager.published), 1)
        event = self.mgr.relay_manager.published[0]
        self.assertEqual(event.kind, 4)
        self.assertEqual(event.public_key, self.mgr._nostr_private_key.public_key.hex())
        self.assertTrue(["p", recipient.public_key.hex()] in event.tags)
        self.assertNotEqual(event.content, content)
        self.assertTrue(len(event.content) > 0)
        self.assertTrue(len(event.signature) > 0)

    def test_publish_relay_lists_publishes_kind10002_and_kind10050(self):
        self.mgr.configure_identity(
            self.mgr._current_nsec, relays="wss://relay.example"
        )
        self.mgr.publish_relay_list()
        kinds = [e.kind for e in self.mgr.relay_manager.published]
        self.assertIn(KIND_RELAY_LIST, kinds)
        self.assertIn(KIND_DM_RELAY_LIST, kinds)
        for event in self.mgr.relay_manager.published:
            self.assertEqual(event.public_key, self.mgr._nostr_private_key.public_key.hex())
            self.assertEqual(event.content, "")
            self.assertTrue(len(event.signature) > 0)
            self.assertTrue(len(event.tags) > 0)

    def test_subscribe_nip17_dms_adds_debug_subscription(self):
        self.mgr.subscribe_nip17_dms()
        sub = self.mgr._subscriptions[-1]
        self.assertEqual(sub.name, "nip17-debug")
        filt = sub.filters.to_json_array()[0]
        self.assertIn(KIND_NIP17_GIFT_WRAP, filt.get("kinds", []))

    def test_publish_nip17_message_creates_kind1059_wrappers(self):
        recipient = PrivateKey()
        ids = self.mgr.publish_nip17_message("hello", [recipient.public_key.hex()])
        self.assertEqual(len(ids), 1)  # only the recipient's gift-wrap
        self.assertEqual(len(self.mgr.relay_manager.published), 1)
        for event in self.mgr.relay_manager.published:
            self.assertEqual(event.kind, KIND_NIP17_GIFT_WRAP)
            self.assertTrue(len(event.content) > 0)
            self.assertTrue(len(event.signature) > 0)

    def test_publish_nip17_message_rejects_empty_content(self):
        try:
            self.mgr.publish_nip17_message("", [PrivateKey().public_key.hex()])
        except ValueError:
            return
        self.fail("publish_nip17_message should reject empty content")

    def test_publish_nip17_message_rejects_empty_recipients(self):
        try:
            self.mgr.publish_nip17_message("hi", [])
        except ValueError:
            return
        self.fail("publish_nip17_message should reject empty recipients")

    def test_process_event_unwraps_gift_wrap_to_rumor(self):
        from nostr.nip17 import make_nip17_messages

        alice = PrivateKey()
        bob = PrivateKey()
        self.mgr._nostr_private_key = bob
        self.mgr._nostr_configured = True
        gifts = make_nip17_messages(alice, "secret dm", [bob.public_key.hex()])
        gift = None
        for g in gifts:
            for tag in g["tags"]:
                if tag[0] == "p" and tag[1] == bob.public_key.hex():
                    gift = g
                    break
        self.assertIsNotNone(gift)
        from nostr.event import Event

        wrap_event = Event(
            content=gift["content"],
            public_key=gift["pubkey"],
            created_at=gift["created_at"],
            kind=gift["kind"],
            tags=gift["tags"],
            signature=gift["sig"],
        )
        caught = []
        self.mgr.register_post_event_handler(KIND_NIP17_CHAT, lambda e: caught.append(e))
        self.mgr._process_event(wrap_event)
        self.assertEqual(len(caught), 1)
        self.assertEqual(caught[0].event.content, "secret dm")
        self.assertEqual(caught[0].event.public_key, alice.public_key.hex())


class TestNostrManagerNwcPublish(unittest.TestCase):
    """Publishing NWC requests as kind 23194 encrypted DMs."""

    def setUp(self):
        self.mgr = NostrManager.get_instance()
        self.mgr._subscriptions = []
        self.mgr._subscription_ids = {}
        self.mgr._default_relays = []
        self.mgr._nostr_configured = False
        self.mgr._nostr_private_key = None
        self.mgr._nwc_configured = True
        self.mgr._nwc_private_key = PrivateKey()
        self.mgr._nwc_wallet_pubkey = "a" * 64
        self.mgr.relay_manager = _FakeRelayManager()

    def test_nwc_fetch_balance_publishes_kind23194_encrypted_request(self):
        self.mgr.nwc_fetch_balance()
        self.assertEqual(len(self.mgr.relay_manager.published), 1)
        event = self.mgr.relay_manager.published[0]
        self.assertEqual(event.kind, 23194)
        self.assertEqual(event.public_key, self.mgr._nwc_private_key.public_key.hex())
        self.assertTrue(["p", self.mgr._nwc_wallet_pubkey] in event.tags)
        self.assertTrue(len(event.content) > 0)
        self.assertTrue(len(event.signature) > 0)

    def test_nwc_fetch_payments_publishes_kind23194_encrypted_request(self):
        self.mgr.nwc_fetch_payments()
        self.assertEqual(len(self.mgr.relay_manager.published), 1)
        event = self.mgr.relay_manager.published[0]
        self.assertEqual(event.kind, 23194)
        self.assertEqual(event.public_key, self.mgr._nwc_private_key.public_key.hex())
        self.assertTrue(["p", self.mgr._nwc_wallet_pubkey] in event.tags)
        self.assertTrue(len(event.content) > 0)
        self.assertTrue(len(event.signature) > 0)


class TestNostrManagerRelaySync(unittest.TestCase):
    """Hot-adding relays configured while the manager is already running."""

    def setUp(self):
        self.mgr = NostrManager.get_instance()
        self.mgr._subscriptions = []
        self.mgr._subscription_ids = {}
        self.mgr._default_relays = []
        self.mgr._nwc_relays = []
        self.mgr._nostr_configured = False
        self.mgr._nwc_configured = False
        self.mgr._nostr_private_key = None
        self.mgr._nwc_private_key = None
        self.mgr._nwc_wallet_pubkey = None
        self.mgr._relays_dirty = False
        self.mgr.connected = False
        self.mgr.relay_manager = None
        self.mgr.keep_running = True
        self.mgr._cleanup_done = True
        # Earlier tests may have scheduled the real _run() loop. Cancel it
        # and pretend the main task is running so configure_identity doesn't
        # spawn a new one while these tests run.
        if self.mgr._main_task is not None and self.mgr._main_task is not True:
            try:
                self.mgr._main_task.cancel()
            except Exception:
                pass
        self.mgr._main_task = True

    def _fresh_nsec(self):
        return PrivateKey().bech32()

    def test_configure_identity_marks_relays_dirty_when_running(self):
        self.mgr.relay_manager = _FakeRelayManagerForSync()
        self.assertFalse(self.mgr._relays_dirty)
        self.mgr.configure_identity(self._fresh_nsec(), relays="wss://a.example")
        self.assertTrue(self.mgr._relays_dirty)

    def test_sync_relays_adds_new_relays_and_republishes(self):
        self.mgr.configure_identity(self._fresh_nsec(), relays="wss://old.example")
        self.mgr.subscribe_channel("f" * 64)
        sub_name = self.mgr._subscriptions[0].name
        self.mgr._subscription_ids = {sub_name: "sub_1"}
        self.mgr.relay_manager = _FakeRelayManagerForSync(["wss://old.example"])
        self.mgr._default_relays = ["wss://old.example", "wss://new.example"]
        self.mgr._relays_dirty = True

        import asyncio
        asyncio.run(self.mgr._sync_relays())

        self.assertIn("wss://old.example", self.mgr.relay_manager.relays)
        self.assertIn("wss://new.example", self.mgr.relay_manager.relays)
        self.assertFalse(self.mgr._relays_dirty)
        self.assertTrue(any("sub_1" in p for p in self.mgr.relay_manager.published))

    def test_sync_relays_adds_nwc_relays(self):
        self.mgr.configure_identity(self._fresh_nsec(), relays="wss://identity.example")
        self.mgr.relay_manager = _FakeRelayManagerForSync(["wss://identity.example"])
        self.mgr._nwc_relays = ["wss://nwc.example"]
        self.mgr._nwc_configured = True
        self.mgr._nwc_sub_id = "nwc_sub_1"
        self.mgr._nwc_private_key = PrivateKey()
        self.mgr._nwc_wallet_pubkey = "a" * 64
        self.mgr._relays_dirty = True

        import asyncio
        asyncio.run(self.mgr._sync_relays())

        self.assertIn("wss://nwc.example", self.mgr.relay_manager.relays)
        self.assertTrue(any("nwc_sub_1" in p for p in self.mgr.relay_manager.published))

    def test_send_subscriptions_to_relays_publishes_req_to_connected(self):
        self.mgr.configure_identity(self._fresh_nsec())
        self.mgr.subscribe_channel("f" * 64)
        sub_name = self.mgr._subscriptions[0].name
        self.mgr._subscription_ids = {sub_name: "sub_1"}
        self.mgr.relay_manager = _FakeRelayManagerForSync(["wss://r.example"])
        self.mgr.relay_manager.relays["wss://r.example"].connected = True

        self.mgr._send_subscriptions_to_relays(["wss://r.example"])

        relay = self.mgr.relay_manager.relays["wss://r.example"]
        self.assertTrue(any("sub_1" in p for p in relay.published))
        self.assertTrue(any("REQ" in p for p in relay.published))

    def test_send_subscriptions_skips_disconnected_relays(self):
        self.mgr.configure_identity(self._fresh_nsec())
        self.mgr.subscribe_channel("f" * 64)
        sub_name = self.mgr._subscriptions[0].name
        self.mgr._subscription_ids = {sub_name: "sub_1"}
        self.mgr.relay_manager = _FakeRelayManagerForSync(["wss://r.example"])
        # leave connected=False

        self.mgr._send_subscriptions_to_relays(["wss://r.example"])

        relay = self.mgr.relay_manager.relays["wss://r.example"]
        self.assertEqual(relay.published, [])


class TestNostrManagerConnectivity(unittest.TestCase):
    """Online/offline callbacks and restart-safe stop behaviour."""

    def setUp(self):
        self.mgr = NostrManager.get_instance()
        # Ensure direct _run() calls in these tests do not block waiting for
        # an NTP-synced clock.
        from mpos.time_zone import TimeZone
        TimeZone.time_is_set = lambda: True
        if self.mgr._main_task is not None and self.mgr._main_task is not True:
            try:
                self.mgr._main_task.cancel()
            except Exception:
                pass
        self.mgr._subscriptions = []
        self.mgr._subscription_ids = {}
        self.mgr._default_relays = []
        self.mgr._nwc_relays = []
        self.mgr._nostr_configured = False
        self.mgr._nwc_configured = False
        self.mgr._nwc_nwc_url = None
        self.mgr._nostr_private_key = None
        self.mgr._nwc_private_key = None
        self.mgr._nwc_wallet_pubkey = None
        self.mgr._relays_dirty = False
        self.mgr.connected = False
        self.mgr.relay_manager = None
        self.mgr.keep_running = False
        self.mgr._cleanup_done = True
        self.mgr._main_task = True  # suppress async task creation in tests

    def test_run_resets_main_task_after_failed_relay_connection(self):
        """If no relay connects, _run() must reset state so start() can retry."""
        from com_micropythonos_nostr import nostr_service

        original_relay_manager = nostr_service.RelayManager

        class _FakeNoConnectRelayManager:
            def __init__(self):
                self.relays = {"wss://test.example": object()}

            def add_relay(self, url):
                self.relays[url] = object()

            async def open_connections(self, ssl_options=None, proxy=None):
                pass

            def connected_relays(self):
                return 0

        nostr_service.RelayManager = _FakeNoConnectRelayManager
        try:
            self.mgr._default_relays = ["wss://test.example"]
            # Simulate the loop having already been asked to stop so the
            # 30-second connection wait exits immediately.
            self.mgr.keep_running = False
            import asyncio

            asyncio.run(self.mgr._run())
            self.assertIsNone(self.mgr._main_task)
            self.assertFalse(self.mgr.keep_running)
        finally:
            nostr_service.RelayManager = original_relay_manager

    def test_stop_preserves_subscriptions_and_config(self):
        """stop() must clear only runtime state, not configured state."""
        import asyncio

        nsec = PrivateKey().bech32()
        self.mgr.configure_identity(nsec, relays="wss://preserve.example")
        self.mgr.subscribe_channel("f" * 64, name="preserved")
        self.mgr._nwc_configured = True
        self.mgr._nwc_nwc_url = "nwc://wallet.example"

        self.mgr.stop()
        self.assertFalse(self.mgr.keep_running)
        # Run the close coroutine synchronously because the async cleanup
        # task will not execute in the test runner.
        asyncio.run(self.mgr._do_close())

        self.assertTrue(self.mgr._nostr_configured)
        self.assertEqual(self.mgr._default_relays, ["wss://preserve.example"])
        self.assertEqual(len(self.mgr._subscriptions), 1)
        self.assertEqual(self.mgr._subscriptions[0].name, "preserved")
        self.assertTrue(self.mgr._nwc_configured)
        self.assertEqual(self.mgr._nwc_nwc_url, "nwc://wallet.example")
        self.assertIsNone(self.mgr._main_task)
        self.assertIsNone(self.mgr.relay_manager)

    def test_on_connectivity_change_starts_when_offline(self):
        self.mgr.keep_running = False
        self.mgr._main_task = True  # suppress async task creation
        self.mgr._on_connectivity_change(True)
        self.assertTrue(self.mgr.keep_running)

    def test_on_connectivity_change_stops_when_online(self):
        self.mgr.keep_running = True
        self.mgr._main_task = True
        self.mgr._on_connectivity_change(False)
        self.assertFalse(self.mgr.keep_running)

    def test_publish_signed_dm_requires_relay_manager(self):
        """NWC helpers must fail cleanly when stopped/offline."""
        self.mgr._nwc_configured = True
        self.mgr._nwc_private_key = PrivateKey()
        self.mgr._nwc_wallet_pubkey = "a" * 64
        self.mgr.relay_manager = None
        try:
            self.mgr.nwc_fetch_balance()
        except RuntimeError:
            return
        self.fail("nwc_fetch_balance should raise RuntimeError when offline")


class TestTimeZoneTimeIsSet(unittest.TestCase):
    """Sanity check for the clock-sync threshold helper."""

    def test_time_is_set_matches_local_year(self):
        from mpos.time_zone import TimeZone
        import time
        # The threshold is 2026-01-01; this test is True on synced modern clocks.
        if time.localtime()[0] < 2026:
            self.assertFalse(TimeZone.time_is_set())
        else:
            self.assertTrue(TimeZone.time_is_set())


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
