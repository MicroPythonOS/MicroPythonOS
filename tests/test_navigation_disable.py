"""
Unit tests for global navigation disable APIs (on InputManager).

Covers:
- InputManager.set_back_screen_disabled() / is_back_screen_disabled()
- InputManager.set_drawer_open_disabled() / is_drawer_open_disabled()
- back_screen() calls callback when disabled, returns False
- open_drawer() / toggle_drawer() call callback when disabled
- Graceful no-op when no callback is set
"""

import sys
import unittest

from mpos.ui import view as view_module
from mpos.ui import topmenu as topmenu_module
from mpos.ui.input_manager import InputManager


class TestBackScreenDisable(unittest.TestCase):
    def setUp(self):
        self._orig_back = InputManager._back_screen_disabled
        self._orig_cb = InputManager._back_screen_cb
        self._orig_stack = view_module.screen_stack[:]
        InputManager._back_screen_disabled = False
        InputManager._back_screen_cb = None

    def tearDown(self):
        InputManager._back_screen_disabled = self._orig_back
        InputManager._back_screen_cb = self._orig_cb
        view_module.screen_stack[:] = self._orig_stack

    def test_set_disabled_getter(self):
        self.assertFalse(InputManager.is_back_screen_disabled())
        InputManager.set_back_screen_disabled(True)
        self.assertTrue(InputManager.is_back_screen_disabled())
        InputManager.set_back_screen_disabled(False)
        self.assertFalse(InputManager.is_back_screen_disabled())

    def test_disabled_calls_callback_and_returns_false(self):
        called = []
        InputManager.set_back_screen_disabled(True, cb=lambda: called.append(1))
        orig_len = len(view_module.screen_stack)
        view_module.screen_stack.append((None, object(), None, None))
        view_module.screen_stack.append((None, object(), None, None))
        result = view_module.back_screen()
        self.assertFalse(result)
        self.assertEqual(called, [1])
        self.assertEqual(len(view_module.screen_stack), orig_len + 2)

    def test_disabled_no_callback_returns_false(self):
        InputManager.set_back_screen_disabled(True)
        orig_len = len(view_module.screen_stack)
        view_module.screen_stack.append((None, object(), None, None))
        result = view_module.back_screen()
        self.assertFalse(result)
        self.assertEqual(len(view_module.screen_stack), orig_len + 1)

    def test_disabled_returns_false_empty_stack(self):
        called = []
        InputManager.set_back_screen_disabled(True, cb=lambda: called.append(1))
        result = view_module.back_screen()
        self.assertFalse(result)
        self.assertEqual(called, [1])


class TestDrawerOpenDisable(unittest.TestCase):
    def setUp(self):
        self._orig_drawer = InputManager._drawer_open_disabled
        self._orig_cb = InputManager._drawer_open_cb
        self._orig_drawer_open = topmenu_module.drawer_open
        InputManager._drawer_open_disabled = False
        InputManager._drawer_open_cb = None

    def tearDown(self):
        InputManager._drawer_open_disabled = self._orig_drawer
        InputManager._drawer_open_cb = self._orig_cb
        topmenu_module.drawer_open = self._orig_drawer_open

    def test_set_disabled_getter(self):
        self.assertFalse(InputManager.is_drawer_open_disabled())
        InputManager.set_drawer_open_disabled(True)
        self.assertTrue(InputManager.is_drawer_open_disabled())
        InputManager.set_drawer_open_disabled(False)
        self.assertFalse(InputManager.is_drawer_open_disabled())

    def test_disabled_open_drawer_calls_callback(self):
        called = []
        InputManager.set_drawer_open_disabled(True, cb=lambda: called.append(1))
        topmenu_module.drawer_open = False
        topmenu_module.open_drawer()
        self.assertEqual(called, [1])
        self.assertFalse(topmenu_module.drawer_open)

    def test_disabled_open_drawer_no_callback(self):
        InputManager.set_drawer_open_disabled(True)
        topmenu_module.drawer_open = False
        topmenu_module.open_drawer()
        self.assertFalse(topmenu_module.drawer_open)

    def test_disabled_toggle_drawer_calls_callback_when_closed(self):
        called = []
        InputManager.set_drawer_open_disabled(True, cb=lambda: called.append(1))
        topmenu_module.drawer_open = False
        topmenu_module.toggle_drawer()
        self.assertEqual(called, [1])
        self.assertFalse(topmenu_module.drawer_open)

    def test_disabled_toggle_drawer_no_callback_when_closed(self):
        InputManager.set_drawer_open_disabled(True)
        topmenu_module.drawer_open = False
        topmenu_module.toggle_drawer()
        self.assertFalse(topmenu_module.drawer_open)


if __name__ == "__main__":
    unittest.main()
