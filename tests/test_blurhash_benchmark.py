import sys
sys.path.insert(0, "builtin/apps/com.micropythonos.appstore")
sys.path.insert(0, "lib")

import unittest
import time

from blurhash import (
    decode_blurhash,
    decode_blurhash_native,
    decode_blurhash_viper,
)

_TEST_HASH = "UBMOZfK1GG%LBBNG,;Rj2skq=eE1s9n4S5Na"
_BADGEHUB_HASH = "LfNnURxu}]xvxvj[X3j@}wj[EdfP"

_ITERATIONS = 10


def _benchmark(func, hash_str, width, height):
    t0 = time.ticks_us()
    for _ in range(_ITERATIONS):
        func(hash_str, width, height)
    t1 = time.ticks_us()
    return time.ticks_diff(t1, t0)


class TestBlurhashBenchmark(unittest.TestCase):

    def test_benchmark_32x32(self):
        pure = _benchmark(decode_blurhash, _TEST_HASH, 32, 32)
        native = _benchmark(decode_blurhash_native, _TEST_HASH, 32, 32)
        viper = _benchmark(decode_blurhash_viper, _TEST_HASH, 32, 32)

        self.assertTrue(pure > 0)
        self.assertTrue(native > 0)
        self.assertTrue(viper > 0)

        print("\n32x32 (%d iterations):" % _ITERATIONS)
        print("  pure:   %d us (%.1fx)" % (pure, 1.0))
        print("  native: %d us (%.1fx)" % (native, pure / native))
        print("  viper:  %d us (%.1fx)" % (viper, pure / viper))

    def test_benchmark_64x64(self):
        pure = _benchmark(decode_blurhash, _TEST_HASH, 64, 64)
        native = _benchmark(decode_blurhash_native, _TEST_HASH, 64, 64)
        viper = _benchmark(decode_blurhash_viper, _TEST_HASH, 64, 64)

        print("\n64x64 (%d iterations):" % _ITERATIONS)
        print("  pure:   %d us (%.1fx)" % (pure, 1.0))
        print("  native: %d us (%.1fx)" % (native, pure / native))
        print("  viper:  %d us (%.1fx)" % (viper, pure / viper))

    def test_benchmark_badgehub_64x64(self):
        pure = _benchmark(decode_blurhash, _BADGEHUB_HASH, 64, 64)
        native = _benchmark(decode_blurhash_native, _BADGEHUB_HASH, 64, 64)
        viper = _benchmark(decode_blurhash_viper, _BADGEHUB_HASH, 64, 64)

        print("\nBadgeHub 64x64 (%d iterations):" % _ITERATIONS)
        print("  pure:   %d us (%.1fx)" % (pure, 1.0))
        print("  native: %d us (%.1fx)" % (native, pure / native))
        print("  viper:  %d us (%.1fx)" % (viper, pure / viper))

    def test_benchmark_16x16(self):
        pure = _benchmark(decode_blurhash, _TEST_HASH, 16, 16)
        native = _benchmark(decode_blurhash_native, _TEST_HASH, 16, 16)
        viper = _benchmark(decode_blurhash_viper, _TEST_HASH, 16, 16)

        print("\n16x16 (%d iterations):" % _ITERATIONS)
        print("  pure:   %d us (%.1fx)" % (pure, 1.0))
        print("  native: %d us (%.1fx)" % (native, pure / native))
        print("  viper:  %d us (%.1fx)" % (viper, pure / viper))


if __name__ == "__main__":
    unittest.main()
