import unittest
import sys


class MockLVGL:
    class obj:
        FLAG_HIDDEN = 1

    class label:
        pass

    class textarea:
        pass

    @staticmethod
    def group_get_default():
        return None


def _mock_lvgl():
    lv_mock = type("module", (), {
        "obj": MockLVGL.obj,
        "label": MockLVGL.label,
        "textarea": MockLVGL.textarea,
        "group_get_default": MockLVGL.group_get_default,
    })()
    sys.modules["lvgl"] = lv_mock


class TestClipboard(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        _mock_lvgl()

    def setUp(self):
        import mpos.clipboard
        mpos.clipboard.copied = None

    def test_get_returns_none_initially(self):
        from mpos.clipboard import get
        self.assertIsNone(get())

    def test_add_then_get_returns_value(self):
        from mpos.clipboard import add, get
        add("hello world")
        self.assertEqual(get(), "hello world")

    def test_add_overwrites_previous(self):
        from mpos.clipboard import add, get
        add("first")
        add("second")
        self.assertEqual(get(), "second")

    def test_add_empty_string(self):
        from mpos.clipboard import add, get
        add("")
        self.assertEqual(get(), "")

