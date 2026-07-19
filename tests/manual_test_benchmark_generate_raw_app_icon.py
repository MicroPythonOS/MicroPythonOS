import sys
sys.path.insert(0, "builtin/apps/com.micropythonos.appstore")
sys.path.insert(0, "lib")

import unittest
import time

from blurhash import generate_raw_app_icon

_APP_NAME = "com.micropythonos.helloworld"
_ITERATIONS = 3 if sys.platform == "esp32" else 10


def _benchmark(app_name, size):
    t0 = time.ticks_us()
    for _ in range(_ITERATIONS):
        generate_raw_app_icon(app_name, size)
    t1 = time.ticks_us()
    return time.ticks_diff(t1, t0)


class TestAppIconBenchmark(unittest.TestCase):

    def test_benchmark_32x32(self):
        elapsed = _benchmark(_APP_NAME, 32)
        avg = elapsed // _ITERATIONS
        self.assertTrue(elapsed > 0)
        print("\n32x32 (avg of %d iterations):" % _ITERATIONS)
        print("  generate_raw_app_icon: %d us" % avg)

    def test_benchmark_64x64(self):
        elapsed = _benchmark(_APP_NAME, 64)
        avg = elapsed // _ITERATIONS
        print("\n64x64 (avg of %d iterations):" % _ITERATIONS)
        print("  generate_raw_app_icon: %d us" % avg)

    def test_benchmark_128x128(self):
        elapsed = _benchmark(_APP_NAME, 128)
        avg = elapsed // _ITERATIONS
        print("\n128x128 (avg of %d iterations):" % _ITERATIONS)
        print("  generate_raw_app_icon: %d us" % avg)


if __name__ == "__main__":
    unittest.main()
