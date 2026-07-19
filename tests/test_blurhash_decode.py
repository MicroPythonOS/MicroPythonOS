import sys
sys.path.insert(0, "builtin/apps/com.micropythonos.appstore")
sys.path.insert(0, "lib")

import unittest

from blurhash import (
    decode_blurhash,
    decode_blurhash_native,
    decode_blurhash_viper,
    generate_raw_app_icon,
    blurhash_to_image_dsc,
)

# Known test hash from halcy/blurhash-python test suite
_TEST_HASH = "UBMOZfK1GG%LBBNG,;Rj2skq=eE1s9n4S5Na"

# Real BadgeHub hash from the appstore examples
_BADGEHUB_HASH = "LfNnURxu}]xvxvj[X3j@}wj[EdfP"


def _pixel_diff(a, b):
    total = 0
    for y in range(len(a)):
        for x in range(len(a[0])):
            ar, ag, ab = a[y][x]
            br, bg, bb = b[y][x]
            total += abs(ar - br) + abs(ag - bg) + abs(ab - bb)
    return total


class TestBlurhashDecode(unittest.TestCase):

    def test_decode_returns_list_of_rows(self):
        pixels = decode_blurhash(_TEST_HASH, 16, 16)
        self.assertIsNotNone(pixels)
        self.assertEqual(len(pixels), 16)
        self.assertEqual(len(pixels[0]), 16)
        self.assertEqual(len(pixels[0][0]), 3)

    def test_decode_all_pixels_valid(self):
        pixels = decode_blurhash(_TEST_HASH, 16, 16)
        for row in pixels:
            for r, g, b in row:
                self.assertTrue(0 <= r <= 255)
                self.assertTrue(0 <= g <= 255)
                self.assertTrue(0 <= b <= 255)

    def test_native_agrees_with_pure_python(self):
        pure = decode_blurhash(_TEST_HASH, 32, 32)
        native = decode_blurhash_native(_TEST_HASH, 32, 32)
        diff = _pixel_diff(pure, native)
        self.assertEqual(diff, 0, "native differs from pure python by %d" % diff)

    def test_viper_agrees_within_tolerance(self):
        pure = decode_blurhash(_TEST_HASH, 32, 32)
        viper = decode_blurhash_viper(_TEST_HASH, 32, 32)
        diff = _pixel_diff(pure, viper)
        # 32×32×3 channels × 2 tolerance ≈ 6144 max
        self.assertTrue(diff < 10000, "viper differs from pure python by %d" % diff)

    def test_badgehub_hash_decodes(self):
        for dec in [decode_blurhash, decode_blurhash_native, decode_blurhash_viper]:
            pixels = dec(_BADGEHUB_HASH, 64, 64)
            self.assertEqual(len(pixels), 64)
            self.assertEqual(len(pixels[0]), 64)
            self.assertEqual(len(pixels[0][0]), 3)

    def test_native_and_viper_badgehub_agree(self):
        native = decode_blurhash_native(_BADGEHUB_HASH, 64, 64)
        viper = decode_blurhash_viper(_BADGEHUB_HASH, 64, 64)
        diff = _pixel_diff(native, viper)
        self.assertTrue(diff < 10000, "viper vs native diff too large: %d" % diff)

    def test_invalid_hash_raises(self):
        with self.assertRaises(ValueError):
            decode_blurhash("short", 16, 16)
        with self.assertRaises(ValueError):
            decode_blurhash("123456", 16, 16)

    def test_different_sizes(self):
        for w, h in [(8, 8), (16, 16), (32, 32), (64, 64), (16, 32)]:
            pixels = decode_blurhash_native(_TEST_HASH, w, h)
            self.assertEqual(len(pixels), h)
            self.assertEqual(len(pixels[0]), w)

    def test_blurhash_to_image_dsc_with_valid_hash(self):
        dsc, buf = blurhash_to_image_dsc(_TEST_HASH, 64, 64)
        self.assertIsNotNone(dsc)
        self.assertIsNotNone(buf)
        self.assertEqual(len(buf), 64 * 64 * 2)

    def test_blurhash_to_image_dsc_none_for_empty(self):
        dsc, buf = blurhash_to_image_dsc(None, 64, 64)
        self.assertIsNone(dsc)
        self.assertIsNone(buf)

        dsc, buf = blurhash_to_image_dsc("", 64, 64)
        self.assertIsNone(dsc)
        self.assertIsNone(buf)

    def test_generate_raw_app_icon(self):
        dsc, buf = generate_raw_app_icon("com.test.myapp", 32)
        self.assertIsNotNone(dsc)
        self.assertIsNotNone(buf)
        self.assertEqual(len(buf), 32 * 32 * 2)

    def test_generate_raw_app_icon_different_names_produce_different_icons(self):
        _, buf1 = generate_raw_app_icon("com.foo.app", 32)
        _, buf2 = generate_raw_app_icon("com.bar.app", 32)
        self.assertNotEqual(buf1, buf2)

    def test_generate_raw_app_icon_same_name_same_icon(self):
        _, buf1 = generate_raw_app_icon("stable.name", 32)
        _, buf2 = generate_raw_app_icon("stable.name", 32)
        self.assertEqual(buf1, buf2)


if __name__ == "__main__":
    unittest.main()
