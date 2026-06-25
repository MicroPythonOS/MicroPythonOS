"""Regression test for LVGL timer linked-list corruption.

The original Nostr crash was a SIGSEGV inside lv_timer_delete -> lv_ll_remove
with a dangling next-node pointer.  It was caused by creating a periodic timer
and then calling set_repeat_count(0): in LVGL repeat_count == 0 means
"fire once and auto-delete".  When the timer later fired and deleted itself,
Python/Self-Flush code still held the wrapper and called .delete() again,
double-freeing the timer and corrupting the timer_ll list.

This test exercises the safe patterns that Nostr now uses: periodic timers
created with the default infinite repeat count (or explicit -1) and then
deleted exactly once.

No need to run this every time, just dont do timer.set_repeat_counter(0) and done.
"""

import lvgl as lv
import unittest

from mpos.ui.testing import GraphicalTestCase


class TestTimerCreateDelete(GraphicalTestCase):
    def test_create_delete_periodic_timer_default_repeat_count(self):
        """Default repeat_count (-1) keeps the timer alive until .delete()."""
        for i in range(500):
            t = lv.timer_create(lambda timer: None, 10, None)
            self.wait_for_render(2)
            t.delete()

    def test_create_delete_periodic_timer_explicit_infinite(self):
        """Explicit repeat_count(-1) is also safe."""
        for i in range(500):
            t = lv.timer_create(lambda timer: None, 10, None)
            t.set_repeat_count(-1)
            self.wait_for_render(2)
            t.delete()


if __name__ == "__main__":
    unittest.main()
