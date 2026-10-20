import unittest

import micropython

from mpos.ui import render_guard


class _FakeTaskHandler:

    def __init__(self):
        self.callbacks = []

    def add_event_cb(self, callback, event, user_data=None):
        self.callbacks.append((callback, event, user_data))


class TestRenderGuard(unittest.TestCase):

    def setUp(self):
        self._stack_size = render_guard.STACK_SIZE
        self._reserve = render_guard.RENDER_RESERVE

    def tearDown(self):
        render_guard.STACK_SIZE = self._stack_size
        render_guard.RENDER_RESERVE = self._reserve

    def test_unknown_stack_size_always_renders(self):
        render_guard.STACK_SIZE = None
        self.assertTrue(render_guard.has_render_headroom())
        self.assertTrue(render_guard.on_task_handler(1, None))

    def test_renders_when_the_reserve_fits_below_the_current_depth(self):
        render_guard.RENDER_RESERVE = 9 * 1024
        render_guard.STACK_SIZE = micropython.stack_use() + 16 * 1024
        self.assertTrue(render_guard.has_render_headroom())
        self.assertTrue(render_guard.on_task_handler(1, None))

    def test_skips_the_pass_when_the_reserve_does_not_fit(self):
        render_guard.RENDER_RESERVE = 9 * 1024
        render_guard.STACK_SIZE = micropython.stack_use() + 4 * 1024
        self.assertFalse(render_guard.has_render_headroom())
        self.assertIs(render_guard.on_task_handler(1, None), False)

    def test_deeper_code_loses_headroom_first(self):
        render_guard.RENDER_RESERVE = 9 * 1024
        render_guard.STACK_SIZE = micropython.stack_use() + render_guard.RENDER_RESERVE + 512

        def deeper(levels):
            if levels:
                return deeper(levels - 1)
            return render_guard.has_render_headroom()

        self.assertTrue(render_guard.has_render_headroom())
        self.assertFalse(deeper(40))

    def test_esp32_reserve_leaves_room_for_a_measured_pass(self):
        self.assertTrue(render_guard.RENDER_RESERVE >= 7344 + 1024)
        if render_guard.STACK_SIZE is not None:
            self.assertTrue(render_guard.STACK_SIZE - render_guard.RENDER_RESERVE >= 6 * 1024)

    def test_install_registers_a_started_callback(self):
        handler = _FakeTaskHandler()
        render_guard.install(handler, 1)
        self.assertEqual(handler.callbacks, [(render_guard.on_task_handler, 1, None)])


if __name__ == "__main__":
    unittest.main()
