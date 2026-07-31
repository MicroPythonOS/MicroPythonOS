import unittest
from mpos import clipboard


class TestClipboard(unittest.TestCase):

    def setUp(self):
        clipboard.copied = None

    def test_initial_none(self):
        clipboard.copied = None
        self.assertIsNone(clipboard.get())

    def test_add_and_get_string(self):
        clipboard.add("hello world")
        self.assertEqual(clipboard.get(), "hello world")

    def test_add_and_get_int(self):
        clipboard.add(42)
        self.assertEqual(clipboard.get(), 42)

    def test_add_and_get_list(self):
        data = [1, 2, 3]
        clipboard.add(data)
        self.assertEqual(clipboard.get(), data)

    def test_add_overwrites_previous(self):
        clipboard.add("first")
        self.assertEqual(clipboard.get(), "first")
        clipboard.add("second")
        self.assertEqual(clipboard.get(), "second")

    def test_add_none(self):
        clipboard.add("something")
        self.assertEqual(clipboard.get(), "something")
        clipboard.add(None)
        self.assertIsNone(clipboard.get())

    def test_get_returns_copied_value(self):
        clipboard.copied = "direct"
        self.assertEqual(clipboard.get(), "direct")
