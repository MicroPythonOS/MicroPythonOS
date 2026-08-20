import unittest
from mpos import SDCardManager


class TestSDCardManager(unittest.TestCase):

    def setUp(self):
        SDCardManager._instance = None

    def test_unmounted_by_default(self):
        self.assertFalse(SDCardManager.is_mounted())
        self.assertIsNone(SDCardManager.get_mount_point())

    def test_mount_returns_bool(self):
        result = SDCardManager.mount()
        self.assertIsInstance(result, bool)

    def test_mount_format_false_is_default(self):
        result = SDCardManager.mount()
        result_explicit = SDCardManager.mount(format=False)
        self.assertEqual(type(result), type(result_explicit))

    def test_mount_format_true_returns_bool(self):
        result = SDCardManager.mount(format=True)
        self.assertIsInstance(result, bool)

    def test_format_returns_bool(self):
        result = SDCardManager.format()
        self.assertIsInstance(result, bool)
        self.assertFalse(result)

    def test_no_instance_returns_false(self):
        self.assertFalse(SDCardManager.is_mounted())
        self.assertIsNone(SDCardManager.get_mode())
        self.assertIsNone(SDCardManager.get_raw())
        self.assertIsNone(SDCardManager.get_mount_point())


if __name__ == "__main__":
    unittest.main()
