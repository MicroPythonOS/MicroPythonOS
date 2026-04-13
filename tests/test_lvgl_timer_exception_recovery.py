"""
Ensure LVGL timer callback exceptions do not stall the scheduler and other timers continue.

Usage:
    Desktop: ./tests/unittest.sh tests/test_lvgl_timer_exception_recovery.py
    Device:  ./tests/unittest.sh tests/test_lvgl_timer_exception_recovery.py --ondevice
"""

import time
import unittest

import lvgl as lv


class TestLvglTimerExceptionRecovery(unittest.TestCase):
    """Verify timer exceptions don't block other timers from running."""

    def setUp(self):
        self.screen = lv.obj()
        self.screen.set_size(320, 240)
        lv.screen_load(self.screen)

    def tearDown(self):
        lv.screen_load(lv.obj())

    def test_timer_exception_does_not_block_other_timer(self):
        good_ticks = {"count": 0}
        bad_ticks = {"count": 0}

        def good_timer_cb(timer):
            good_ticks["count"] += 1

        def bad_timer_cb(timer):
            bad_ticks["count"] += 1
            raise ValueError("timer failure for recovery test")

        good_timer = lv.timer_create(good_timer_cb, 10, None)
        bad_timer = lv.timer_create(bad_timer_cb, 10, None)

        try:
            for _ in range(100):
                lv.task_handler()
                time.sleep(0.01)
        except Exception as exc:
            self.fail(f"lv.task_handler raised unexpectedly: {exc}")
        finally:
            try:
                good_timer.delete()
            except Exception:
                pass
            try:
                bad_timer.delete()
            except Exception:
                pass

        self.assertTrue(
            good_ticks["count"] > 0,
            "Expected good timer to run despite exception in another timer",
        )
