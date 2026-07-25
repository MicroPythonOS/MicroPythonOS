import unittest
import os
from mpos.util import urldecode, mkdir_parents


class TestUrlDecode(unittest.TestCase):

    def test_no_encoding(self):
        self.assertEqual(urldecode("hello"), "hello")
        self.assertEqual(urldecode("hello world"), "hello world")

    def test_basic_percent_encoding(self):
        self.assertEqual(urldecode("hello%20world"), "hello world")
        self.assertEqual(urldecode("%21%22%23"), '!"#')

    def test_hex_characters(self):
        self.assertEqual(urldecode("%41%42%43"), "ABC")
        self.assertEqual(urldecode("%3C%3E"), "<>")

    def test_empty_string(self):
        self.assertEqual(urldecode(""), "")

    def test_percent_only_no_following_chars(self):
        self.assertRaises(ValueError, urldecode, "100%")

    def test_mixed_percent_encoding(self):
        result = urldecode("hello%20world%77orld")
        self.assertEqual(result, "hello worldworld")

    def test_byte_sequences(self):
        self.assertEqual(urldecode("%C3%A9"), "\xc3\xa9")

    def test_plus_not_decoded(self):
        self.assertEqual(urldecode("hello+world"), "hello+world")


class TestMkdirParents(unittest.TestCase):

    def setUp(self):
        self.test_root = "tmp/test_mkdirparents"
        self._rmtree(self.test_root)

    def tearDown(self):
        self._rmtree(self.test_root)

    @staticmethod
    def _rmtree(path):
        if not path:
            return

        def _is_dir(s):
            try:
                return (os.stat(s)[0] & 0x4000) != 0
            except OSError:
                return False

        try:
            children = os.listdir(path)
        except OSError:
            return
        for child in children:
            child_path = f"{path}/{child}"
            if _is_dir(child_path):
                TestMkdirParents._rmtree(child_path)
            else:
                os.remove(child_path)
        try:
            os.rmdir(path)
        except OSError:
            pass

    def _exists(self, path):
        try:
            os.stat(path)
            return True
        except OSError:
            return False

    def test_creates_single_directory(self):
        d = f"{self.test_root}/single"
        self.assertFalse(self._exists(d))
        mkdir_parents(d)
        self.assertTrue(self._exists(d))

    def test_creates_nested_directories(self):
        d = f"{self.test_root}/a/b/c"
        self.assertFalse(self._exists(d))
        mkdir_parents(d)
        self.assertTrue(self._exists(d))
        self.assertTrue(self._exists(f"{self.test_root}/a"))
        self.assertTrue(self._exists(f"{self.test_root}/a/b"))

    def test_idempotent(self):
        d = f"{self.test_root}/exists"
        mkdir_parents(d)
        self.assertTrue(self._exists(d))
        mkdir_parents(d)
        self.assertTrue(self._exists(d))

    def test_empty_path_does_nothing(self):
        mkdir_parents("")
        self.assertFalse(self._exists(self.test_root))

    def test_absolute_path(self):
        d = f"/tmp/test_mkdirparents_abs/sub"
        self._rmtree(d)
        self.assertFalse(self._exists(d))
        mkdir_parents(d)
        self.assertTrue(self._exists(d))
        self._rmtree("/tmp/test_mkdirparents_abs")

    def test_raises_on_file_in_path(self):
        d = f"{self.test_root}/file_in_way"
        mkdir_parents(self.test_root)
        with open(d, "w") as f:
            f.write("block")
        self.assertTrue(self._exists(d))
        with self.assertRaises(OSError):
            mkdir_parents(f"{d}/sub")

