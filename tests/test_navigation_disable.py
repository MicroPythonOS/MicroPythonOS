"""
Unit tests for global navigation disable APIs (on InputManager).

Covers:
- InputManager.set_back_screen_disabled() / is_back_screen_disabled()
- InputManager.set_drawer_open_disabled() / is_drawer_open_disabled()
- back_screen() returns False and forwards lv.KEY.ESC when disabled
- open_drawer() / toggle_drawer() forward lv.KEY.HOME when disabled
- Graceful no-op when no focus group exists
"""

import sys
import unittest

from mpos.ui import view as view_module
from mpos.ui import topmenu as topmenu_module
from mpos.ui.input_manager import InputManager

from mpos.testing.mocks import create_mock_module


def _make_mock_lvgl():
    m = create_mock_module("lvgl")
    m.KEY = create_mock_module("KEY")
    m.KEY.ESC = 27
    m.KEY.HOME = 2
    m._sent_keys = []
    m._group = object()
    m.group_get_default = lambda: m._group
    m.group_send_data = lambda group, key: m._sent_keys.append(key)
    return m


class TestBackScreenDisable(unittest.TestCase):
    def setUp(self):
        self._orig_back = InputManager._back_screen_disabled
        self._orig_lv = getattr(view_module, "lv", None)
        self._orig_stack = view_module.screen_stack[:]
        InputManager._back_screen_disabled = False
        self._mock_lv = _make_mock_lvgl()
        view_module.lv = self._mock_lv

    def tearDown(self):
        InputManager._back_screen_disabled = self._orig_back
        view_module.screen_stack[:] = self._orig_stack
        if self._orig_lv is not None:
            view_module.lv = self._orig_lv

    def test_set_disabled_getter(self):
        self.assertFalse(InputManager.is_back_screen_disabled())
        InputManager.set_back_screen_disabled(True)
        self.assertTrue(InputManager.is_back_screen_disabled())
        InputManager.set_back_screen_disabled(False)
        self.assertFalse(InputManager.is_back_screen_disabled())

    def test_disabled_forwards_esc_and_returns_false(self):
        InputManager.set_back_screen_disabled(True)
        orig_len = len(view_module.screen_stack)
        view_module.screen_stack.append((None, object(), None, None))
        view_module.screen_stack.append((None, object(), None, None))
        result = view_module.back_screen()
        self.assertFalse(result)
        self.assertEqual(self._mock_lv._sent_keys, [27])
        self.assertEqual(len(view_module.screen_stack), orig_len + 2)

    def test_disabled_returns_false_empty_stack(self):
        InputManager.set_back_screen_disabled(True)
        result = view_module.back_screen()
        self.assertFalse(result)
        self.assertEqual(self._mock_lv._sent_keys, [27])

    def test_disabled_no_group_returns_false(self):
        InputManager.set_back_screen_disabled(True)
        self._mock_lv.group_get_default = lambda: None
        view_module.screen_stack.append((None, object(), None, None))
        result = view_module.back_screen()
        self.assertFalse(result)
        self.assertEqual(self._mock_lv._sent_keys, [])


class TestDrawerOpenDisable(unittest.TestCase):
    def setUp(self):
        self._orig_drawer = InputManager._drawer_open_disabled
        self._orig_drawer_open = topmenu_module.drawer_open
        self._orig_lv = getattr(topmenu_module, "lv", None)
        InputManager._drawer_open_disabled = False
        self._mock_lv = _make_mock_lvgl()
        topmenu_module.lv = self._mock_lv

    def tearDown(self):
        InputManager._drawer_open_disabled = self._orig_drawer
        topmenu_module.drawer_open = self._orig_drawer_open
        if self._orig_lv is not None:
            topmenu_module.lv = self._orig_lv

    def test_set_disabled_getter(self):
        self.assertFalse(InputManager.is_drawer_open_disabled())
        InputManager.set_drawer_open_disabled(True)
        self.assertTrue(InputManager.is_drawer_open_disabled())
        InputManager.set_drawer_open_disabled(False)
        self.assertFalse(InputManager.is_drawer_open_disabled())

    def test_disabled_open_drawer_forwards_home(self):
        InputManager.set_drawer_open_disabled(True)
        topmenu_module.drawer_open = False
        topmenu_module.open_drawer()
        self.assertEqual(self._mock_lv._sent_keys, [2])
        self.assertFalse(topmenu_module.drawer_open)

    def test_disabled_open_drawer_no_group(self):
        InputManager.set_drawer_open_disabled(True)
        self._mock_lv.group_get_default = lambda: None
        topmenu_module.open_drawer()
        self.assertEqual(self._mock_lv._sent_keys, [])

    def test_disabled_toggle_drawer_forwards_home_when_closed(self):
        InputManager.set_drawer_open_disabled(True)
        topmenu_module.drawer_open = False
        topmenu_module.toggle_drawer()
        self.assertEqual(self._mock_lv._sent_keys, [2])
        self.assertFalse(topmenu_module.drawer_open)

    def test_disabled_toggle_drawer_no_group(self):
        InputManager.set_drawer_open_disabled(True)
        self._mock_lv.group_get_default = lambda: None
        topmenu_module.drawer_open = False
        topmenu_module.toggle_drawer()
        self.assertEqual(self._mock_lv._sent_keys, [])


if __name__ == "__main__":
    unittest.main()
