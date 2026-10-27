"""Base64 through lib/binascii.py and lib/base64.py.

lib/binascii.py used to redefine b2a_base64/a2b_base64 in pure Python on top of
``from ubinascii import *``, shadowing the C implementations with O(n^2) ones
(13.6 ms per 3000-byte round-trip on a desktop build versus 0.026 ms in C, far
worse on an ESP32). These tests pin the C functions, check their output against
RFC 4648 and a small pure-Python reference encoder for every size 0..3000, cover
invalid input, and keep a coarse timing bound that the pure-Python version fails.

They also pin binascii.Error and base64.urlsafe_b64decode(). lib/binascii.py
defined no Error, so the b64decode(validate=True), b32decode() and b16decode()
error paths in lib/base64.py raised AttributeError instead of ValueError, and
urlsafe_b64decode() was a NotImplementedError stub (MicroPython has no
bytes.translate(); the altchars path of b64decode() does the same job).

A str with a non-ASCII character must raise ValueError, as in CPython. The
decoders used to accept it silently: MicroPython's str.encode("ascii") ignores
the codec and returns UTF-8 bytes, which b64decode() then skipped as
non-alphabet input. Non-ASCII test strings are built with chr(), because the
desktop runner pastes this file into the REPL, where non-ASCII literals and
unicode escapes are lost.

The OS imports binascii and base64 at boot (webrepl, secrets, aiohttp, nostr),
so both are evicted from sys.modules first: the tests then exercise the copies
found on sys.path (lib/ on the desktop build, the frozen ones on a device)
instead of whatever the running firmware cached at boot.
"""

import sys
import time
import unittest

sys.path.insert(0, "lib")
for _name in ("base64", "binascii"):
    sys.modules.pop(_name, None)

import base64
import binascii
import ubinascii


_ALPHABET = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_MAX_SIZE = 3000

_RFC4648 = (
    (b"", b""),
    (b"f", b"Zg=="),
    (b"fo", b"Zm8="),
    (b"foo", b"Zm9v"),
    (b"foob", b"Zm9vYg=="),
    (b"fooba", b"Zm9vYmE="),
    (b"foobar", b"Zm9vYmFy"),
)


def _make_data(size, seed=12345):
    buf = bytearray(size)
    for i in range(size):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        buf[i] = (seed >> 16) & 0xFF
    return bytes(buf)


_DATA = _make_data(_MAX_SIZE)


def _ref_b64encode(data):
    out = bytearray()
    full = len(data) - len(data) % 3
    for i in range(0, full, 3):
        n = (data[i] << 16) | (data[i + 1] << 8) | data[i + 2]
        out.append(_ALPHABET[(n >> 18) & 63])
        out.append(_ALPHABET[(n >> 12) & 63])
        out.append(_ALPHABET[(n >> 6) & 63])
        out.append(_ALPHABET[n & 63])
    rem = len(data) - full
    if rem == 1:
        n = data[full] << 16
        out.append(_ALPHABET[(n >> 18) & 63])
        out.append(_ALPHABET[(n >> 12) & 63])
        out.extend(b"==")
    elif rem == 2:
        n = (data[full] << 16) | (data[full + 1] << 8)
        out.append(_ALPHABET[(n >> 18) & 63])
        out.append(_ALPHABET[(n >> 12) & 63])
        out.append(_ALPHABET[(n >> 6) & 63])
        out.extend(b"=")
    return bytes(out)


class TestBinasciiIsC(unittest.TestCase):
    def test_lib_binascii_exposes_c_base64(self):
        self.assertTrue(binascii.b2a_base64 is ubinascii.b2a_base64)
        self.assertTrue(binascii.a2b_base64 is ubinascii.a2b_base64)

    def test_hex_shims_kept(self):
        self.assertEqual(binascii.hexlify(b"\x01\xff"), b"01ff")
        self.assertEqual(binascii.b2a_hex(b"\x01\xff"), b"01ff")
        self.assertEqual(binascii.unhexlify(b"01ff"), b"\x01\xff")
        self.assertEqual(binascii.a2b_hex(b"01ff"), b"\x01\xff")

    def test_error_is_a_valueerror(self):
        self.assertTrue(issubclass(binascii.Error, ValueError))
        with self.assertRaises(binascii.Error):
            binascii.a2b_base64(b"Q")
        with self.assertRaises(binascii.Error):
            binascii.unhexlify(b"0G")


class TestBase64RoundTrip(unittest.TestCase):
    def test_rfc4648_vectors(self):
        for raw, enc in _RFC4648:
            self.assertEqual(binascii.b2a_base64(raw), enc + b"\n")
            self.assertEqual(binascii.a2b_base64(enc), raw)
            self.assertEqual(base64.b64encode(raw), enc)
            self.assertEqual(base64.b64decode(enc), raw)
            self.assertEqual(base64.standard_b64encode(raw), enc)
            self.assertEqual(base64.standard_b64decode(enc), raw)

    def test_roundtrip_every_size_0_to_3000(self):
        for n in range(_MAX_SIZE + 1):
            data = _DATA[:n]
            pad = (3 - n % 3) % 3
            enc = binascii.b2a_base64(data)
            self.assertEqual(len(enc), ((n + 2) // 3) * 4 + 1, "size %d" % n)
            self.assertEqual(enc[-1:], b"\n", "size %d" % n)
            body = enc[:-1]
            self.assertEqual(body[len(body) - pad :], b"=" * pad, "size %d" % n)
            self.assertEqual(body[: len(body) - pad].strip(_ALPHABET), b"", "size %d" % n)
            self.assertEqual(binascii.a2b_base64(enc), data, "size %d" % n)
            self.assertEqual(binascii.a2b_base64(body), data, "size %d" % n)
            b64 = base64.b64encode(data)
            self.assertEqual(b64, body, "size %d" % n)
            self.assertEqual(base64.b64decode(b64), data, "size %d" % n)

    def test_matches_reference_encoder(self):
        sizes = list(range(0, 513)) + list(range(513, _MAX_SIZE + 1, 251)) + [_MAX_SIZE]
        for n in sizes:
            data = _DATA[:n]
            self.assertEqual(binascii.b2a_base64(data), _ref_b64encode(data) + b"\n", "size %d" % n)

    def test_newline_kwarg(self):
        self.assertEqual(binascii.b2a_base64(b"abc", newline=True), b"YWJj\n")
        self.assertEqual(binascii.b2a_base64(b"abc", newline=False), b"YWJj")
        self.assertEqual(binascii.b2a_base64(b"", newline=False), b"")

    def test_urlsafe_and_legacy_api(self):
        data = _DATA[:1000]
        self.assertEqual(base64.urlsafe_b64encode(data), base64.b64encode(data).replace(b"+", b"-").replace(b"/", b"_"))
        self.assertEqual(base64.b64decode(base64.urlsafe_b64encode(data), altchars=b"-_"), data)
        self.assertEqual(base64.urlsafe_b64encode(b"\xfb\xff"), b"-_8=")
        self.assertEqual(base64.b64encode(b"\xfb\xff"), b"+/8=")
        lines = base64.encodebytes(data)
        self.assertEqual(lines[-1:], b"\n")
        self.assertEqual(lines.count(b"\n"), (len(data) + 56) // 57)
        self.assertEqual(base64.decodebytes(lines), data)
        self.assertEqual(base64.b16decode(base64.b16encode(data)), data)
        self.assertEqual(base64.b32decode(base64.b32encode(data[:100])), data[:100])


class TestBase64InvalidInput(unittest.TestCase):
    def test_non_alphabet_bytes_are_skipped(self):
        self.assertEqual(binascii.a2b_base64(b"YW\r\nJj\n"), b"abc")
        self.assertEqual(binascii.a2b_base64(b"YW Jj"), b"abc")
        self.assertEqual(binascii.a2b_base64(b"Y-W_J*j"), b"abc")
        self.assertEqual(binascii.a2b_base64(b"!!!"), b"")
        self.assertEqual(binascii.a2b_base64(b""), b"")
        self.assertEqual(base64.b64decode(b"YW\nJj"), b"abc")

    def test_incorrect_padding_raises_valueerror(self):
        for bad in (b"Q", b"QQ", b"QQ=", b"QQQ", b"QQQQQ", b"QQQQQQ", b"QQQQQQQ"):
            with self.assertRaises(ValueError):
                binascii.a2b_base64(bad)
            with self.assertRaises(ValueError):
                base64.b64decode(bad)

    def test_padding_variants(self):
        self.assertEqual(binascii.a2b_base64(b"QQ=="), b"A")
        self.assertEqual(binascii.a2b_base64(b"QUI="), b"AB")
        self.assertEqual(binascii.a2b_base64(b"QUJD"), b"ABC")
        self.assertEqual(binascii.a2b_base64(b"QQ==QUI="), b"A")
        self.assertEqual(binascii.a2b_base64(b"QUJDQQ=="), b"ABCA")
        self.assertEqual(binascii.a2b_base64(b"QQQQQQQ="), b"A\x04\x10A\x04")

    def test_str_input_accepted(self):
        self.assertEqual(binascii.a2b_base64("YWJj"), b"abc")
        self.assertEqual(binascii.b2a_base64("abc"), b"YWJj\n")
        self.assertEqual(base64.b64decode("YWJj"), b"abc")


class TestBase64Validate(unittest.TestCase):
    def test_validate_accepts_alphabet_only_input(self):
        self.assertEqual(base64.b64decode(b"YWJj", validate=True), b"abc")
        self.assertEqual(base64.b64decode(b"QQ==", validate=True), b"A")
        self.assertEqual(base64.b64decode(b"", validate=True), b"")
        self.assertEqual(base64.b64decode("YWJj", validate=True), b"abc")
        self.assertEqual(base64.b64decode(b"+/8=", validate=True), b"\xfb\xff")
        # altchars are translated back before the alphabet check
        self.assertEqual(base64.b64decode(b"-_8=", altchars=b"-_", validate=True), b"\xfb\xff")

    def test_validate_rejects_non_alphabet_input(self):
        for bad in (b"YW\nJj", b"YW Jj", b"Y-W_Jj", b"YW*Jj", b"-_8=", b"YWJj\n"):
            with self.assertRaises(ValueError):
                base64.b64decode(bad, validate=True)
            with self.assertRaises(binascii.Error):
                base64.b64decode(bad, validate=True)
        # the same input is accepted without validate: non-alphabet bytes are skipped
        self.assertEqual(base64.b64decode(b"YW\nJj"), b"abc")
        self.assertEqual(base64.b64decode(b"Y-W_Jj"), b"abc")


class TestBase32Base16(unittest.TestCase):
    _RFC4648_B32 = (
        (b"", b""),
        (b"f", b"MY======"),
        (b"fo", b"MZXQ===="),
        (b"foo", b"MZXW6==="),
        (b"foob", b"MZXW6YQ="),
        (b"fooba", b"MZXW6YTB"),
        (b"foobar", b"MZXW6YTBOI======"),
    )

    def test_b32_rfc4648_vectors(self):
        for raw, enc in self._RFC4648_B32:
            self.assertEqual(base64.b32encode(raw), enc)
            self.assertEqual(base64.b32decode(enc), raw)
        self.assertEqual(base64.b32decode(b"mzxw6ytboi======", casefold=True), b"foobar")
        self.assertEqual(base64.b32decode(b"MZXW6YTB01======", map01=b"I"), b"foobar")
        self.assertEqual(base64.b32decode("MZXW6YTBOI======"), b"foobar")

    def test_b32_errors_raise_valueerror(self):
        for bad in (
            b"A",  # length not a multiple of 8
            b"MZXW6YTBOI=====",
            b"mzxw6ytboi======",  # lowercase without casefold
            b"MZXW6YTB01======",  # 0 and 1 without map01
            b"!!!!!!!!",  # non-alphabet bytes
            b"MZXW6YTBOIA=====",  # 5 pad chars is never valid
            b"MZXW6YTBOIAAAA==",  # nor 2
            b"MZXW6YTBO=======",  # nor 7
        ):
            with self.assertRaises(ValueError):
                base64.b32decode(bad)

    def test_b16_vectors(self):
        self.assertEqual(base64.b16encode(b""), b"")
        self.assertEqual(base64.b16encode(b"\x01\xab"), b"01AB")
        self.assertEqual(base64.b16decode(b"01AB"), b"\x01\xab")
        self.assertEqual(base64.b16decode("01AB"), b"\x01\xab")
        self.assertEqual(base64.b16decode(b"01ab", casefold=True), b"\x01\xab")
        self.assertEqual(base64.b16decode(b""), b"")

    def test_b16_errors_raise_valueerror(self):
        for bad in (
            b"01ab",  # lowercase without casefold
            b"0G",
            b"01 AB",
            b"01AB\n",
            b"0",  # odd length (rejected by unhexlify)
            b"0AB",
        ):
            with self.assertRaises(ValueError):
                base64.b16decode(bad)


class TestUrlsafe(unittest.TestCase):
    def test_urlsafe_vectors(self):
        self.assertEqual(base64.urlsafe_b64encode(b"\xfb\xff"), b"-_8=")
        self.assertEqual(base64.urlsafe_b64decode(b"-_8="), b"\xfb\xff")
        self.assertEqual(base64.urlsafe_b64decode("-_8="), b"\xfb\xff")
        self.assertEqual(base64.urlsafe_b64decode(bytearray(b"-_8=")), b"\xfb\xff")
        # as in CPython, the standard alphabet still decodes
        self.assertEqual(base64.urlsafe_b64decode(b"+/8="), b"\xfb\xff")
        for raw, enc in _RFC4648:
            self.assertEqual(base64.urlsafe_b64encode(raw), enc)
            self.assertEqual(base64.urlsafe_b64decode(enc), raw)

    def test_urlsafe_roundtrip_every_size_0_to_300(self):
        urlsafe_alphabet = _ALPHABET.replace(b"+/", b"-_")
        for n in range(301):
            data = _DATA[:n]
            enc = base64.urlsafe_b64encode(data)
            self.assertEqual(enc.strip(urlsafe_alphabet + b"="), b"", "size %d" % n)
            self.assertEqual(base64.urlsafe_b64decode(enc), data, "size %d" % n)
        enc = base64.urlsafe_b64encode(_DATA)
        self.assertTrue(b"-" in enc and b"_" in enc)
        self.assertTrue(b"+" not in enc and b"/" not in enc)
        self.assertEqual(base64.urlsafe_b64decode(enc), _DATA)

    def test_urlsafe_errors(self):
        for bad in (b"-_8", b"Q", b"QQ="):
            with self.assertRaises(ValueError):
                base64.urlsafe_b64decode(bad)
        with self.assertRaises(TypeError):
            base64.urlsafe_b64decode(123)


class TestNonAsciiStr(unittest.TestCase):
    _MESSAGE = "string argument should contain only ASCII characters"
    # 2-, 3- and 4-byte UTF-8 characters, alone and next to valid input
    _NON_ASCII = (
        chr(233),
        chr(128),
        "YWJj" + chr(233),
        chr(0x20AC) + "QUJD",
        "QUJD" + chr(0x1F600) + "QUJD",
    )

    def _assert_rejected(self, decode, s, **kwargs):
        with self.assertRaises(ValueError) as cm:
            decode(s, **kwargs)
        # b32decode() and b16decode() reject the UTF-8 bytes of a non-ASCII str
        # as non-alphabet input anyway; the message says the str was refused
        self.assertEqual(str(cm.exception), self._MESSAGE, "%r raised %r" % (s, str(cm.exception)))

    def test_b64decode_rejects_non_ascii_str(self):
        for s in self._NON_ASCII:
            self._assert_rejected(base64.b64decode, s)
            self._assert_rejected(base64.b64decode, s, validate=True)
            self._assert_rejected(base64.standard_b64decode, s)

    def test_urlsafe_b64decode_rejects_non_ascii_str(self):
        for s in self._NON_ASCII:
            self._assert_rejected(base64.urlsafe_b64decode, s)

    def test_b32decode_rejects_non_ascii_str(self):
        for s in self._NON_ASCII + (chr(233) * 8,):
            self._assert_rejected(base64.b32decode, s)
            self._assert_rejected(base64.b32decode, s, casefold=True)

    def test_b16decode_rejects_non_ascii_str(self):
        for s in self._NON_ASCII:
            self._assert_rejected(base64.b16decode, s)
            self._assert_rejected(base64.b16decode, s, casefold=True)

    def test_altchars_and_map01_reject_non_ascii_str(self):
        # one character, but two UTF-8 bytes: the len(altchars) == 2 assert passed
        self._assert_rejected(base64.b64decode, b"QUJD", altchars=chr(233))
        self._assert_rejected(base64.b64decode, b"QUJD", altchars="-" + chr(233))
        self._assert_rejected(base64.b32decode, b"MZXW6YTB01======", map01=chr(233))

    def test_ascii_str_still_decodes(self):
        self.assertEqual(base64.b64decode(""), b"")
        self.assertEqual(base64.b64decode("YWJj"), b"abc")
        self.assertEqual(base64.b64decode("YWJj", validate=True), b"abc")
        self.assertEqual(base64.b64decode("-_8=", altchars="-_"), b"\xfb\xff")
        self.assertEqual(base64.standard_b64decode("QUJD"), b"ABC")
        self.assertEqual(base64.urlsafe_b64decode("-_8="), b"\xfb\xff")
        self.assertEqual(base64.b32decode("MZXW6YTBOI======"), b"foobar")
        self.assertEqual(base64.b32decode("mzxw6ytboi======", casefold=True), b"foobar")
        self.assertEqual(base64.b32decode("MZXW6YTB01======", map01="I"), b"foobar")
        self.assertEqual(base64.b16decode("01AB"), b"\x01\xab")
        self.assertEqual(base64.b16decode("01ab", casefold=True), b"\x01\xab")
        # chr(127) is the last ASCII character: skipped as non-alphabet input
        self.assertEqual(base64.b64decode("YWJj" + chr(127)), b"abc")
        with self.assertRaises(ValueError):
            base64.b64decode("YWJj" + chr(127), validate=True)
        enc = base64.b64encode(_DATA)
        self.assertEqual(base64.b64decode(enc.decode()), _DATA)
        self.assertEqual(base64.urlsafe_b64decode(base64.urlsafe_b64encode(_DATA).decode()), _DATA)


class TestBase64Timing(unittest.TestCase):
    def test_3000_byte_roundtrip_is_fast(self):
        """200 round-trips of 3000 bytes must finish within 1 s.

        Desktop build: ~5 ms with the C functions, ~2700 ms with the former
        pure-Python ones. Generous enough for an ESP32 or a CPU-limited CI run.
        """
        data = _DATA
        reps = 200
        t0 = time.ticks_ms()
        for _ in range(reps):
            self.assertEqual(binascii.a2b_base64(binascii.b2a_base64(data)), data)
        via_binascii = time.ticks_diff(time.ticks_ms(), t0)
        t0 = time.ticks_ms()
        for _ in range(reps):
            self.assertEqual(base64.b64decode(base64.b64encode(data)), data)
        via_base64 = time.ticks_diff(time.ticks_ms(), t0)
        print(
            "base64 timing: %d x %d bytes: binascii %d ms, base64 %d ms" % (reps, len(data), via_binascii, via_base64)
        )
        budget = 15000 if sys.platform == "esp32" else 1000
        self.assertTrue(via_binascii < budget, "binascii round-trips took %d ms" % via_binascii)
        self.assertTrue(via_base64 < budget, "base64 round-trips took %d ms" % via_base64)


if __name__ == "__main__":
    unittest.main()
