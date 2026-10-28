"""lib/secp256k1.py must still verify signatures when compiled without asserts.

The macOS and web builds freeze lib/ with mpy-cross -O3, which drops every
assert statement, and so any call made inside one. PublicKey used to fill
its x-only key inside an assert: in those builds the key stayed all zeros
and every Schnorr verify failed, so Event.verify() returned False for good
signatures (relay events dropped, NIP-17 seals rejected).

micropython.opt_level(3) makes the next import compile the same way, so the
test imports a fresh copy of lib/secp256k1.py at that level.
"""

import sys
import unittest

import micropython

from nostr.event import Event
from nostr.key import PrivateKey


def _fresh_secp256k1(opt_level):
    """Import lib/secp256k1.py again, compiled at `opt_level`.

    The original module is put back in sys.modules afterwards, so the rest
    of the process keeps using it.
    """
    saved_module = sys.modules.pop("secp256k1", None)
    saved_level = micropython.opt_level()
    micropython.opt_level(opt_level)
    try:
        import secp256k1 as fresh
    finally:
        micropython.opt_level(saved_level)
        if saved_module is not None:
            sys.modules["secp256k1"] = saved_module
        else:
            sys.modules.pop("secp256k1", None)
    return fresh


class TestSecp256k1WithoutAsserts(unittest.TestCase):
    def setUp(self):
        key = PrivateKey()
        self.pubkey_hex = key.public_key.hex()
        event = Event(content="hi", public_key=self.pubkey_hex, created_at=1700000000,
                      kind=1, tags=[])
        key.sign_event(event)
        self.event_id = bytes.fromhex(event.id)
        self.signature = bytes.fromhex(event.signature)

    def _verify_with(self, secp):
        pubkey = secp.PublicKey(bytes.fromhex("02" + self.pubkey_hex), True)
        return pubkey.schnorr_verify(self.event_id, self.signature, None, raw=True)

    def test_opt_level_3_drops_asserts(self):
        # The premise: code compiled at level 3 skips a failing assert.
        saved_level = micropython.opt_level()
        micropython.opt_level(3)
        try:
            exec("assert False, 'kept'")
        finally:
            micropython.opt_level(saved_level)

    def test_fresh_copy_is_compiled_from_lib_source(self):
        # A frozen module's __file__ has no directory; the fix lives in lib/.
        fresh = _fresh_secp256k1(3)
        if not fresh.__file__.endswith("lib/secp256k1.py"):
            self.skipTest(
                "frozen build without lib/ on disk: the re-imported module is the -O3 frozen one, "
                "which the signature tests below verify"
            )
        self.assertTrue(fresh.__file__.endswith("lib/secp256k1.py"), fresh.__file__)

    def test_schnorr_verify_with_asserts(self):
        self.assertTrue(self._verify_with(_fresh_secp256k1(0)))

    def test_schnorr_verify_without_asserts(self):
        self.assertTrue(self._verify_with(_fresh_secp256k1(3)))

    def test_wrong_signature_still_fails_without_asserts(self):
        self.signature = bytes(64)
        self.assertFalse(self._verify_with(_fresh_secp256k1(3)))


if __name__ == "__main__":
    unittest.main()
