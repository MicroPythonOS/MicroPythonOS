"""Self-send NIP-17 over the real default relays.

This test opens live websocket connections to the default relays, publishes a
NIP-17 gift-wrap addressed to the device's own pubkey, and waits for the same
relays to echo it back. Unlike the fake-relay test, this catches subscription,
filter, network, and relay-specific issues.
"""

import asyncio
import os
import sys
import time
import unittest

sys.path.append("apps")

from com_micropythonos_nostr.nostr_service import (
    KIND_NIP17_CHAT,
    KIND_NIP17_GIFT_WRAP,
    NostrManager,
)
from nostr.key import PrivateKey


def _run_async(coro):
    """Run a coroutine under MicroPython's asyncio."""
    return asyncio.run(coro)

_DEFAULT_RELAYS = [
    "wss://relay.damus.io",
    "wss://relay.primal.net",
    "wss://relay.0xchat.com",
]

if not os.getenv("MPOS_RUN_NETWORK_TESTS"):
    print(
        "SKIP: test_nostr_nip17_self_send_real_relays requires "
        "MPOS_RUN_NETWORK_TESTS=1 (depends on live relay uptime)"
    )

@unittest.skipUnless(
    os.getenv("MPOS_RUN_NETWORK_TESTS"),
    "live-relay integration test; depends on external relay uptime. "
    "Set MPOS_RUN_NETWORK_TESTS=1 to run.",
)
class TestNip17SelfSendRealRelays(unittest.TestCase):
    """Send a NIP-17 message to yourself over the internet and verify receipt."""

    def _load_test_key(self):
        # Deterministic test key so the test does not depend on /prefs/.
        return PrivateKey(bytes.fromhex(
            "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2"
        ))

    async def _wait_for_connected(self, manager, timeout=30):
        """Yield until manager reports connected, up to timeout seconds."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if manager.is_connected():
                return True
            await asyncio.sleep(0.25)
        return False

    async def _wait_for_event(self, captured, timeout=45):
        """Yield until captured is non-empty, up to timeout seconds."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if captured:
                return True
            await asyncio.sleep(0.25)
        return False

    async def _async_test_self_send(self):
        """Async body: connect, publish, wait for echo."""
        private_key = self._load_test_key()
        own_hex = private_key.public_key.hex()

        # Use a fresh manager instance so a running service doesn't interfere.
        manager = NostrManager()
        manager.start()
        manager.configure_identity(private_key.bech32(), relays=_DEFAULT_RELAYS)

        unwrapped_rumors = []
        manager.register_post_event_handler(
            KIND_NIP17_CHAT, lambda e: unwrapped_rumors.append(e)
        )

        # Only fetch events published after now, so historical DMs don't
        # satisfy the assertion before our marker event arrives.
        since = int(time.time())
        manager.subscribe_nip17_dms(since=since)

        connected = await self._wait_for_connected(manager, timeout=30)
        self.assertTrue(
            connected,
            "NostrManager did not connect to any relay within 30s",
        )

        marker = "REAL-RELAY-SELF-SEND-{}".format(int(time.time()))
        print(
            "Connected to relays; publishing self-send NIP-17 marker={} to {}".format(
                marker, own_hex[:16]
            )
        )
        manager.publish_nip17_message(marker, [own_hex])

        deadline = time.time() + 45
        found = None
        while time.time() < deadline:
            for nevent in unwrapped_rumors:
                if nevent.event.content == marker:
                    found = nevent.event
                    break
            if found is not None:
                break
            await asyncio.sleep(0.25)

        print("unwrapped rumors seen: {}".format(len(unwrapped_rumors)))

        manager.stop()

        self.assertIsNotNone(
            found,
            "No kind-14 rumor with marker {} was received within 45s".format(marker),
        )
        self.assertEqual(found.kind, KIND_NIP17_CHAT)
        self.assertEqual(found.public_key, own_hex)
        self.assertEqual(found.content, marker)

    def test_self_send_nip17_over_real_relays(self):
        """Publish a NIP-17 DM to self and wait for a real relay echo."""
        _run_async(self._async_test_self_send())


if __name__ == "__main__":
    unittest.main()
