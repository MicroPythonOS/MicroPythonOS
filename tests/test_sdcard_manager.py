import unittest
from mpos import SDCardManager


class TestSDCardManager(unittest.TestCase):

    def test_unmounted_by_default(self):
        self.assertFalse(SDCardManager.is_mounted())
        self.assertIsNone(SDCardManager.get_mount_point())

    def test_mount_returns_bool(self):
        result = SDCardManager.mount()
        self.assertIsInstance(result, bool)

    def test_no_instance_returns_false(self):
        self.assertFalse(SDCardManager.is_mounted())
        self.assertIsNone(SDCardManager.get_mode())
        self.assertIsNone(SDCardManager.get_raw())
        self.assertIsNone(SDCardManager.get_mount_point())


if __name__ == "__main__":
    unittest.main()
