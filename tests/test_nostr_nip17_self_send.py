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
        """Publish a NIP-17 message to self, route it through _process_event,
        and verify both post-event and event handlers receive the unwrapped rumor."""
        content = "self-send NIP-17 test"
        ids = self.mgr.publish_nip17_message(content, [self.own_hex])
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

        post_caught = []
        event_caught = []
        self.mgr.register_post_event_handler(KIND_NIP17_CHAT, lambda e: post_caught.append(e))
        self.mgr.register_event_handler(KIND_NIP17_CHAT, lambda e: event_caught.append(e))
        self.mgr._process_event(wrap_event)

        self.assertEqual(len(post_caught), 1)
        rumor = post_caught[0].event
        self.assertEqual(rumor.kind, KIND_NIP17_CHAT)
        self.assertEqual(rumor.content, content)
        self.assertEqual(rumor.public_key, self.own_hex)

        self.assertEqual(len(event_caught), 1)
        self.assertEqual(event_caught[0].event.content, content)
        self.assertEqual(event_caught[0].event.public_key, self.own_hex)


    def test_send_to_peer_also_wraps_for_self_and_routes_to_the_dm(self):
        """The sender's own gift-wrap (NIP-17: "to each receiver and the sender
        individually") must unwrap for us, route to the peer's DM chat, and
        carry the id the local echo was stored under (ids[0])."""
        from com_micropythonos_nostr.chat_model import chat_id_for_event, dm_chat_id

        peer = PrivateKey()
        peer_hex = peer.public_key.hex()
        ids = self.mgr.publish_nip17_message("to a peer", [peer_hex])
        self.assertEqual(len(ids), 2)
        gifts = [self._event_to_gift_dict(e) for e in self.mgr.relay_manager.published]
        own_gift = self._find_wrap_for_recipient(gifts, self.own_hex)
        self.assertIsNotNone(own_gift)
        self.assertEqual(own_gift["id"], ids[0])
        self.assertIsNotNone(self._find_wrap_for_recipient(gifts, peer_hex))

        caught = []
        self.mgr.register_event_handler(KIND_NIP17_CHAT, lambda e: caught.append(e))
        self.mgr._process_event(Event(
            content=own_gift["content"],
            public_key=own_gift["pubkey"],
            created_at=own_gift["created_at"],
            kind=own_gift["kind"],
            tags=own_gift["tags"],
            signature=own_gift["sig"],
        ))
        self.assertEqual(len(caught), 1)
        rumor = caught[0].event
        self.assertEqual(rumor.public_key, self.own_hex)
        self.assertEqual(rumor.id, ids[0])
        self.assertEqual(chat_id_for_event(rumor, self.own_hex), dm_chat_id(self.own_hex, peer_hex))


if __name__ == "__main__":
    unittest.main()
