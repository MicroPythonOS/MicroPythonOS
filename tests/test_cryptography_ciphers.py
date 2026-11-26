"""AES-CBC through the cryptography compatibility layer must not print.

NIP-04 direct messages and Nostr Wallet Connect requests are encrypted with
these classes, so anything they print puts message contents on the serial
console.
"""

import builtins
import sys
import unittest

sys.path.insert(0, "lib")

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

KEY = bytes(range(32))
IV = bytes(range(100, 116))
BLOCK_BITS = 128
MESSAGE = b"pay 21 sats to the piggy, and keep this line off the console"


def _run_and_capture_prints(action):
    """Run action() and return (its result, every line it printed)."""
    printed = []
    original_print = builtins.print

    def _recording_print(*args, **kwargs):
        printed.append(" ".join(str(a) for a in args))

    builtins.print = _recording_print
    try:
        result = action()
    finally:
        builtins.print = original_print
    return result, printed


def _encrypt(message):
    padder = padding.PKCS7(BLOCK_BITS).padder()
    padded = padder.update(message) + padder.finalize()
    encryptor = Cipher(algorithms.AES(KEY), modes.CBC(IV)).encryptor()
    return encryptor.update(padded) + encryptor.finalize()


def _decrypt(ciphertext):
    decryptor = Cipher(algorithms.AES(KEY), modes.CBC(IV)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(BLOCK_BITS).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


class TestCiphersDoNotPrint(unittest.TestCase):

    def test_capture_sees_prints(self):
        """The capture helper itself works, so an empty capture means silence."""
        _, printed = _run_and_capture_prints(lambda: print("canary", 42))
        self.assertEqual(printed, ["canary 42"])

    def test_round_trip(self):
        """What goes in comes back out, and the ciphertext is not the message."""
        ciphertext = _encrypt(MESSAGE)
        self.assertEqual(len(ciphertext) % 16, 0)
        self.assertTrue(MESSAGE not in ciphertext)
        self.assertEqual(_decrypt(ciphertext), MESSAGE)

    def test_encrypt_prints_nothing(self):
        """Padding and encrypting a whole message, as NIP-04 does, is silent."""
        ciphertext, printed = _run_and_capture_prints(lambda: _encrypt(MESSAGE))
        self.assertEqual(printed, [])
        self.assertEqual(_decrypt(ciphertext), MESSAGE)

    def test_decrypt_prints_nothing(self):
        """Decrypting and unpadding a whole message is silent."""
        ciphertext = _encrypt(MESSAGE)
        plaintext, printed = _run_and_capture_prints(lambda: _decrypt(ciphertext))
        self.assertEqual(printed, [])
        self.assertEqual(plaintext, MESSAGE)

    def test_encrypt_in_pieces_prints_nothing(self):
        """Pieces that do not end on a block boundary are buffered silently."""
        padder = padding.PKCS7(BLOCK_BITS).padder()
        padded = padder.update(MESSAGE) + padder.finalize()

        def _encrypt_in_pieces():
            encryptor = Cipher(algorithms.AES(KEY), modes.CBC(IV)).encryptor()
            out = b""
            for start in range(0, len(padded), 10):
                out += encryptor.update(padded[start:start + 10])
            return out + encryptor.finalize()

        ciphertext, printed = _run_and_capture_prints(_encrypt_in_pieces)
        self.assertEqual(printed, [])
        self.assertEqual(_decrypt(ciphertext), MESSAGE)

    def test_decrypt_in_pieces_prints_nothing(self):
        """The decryptor buffers uneven pieces just as silently."""
        ciphertext = _encrypt(MESSAGE)

        def _decrypt_in_pieces():
            decryptor = Cipher(algorithms.AES(KEY), modes.CBC(IV)).decryptor()
            out = b""
            for start in range(0, len(ciphertext), 10):
                out += decryptor.update(ciphertext[start:start + 10])
            out += decryptor.finalize()
            unpadder = padding.PKCS7(BLOCK_BITS).unpadder()
            return unpadder.update(out) + unpadder.finalize()

        plaintext, printed = _run_and_capture_prints(_decrypt_in_pieces)
        self.assertEqual(printed, [])
        self.assertEqual(plaintext, MESSAGE)

    def test_encryptor_finalize_with_leftover_prints_nothing(self):
        """A leftover partial block reaches finalize(); its bytes stay private.

        AES-CBC refuses a partial block, so finalize() may raise: that is not
        what this test is about.
        """

        def _finalize_with_leftover():
            encryptor = Cipher(algorithms.AES(KEY), modes.CBC(IV)).encryptor()
            encryptor.update(b"secret!!")
            try:
                encryptor.finalize()
            except ValueError:
                pass

        _, printed = _run_and_capture_prints(_finalize_with_leftover)
        self.assertEqual(printed, [])

    def test_decryptor_finalize_with_leftover_prints_nothing(self):
        """The decryptor's finalize() keeps a leftover partial block private too."""

        def _finalize_with_leftover():
            decryptor = Cipher(algorithms.AES(KEY), modes.CBC(IV)).decryptor()
            decryptor.update(b"secret!!")
            try:
                decryptor.finalize()
            except ValueError:
                pass

        _, printed = _run_and_capture_prints(_finalize_with_leftover)
        self.assertEqual(printed, [])
