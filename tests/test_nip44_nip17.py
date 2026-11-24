"""Unit tests for NIP-44 v2 and NIP-17 gift-wrap helpers."""

import sys
import unittest

sys.path.append("lib")

from nostr.key import PrivateKey
from nostr.nip44 import decrypt, encrypt, get_conversation_key
from nostr.nip17 import (
    decrypt_gift_wrap_to_rumor,
    make_nip17_messages,
    make_rumor,
)


# NIP-44 test vector from https://nips.nostr.com/44.
_KNOWN_SEC1 = "0000000000000000000000000000000000000000000000000000000000000001"
_KNOWN_SEC2 = "0000000000000000000000000000000000000000000000000000000000000002"
_KNOWN_CONVERSATION_KEY = "c41c775356fd92eadc63ff5a0dc1da211b268cbea22316767095b2871ea1412d"
_KNOWN_CIPHER = "AgAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABee0G5VSK0/9YypIObAtDKfYEAjD35uVkHyB0F4DwrcNaCXlCWZKaArsGrY6M9wnuTMxWfp1RTN9Xga8no+kF5Vsb"
_KNOWN_NONCE = "0000000000000000000000000000000000000000000000000000000000000001"


class TestNip44(unittest.TestCase):
    """Pure-Python NIP-44 v2 encryption/decryption."""

    def test_known_conversation_key(self):
        sk1 = PrivateKey(bytes.fromhex(_KNOWN_SEC1))
        sk2 = PrivateKey(bytes.fromhex(_KNOWN_SEC2))
        # Conversation key should be identical in either direction.
        self.assertEqual(
            get_conversation_key(sk1, sk2.public_key.hex()).hex(),
            _KNOWN_CONVERSATION_KEY,
        )
        self.assertEqual(
            get_conversation_key(sk2, sk1.public_key.hex()).hex(),
            _KNOWN_CONVERSATION_KEY,
        )

    def test_known_encrypt_vector(self):
        conv = bytes.fromhex(_KNOWN_CONVERSATION_KEY)
        payload = encrypt("a", conv, nonce=bytes.fromhex(_KNOWN_NONCE))
        self.assertEqual(payload, _KNOWN_CIPHER)

    def test_encrypt_decrypt_roundtrip(self):
        alice = PrivateKey()
        bob = PrivateKey()
        conv = get_conversation_key(alice, bob.public_key.hex())
        for plaintext in ("a", "hello", "üñïçøðé", "x" * 4096):
            ciphertext = encrypt(plaintext, conv)
            decrypted = decrypt(ciphertext, conv)
            self.assertEqual(decrypted, plaintext)

    def test_tampered_mac_fails(self):
        import base64 as _base64

        conv = bytes.fromhex(_KNOWN_CONVERSATION_KEY)
        payload = encrypt("secret", conv)
        raw = bytearray(_base64.b64decode(payload))
        raw[-1] ^= 0xFF
        tampered = _base64.b64encode(bytes(raw)).decode("ascii")
        try:
            decrypt(tampered, conv)
        except ValueError:
            return
        self.fail("tampered payload should fail MAC check")


def _wrap_target(gift):
    return [t[1] for t in gift["tags"] if t[0] == "p"][0]


def _p_tags(rumor):
    return [t[1] for t in rumor["tags"] if t[0] == "p"]


class TestNip44ChaCha20(unittest.TestCase):
    """The ChaCha20 core NIP-44 uses (Viper-accelerated on MicroPython)."""

    def test_rfc8439_encryption_vector(self):
        # RFC 8439 section 2.4.2. The RFC starts at block counter 1, so prefix
        # one block of zeros and drop its output.
        from nostr.nip44 import _chacha20

        key = bytes(range(32))
        nonce = bytes([0, 0, 0, 0, 0, 0, 0, 0x4A, 0, 0, 0, 0])
        plaintext = (
            b"Ladies and Gentlemen of the class of '99: If I could offer you "
            b"only one tip for the future, sunscreen would be it."
        )
        expected = bytes.fromhex(
            "6e2e359a2568f98041ba0728dd0d6981e97e7aec1d4360c20a27afccfd9fae0b"
            "f91b65c5524733ab8f593dabcd62b3571639d624e65152ab8f530c359f0861d8"
            "07ca0dbf500d6a6156a38e088a22b65e52bc514d16ccf806818ce91ab7793736"
            "5af90bbf74a35be6b40b8eedf2785e42874d"
        )
        ciphertext = _chacha20(key, nonce, bytes(64) + plaintext)[64:]
        self.assertEqual(ciphertext, expected)

    def test_matches_reference_at_block_boundaries(self):
        from nostr.nip44 import _chacha20, _chacha20_py

        key = bytes((7 * i + 3) & 0xFF for i in range(32))
        nonce = bytes((11 * i + 5) & 0xFF for i in range(12))
        for length in (0, 1, 63, 64, 65, 127, 128, 129, 1000):
            data = bytes((i * 31 + length) & 0xFF for i in range(length))
            self.assertEqual(_chacha20(key, nonce, data), _chacha20_py(key, nonce, data), length)

    def test_viper_core_is_used_only_when_it_passes_its_self_test(self):
        from nostr import nip44

        if not hasattr(nip44, "_viper_chacha20_works"):
            return  # CPython or a big-endian port: pure Python only
        if nip44._viper_chacha20_works():
            self.assertTrue(nip44._chacha20 is nip44._chacha20_viper)
        else:
            # e.g. the desktop builds, where Viper runs as plain bytecode
            self.assertTrue(nip44._chacha20 is nip44._chacha20_py)

    def test_is_its_own_inverse(self):
        from nostr.nip44 import _chacha20

        key = bytes(32)
        nonce = bytes(12)
        data = b"pocket money" * 50
        self.assertEqual(_chacha20(key, nonce, _chacha20(key, nonce, data)), data)


class TestNip17(unittest.TestCase):
    """NIP-17 gift-wrap construction and decryption."""

    def test_rumor_has_correct_kind_and_recipients(self):
        alice = PrivateKey()
        recipients = [alice.public_key.hex()]
        rumor = make_rumor(alice, "hi", recipients, subject="topic", reply_to="reply-id")
        self.assertEqual(rumor["kind"], 14)
        self.assertEqual(rumor["content"], "hi")
        self.assertIn(["p", alice.public_key.hex()], rumor["tags"])
        self.assertIn(["subject", "topic"], rumor["tags"])
        self.assertIn(["e", "reply-id"], rumor["tags"])

    def test_make_nip17_messages_requires_recipient(self):
        alice = PrivateKey()
        try:
            make_nip17_messages(alice, "hi", [])
        except ValueError:
            return
        self.fail("empty recipients should raise ValueError")

    def test_make_nip17_messages_wraps_for_sender_first(self):
        alice = PrivateKey()
        bob = PrivateKey()
        messages = make_nip17_messages(alice, "hello", [bob.public_key.hex()])
        self.assertEqual(len(messages), 2)
        self.assertTrue(all(m["kind"] == 1059 for m in messages))
        self.assertEqual(_wrap_target(messages[0]), alice.public_key.hex())
        self.assertEqual(_wrap_target(messages[1]), bob.public_key.hex())
        own_copy = decrypt_gift_wrap_to_rumor(messages[0], alice)
        self.assertEqual(_p_tags(own_copy), [bob.public_key.hex()])

    def test_make_nip17_messages_can_skip_the_sender(self):
        alice = PrivateKey()
        bob = PrivateKey()
        messages = make_nip17_messages(
            alice, "hello", [bob.public_key.hex()], include_sender=False
        )
        self.assertEqual([_wrap_target(m) for m in messages], [bob.public_key.hex()])

    def test_roundtrip_decrypt_gift_wrap(self):
        alice = PrivateKey()
        bob = PrivateKey()
        messages = make_nip17_messages(
            alice, "hello", [bob.public_key.hex()], subject="test"
        )
        gift = next(
            m
            for m in messages
            if "p" in [t[0] for t in m["tags"]]
            and bob.public_key.hex() in [t[1] for t in m["tags"]]
        )
        rumor = decrypt_gift_wrap_to_rumor(gift, bob)
        self.assertEqual(rumor["kind"], 14)
        self.assertEqual(rumor["content"], "hello")
        self.assertEqual(rumor["pubkey"], alice.public_key.hex())
        self.assertIn(["subject", "test"], rumor["tags"])

    def test_wrong_receiver_cannot_decrypt(self):
        alice = PrivateKey()
        bob = PrivateKey()
        charlie = PrivateKey()
        messages = make_nip17_messages(alice, "hello", [bob.public_key.hex()])
        gift = next(m for m in messages if _wrap_target(m) == bob.public_key.hex())
        try:
            decrypt_gift_wrap_to_rumor(gift, charlie)
        except ValueError:
            return
        self.fail("wrong receiver should fail decryption")

    def test_group_chat_wraps_for_all_recipients(self):
        alice = PrivateKey()
        bob = PrivateKey()
        charlie = PrivateKey()
        recipients = [bob.public_key.hex(), charlie.public_key.hex()]
        messages = make_nip17_messages(alice, "group hi", recipients, subject="g")
        self.assertEqual(len(messages), 3)
        targets = {_wrap_target(m) for m in messages}
        self.assertEqual(
            targets,
            {alice.public_key.hex(), bob.public_key.hex(), charlie.public_key.hex()},
        )
        gift = next(m for m in messages if _wrap_target(m) == bob.public_key.hex())
        rumor = decrypt_gift_wrap_to_rumor(gift, bob)
        self.assertEqual(sorted(_p_tags(rumor)), sorted(recipients))

    def test_created_at_is_respected(self):
        from nostr.event import Event

        alice = PrivateKey()
        bob = PrivateKey()
        fixed_ts = 2000000000
        messages = make_nip17_messages(
            alice, "ts test", [bob.public_key.hex()], created_at=fixed_ts
        )
        gift = next(m for m in messages if _wrap_target(m) == bob.public_key.hex())
        self.assertEqual(decrypt_gift_wrap_to_rumor(gift, bob)["created_at"], fixed_ts)
        now = Event.epoch_seconds()
        for gift in messages:
            self.assertTrue(now - 2 * 24 * 60 * 60 - 5 <= gift["created_at"] <= now + 5)
            event = Event(
                content=gift["content"],
                public_key=gift["pubkey"],
                created_at=gift["created_at"],
                kind=gift["kind"],
                tags=gift["tags"],
            )
            self.assertEqual(event.id, gift["id"])


if __name__ == "__main__":
    unittest.main()
