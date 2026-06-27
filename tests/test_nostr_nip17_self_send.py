"""End-to-end self-send NIP-17 test.

Builds a NIP-17 gift-wrap addressed to the device's own pubkey, feeds it back
through NostrManager._process_event, and asserts the unwrapped kind-14 rumor
is routed to registered handlers. This mirrors the relay echo path and
catches regressions where sending works but receiving does not.
"""

import sys
import unittest

sys.path.append("apps")

from nostr.event import Event
from nostr.key import PrivateKey
from nostr.nip17 import make_nip17_messages
from com_micropythonos_nostr.nostr_service import (
    KIND_NIP17_CHAT,
    KIND_NIP17_GIFT_WRAP,
    NostrManager,
)


class _FakeRelayManager:
    """Captures events published by NostrManager without touching the network."""

    def __init__(self):
        self.published = []

    def publish_event(self, event):
        self.published.append(event)


class TestNip17SelfSendReceive(unittest.TestCase):
    """Send a NIP-17 message to yourself and verify it can be unwrapped and routed."""

    def _load_test_key(self):
        # Deterministic test key. Avoids depending on /prefs/ so the test runs
        # on the build server and in clean workspaces.
        return PrivateKey(bytes.fromhex(
            "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2"
        ))

    def setUp(self):
        self.private_key = self._load_test_key()
        self.own_hex = self.private_key.public_key.hex()

        self.mgr = NostrManager.get_instance()
        # Reset state so each test runs deterministically.
        self.mgr._subscriptions = []
        self.mgr._subscription_ids = {}
        self.mgr._default_relays = []
        self.mgr._nostr_configured = True
        self.mgr._nostr_private_key = self.private_key
        self.mgr.relay_manager = _FakeRelayManager()
        self.mgr._event_handlers = {}
        self.mgr._post_event_handlers = {}

    def _event_to_gift_dict(self, event):
        """Convert a published kind-1059 Event into the dict our helpers expect."""
        return {
            "id": event.id,
            "content": event.content,
            "pubkey": event.public_key,
            "created_at": event.created_at,
            "kind": event.kind,
            "tags": event.tags,
            "sig": event.signature,
        }

    def _find_wrap_for_recipient(self, gifts, recipient_hex):
        """Return the kind-1059 gift whose 'p' tag points to recipient_hex."""
        for gift in gifts:
            for tag in gift.get("tags", []):
                if len(tag) >= 2 and tag[0] == "p" and tag[1] == recipient_hex:
                    return gift
        return None

    def test_self_send_nip17_unwraps_and_routes(self):
        """Publish a NIP-17 message to self and route it back through _process_event."""
        content = "self-send NIP-17 test"
        ids = self.mgr.publish_nip17_message(content, [self.own_hex])
        # Self-send: own pubkey is deduped with the recipient, so only one wrap.
        self.assertEqual(len(ids), 1)
        self.assertEqual(len(self.mgr.relay_manager.published), 1)

        gifts = self.mgr.relay_manager.published
        for event in gifts:
            self.assertEqual(event.kind, KIND_NIP17_GIFT_WRAP)
            self.assertTrue(event.verify())

        gift = self._find_wrap_for_recipient(
            [self._event_to_gift_dict(e) for e in self.mgr.relay_manager.published],
            self.own_hex,
        )
        self.assertIsNotNone(gift)

        wrap_event = Event(
            content=gift["content"],
            public_key=gift["pubkey"],
            created_at=gift["created_at"],
            kind=gift["kind"],
            tags=gift["tags"],
            signature=gift["sig"],
        )
        self.assertEqual(wrap_event.id, gift["id"])
        self.assertTrue(wrap_event.verify())

        caught = []
        self.mgr.register_post_event_handler(KIND_NIP17_CHAT, lambda e: caught.append(e))
        self.mgr._process_event(wrap_event)

        self.assertEqual(len(caught), 1)
        rumor = caught[0].event
        self.assertEqual(rumor.kind, KIND_NIP17_CHAT)
        self.assertEqual(rumor.content, content)
        self.assertEqual(rumor.public_key, self.own_hex)
        self.assertEqual(rumor.id, wrap_event.id)

    def test_self_send_nip17_event_handler_receives_rumor(self):
        """A kind-14 event handler should see the decrypted rumor, not the wrapper."""
        content = "handler self-send NIP-17 test"
        self.mgr.publish_nip17_message(content, [self.own_hex])

        gift = self._find_wrap_for_recipient(
            [self._event_to_gift_dict(e) for e in self.mgr.relay_manager.published],
            self.own_hex,
        )
        wrap_event = Event(
            content=gift["content"],
            public_key=gift["pubkey"],
            created_at=gift["created_at"],
            kind=gift["kind"],
            tags=gift["tags"],
            signature=gift["sig"],
        )

        caught = []
        self.mgr.register_event_handler(KIND_NIP17_CHAT, lambda e: caught.append(e))
        self.mgr._process_event(wrap_event)

        self.assertEqual(len(caught), 1)
        self.assertEqual(caught[0].event.content, content)
        self.assertEqual(caught[0].event.public_key, self.own_hex)


if __name__ == "__main__":
    unittest.main()
