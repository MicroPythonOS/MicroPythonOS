"""Round-trip Nostr DMs through a local in-memory relay.

This exercises the full publish/subscribe WebSocket path without relying on
external relays, and validates that the client answers server ping frames.
"""

import asyncio
import sys
import time
import unittest

sys.path.append("tests")
sys.path.append("apps")

from com_micropythonos_nostr.nostr_service import (
    KIND_NIP17_CHAT,
    KIND_NIP17_GIFT_WRAP,
    NostrManager,
)
from nostr.key import PrivateKey
from nostr_local_relay import LocalNostrRelay


def _run_async(coro):
    return asyncio.run(coro)


class TestNostrLocalRelayRoundTrip(unittest.TestCase):
    """Publish a NIP-17 DM to a local relay and verify the echo is received."""

    def _load_test_key(self):
        return PrivateKey(bytes.fromhex(
            "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2"
        ))

    async def _wait_for_connected(self, manager, timeout=10):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if manager.is_connected():
                return True
            await asyncio.sleep(0.1)
        return False

    async def _async_test_nip17_self_send(self):
        relay = LocalNostrRelay()
        url = await relay.start()

        private_key = self._load_test_key()
        own_hex = private_key.public_key.hex()

        manager = NostrManager()
        manager.start()
        manager.configure_identity(private_key.bech32(), relays=[url])

        caught = []
        manager.register_post_event_handler(
            KIND_NIP17_CHAT, lambda e: caught.append(e)
        )

        since = int(time.time())
        manager.subscribe_nip17_dms(since=since)

        connected = await self._wait_for_connected(manager, timeout=10)
        self.assertTrue(connected, "Manager did not connect to local relay")

        # The local relay should receive a ping and stay connected.
        await relay.send_ping()
        self.assertTrue(manager.is_connected(), "Connection dropped after ping")

        marker = "LOCAL-RELAY-SELF-SEND-{}".format(int(time.time()))
        ids = manager.publish_nip17_message(marker, [own_hex])
        self.assertEqual(len(ids), 1)

        found = None
        deadline = time.time() + 10
        while time.time() < deadline:
            for nevent in caught:
                if nevent.event.content == marker:
                    found = nevent.event
                    break
            if found is not None:
                break
            await asyncio.sleep(0.1)

        manager.stop()
        await relay.stop()

        self.assertTrue(found is not None, "No kind-14 rumor echoed by local relay")
        self.assertEqual(found.kind, KIND_NIP17_CHAT)
        self.assertEqual(found.public_key, own_hex)
        self.assertEqual(found.content, marker)

    def test_nip17_self_send_round_trip(self):
        _run_async(self._async_test_nip17_self_send())


if __name__ == "__main__":
    unittest.main()
