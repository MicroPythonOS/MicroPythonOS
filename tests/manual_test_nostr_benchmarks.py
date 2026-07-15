"""Manual benchmark for NIP-17 DM creation.


This is a test purely for timing; it always passes so CI is not broken,
but it prints the per-operation timings used to judge speed-ups.
"""

import time
import unittest

from nostr.key import PrivateKey
from nostr.nip17 import make_nip17_messages
from nostr.nip44 import encrypt, decrypt, get_conversation_key


_FIXED_SECRET = bytes.fromhex(
    "deadbeef00000000000000000000000000000000000000000000000000deadbe"
)


def _ms(start, end=None):
    if end is None:
        end = time.ticks_ms()
    return time.ticks_diff(end, start)


class NostrBenchmarkTest(unittest.TestCase):
    def test_benchmark_nip17_pipeline(self):
        sender = PrivateKey(_FIXED_SECRET)
        recipient = PrivateKey()
        recipient_hex = recipient.public_key.hex()

        # Do enough work that the total is comfortably measurable on desktop.
        counts = {
            "nip17_message": 30,
            "nip44_encrypt": 200,
            "chacha20_xor": 2000,
            "conversation_key": 100,
            "event_id": 1000,
        }

        print("\n--- Nostr NIP-17 baseline benchmark ---")
        print("counts:", counts)

        # 1) Full NIP-17 gift-wrap construction.
        start = time.ticks_ms()
        for _ in range(counts["nip17_message"]):
            make_nip17_messages(sender, "hello benchmark", [recipient_hex])
        elapsed = _ms(start)
        print(
            "make_nip17_messages: {} ms total, {:.2f} ms/msg".format(
                elapsed, elapsed / counts["nip17_message"]
            )
        )

        # 2) NIP-44 encrypt/decrypt round-trip.
        conv_key = get_conversation_key(sender, recipient_hex)
        plaintext = "this is a test nip44 message with enough length"
        start = time.ticks_ms()
        for _ in range(counts["nip44_encrypt"]):
            payload = encrypt(plaintext, conv_key)
            decrypt(payload, conv_key)
        elapsed = _ms(start)
        print(
            "nip44 encrypt+decrypt: {} ms total, {:.2f} ms/round".format(
                elapsed, elapsed / counts["nip44_encrypt"]
            )
        )

        # 3) Raw ChaCha20 XOR throughput via the internal helper.
        from nostr.nip44 import _chacha20

        key = bytes(range(32))
        nonce = bytes(range(12))
        data = bytearray(512)
        start = time.ticks_ms()
        for _ in range(counts["chacha20_xor"]):
            _chacha20(key, nonce, bytes(data))
        elapsed = _ms(start)
        print(
            "_chacha20 (512 B): {} ms total, {:.2f} ms/call, {:.1f} B/ms".format(
                elapsed,
                elapsed / counts["chacha20_xor"],
                (counts["chacha20_xor"] * len(data)) / max(elapsed, 1),
            )
        )

        # 4) Conversation key (ECDH + HKDF extract).
        start = time.ticks_ms()
        for _ in range(counts["conversation_key"]):
            get_conversation_key(sender, recipient_hex)
        elapsed = _ms(start)
        print(
            "get_conversation_key: {} ms total, {:.2f} ms/call".format(
                elapsed, elapsed / counts["conversation_key"]
            )
        )

        # 5) Event id computation (SHA256 + hexlify).
        from nostr.event import Event

        event = Event(
            content="hello benchmark",
            public_key=sender.public_key.hex(),
            created_at=1234567890,
            kind=14,
            tags=[["p", recipient_hex]],
        )
        start = time.ticks_ms()
        for _ in range(counts["event_id"]):
            _ = event.id
        elapsed = _ms(start)
        print(
            "Event.compute_id: {} ms total, {:.2f} ms/call".format(
                elapsed, elapsed / counts["event_id"]
            )
        )

        print("--- end benchmark ---\n")
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
