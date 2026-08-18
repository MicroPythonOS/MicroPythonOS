import unittest
import time as time_module
from mpos.time import epoch_seconds


class TestEpochSeconds(unittest.TestCase):

    def test_returns_int_on_desktop(self):
        result = epoch_seconds()
        self.assertIsInstance(result, int)

    def test_returns_positive_value(self):
        result = epoch_seconds()
        self.assertTrue(result > 0)

    def test_consistent_with_time_time(self):
        import sys
        a = int(epoch_seconds())
        current = int(time_module.time())
        if sys.platform == "esp32":
            current += 946684800
        diff = abs(a - current)
        self.assertTrue(diff <= 1)

