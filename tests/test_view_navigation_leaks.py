"""Regression tests for LVGL resource leaks in the activity navigation stack.

LVGL allocates from the MicroPython heap (lv_conf.h sets
LV_USE_STDLIB_MALLOC = LV_STDLIB_MPY) and keeps its global state in a GC root,
so anything LVGL never frees stays counted by gc.mem_alloc() forever.

Two things were leaked:
  * the per-activity focus group created by setContentView(). LVGL holds every
    group in a global linked list, so only an explicit delete() frees it.
  * the screens torn down by remove_and_stop_all_activities(). clean() only
    deletes a screen's children, not the screen itself, and that path has no
    screen_load_anim(..., auto_del=True) to do it either.
"""

import gc
import unittest

import lvgl as lv

import mpos.ui.view as view
from mpos.ui.testing import GraphicalTestCase


def _is_deleted(obj):
    """Report whether LVGL freed the object behind this binding wrapper.

    The binding invalidates the wrapper on delete and raises LvReferenceError
    on any later access.
    """
    try:
        obj.get_child_count()
    except Exception as e:
        return type(e).__name__ == "LvReferenceError"
    return False


class _StubActivity:
    """Minimal activity: the navigation stack only calls these lifecycle hooks."""

    appFullName = "com.micropythonos.leaktest"

    def onStart(self, screen): pass
    def onResume(self, screen): pass
    def onPause(self, screen): pass
    def onStop(self, screen): pass
    def onDestroy(self, screen): pass
    def onBackPressed(self, screen): return False


class TestNavigationLeaks(GraphicalTestCase):

    # Enough task_handler iterations to outlast the 500 ms load animation.
    ANIMATION_ITERATIONS = 70

    def setUp(self):
        super().setUp()
        self._saved_stack = view.screen_stack[:]
        del view.screen_stack[:]

    def tearDown(self):
        del view.screen_stack[:]
        view.screen_stack.extend(self._saved_stack)
        super().tearDown()

    def _settle(self):
        self.wait_for_render(self.ANIMATION_ITERATIONS)

    def _push_and_pop(self):
        view.setContentView(_StubActivity(), lv.obj())
        self._settle()
        view.finish_current_activity()
        self._settle()

    def test_back_navigation_does_not_leak(self):
        view.setContentView(_StubActivity(), lv.obj())
        self._settle()
        # Warm up: the first round pulls in lazily imported modules.
        self._push_and_pop()

        gc.collect()
        before = gc.mem_alloc()
        rounds = 10
        for _ in range(rounds):
            self._push_and_pop()
        gc.collect()
        leaked = gc.mem_alloc() - before

        print("leaked %d bytes over %d navigations" % (leaked, rounds))
        self.assertTrue(
            leaked < rounds * 32,
            "leaked %d bytes over %d navigations" % (leaked, rounds),
        )

    def test_remove_all_activities_frees_its_screens(self):
        first = lv.obj()
        second = lv.obj()
        view.setContentView(_StubActivity(), first)
        self._settle()
        view.setContentView(_StubActivity(), second)
        self._settle()

        view.remove_and_stop_all_activities()
        # The next activity takes over the display, which releases the screen
        # that was still shown when the stack was emptied.
        view.setContentView(_StubActivity(), lv.obj())
        self._settle()

        self.assertTrue(_is_deleted(first), "screen below the top was not freed")
        self.assertTrue(_is_deleted(second), "screen on display was not freed")


if __name__ == "__main__":
    unittest.main()
