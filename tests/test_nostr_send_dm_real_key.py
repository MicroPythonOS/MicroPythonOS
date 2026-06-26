"""Verify NIP-04 and NIP-17 signatures with the device's saved Nostr key."""

import json
import sys
import unittest

sys.path.append("apps")

from nostr.event import EncryptedDirectMessage, Event
from nostr.key import PrivateKey
from nostr.nip17 import make_nip17_messages


class TestSendDmSignatures(unittest.TestCase):
    """Local signature check that mirrors what a relay does on publish."""

    def setUp(self):
        with open("prefs/com_micropythonos_nostr/config.json", "r") as f:
            config = json.load(f)
        self.private_key = PrivateKey.from_nsec(config["nostr_nsec"])
        self.recipient = "181137054fe60df5168976311f0bf44dbe4bd4d2e0af69325dfee9fa81a8cbda"

    def test_nip04_dm_signature_verifies(self):
        dm = EncryptedDirectMessage(
            recipient_pubkey=self.recipient,
            cleartext_content="local NIP-04 test",
            kind=4,
        )
        self.private_key.sign_event(dm)
        self.assertTrue(dm.verify())

    def test_nip17_gift_wrap_signature_verifies(self):
        gifts = make_nip17_messages(
            self.private_key,
            "local NIP-17 test",
            [self.recipient],
        )
        self.assertEqual(len(gifts), 2)
        for gift in gifts:
            event = Event(
                content=gift["content"],
                public_key=gift["pubkey"],
                created_at=gift["created_at"],
                kind=gift["kind"],
                tags=gift["tags"],
                signature=gift["sig"],
            )
            self.assertEqual(event.id, gift["id"])
            self.assertTrue(event.verify())


if __name__ == "__main__":
    unittest.main()
