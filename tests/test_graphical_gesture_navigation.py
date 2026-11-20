"""Tests for the OS edge swipes and the per-activity opt-out.

The two strips live in ``lv.layer_top()`` so they win the hit test over the
activity's screen. Suppressing them is therefore not a matter of ignoring the
event: they have to leave the hit test, or the touches never reach the game.
"""

import unittest

import lvgl as lv

import mpos.ui.gesture_navigation as gestures
import mpos.ui.view as view


class TestSystemGestures(unittest.TestCase):

    def setUp(self):
        self.saved = (gestures.back_rect, gestures.backbutton,
                      gestures.top_rect, gestures.downbutton,
                      gestures.system_gestures_enabled)
        gestures.handle_back_swipe()
        gestures.handle_top_swipe()
        gestures.set_system_gestures_enabled(True)

    def tearDown(self):
        gestures._delete_gesture_objects(gestures.back_rect, gestures.backbutton)
        gestures._delete_gesture_objects(gestures.top_rect, gestures.downbutton)
        (gestures.back_rect, gestures.backbutton,
         gestures.top_rect, gestures.downbutton,
         gestures.system_gestures_enabled) = self.saved

    def _hit(self, x, y):
        top = lv.layer_top()
        top.update_layout()
        return lv.indev_search_obj(top, lv.point_t({"x": x, "y": y}))

    def test_disabling_removes_both_strips_from_the_hit_test(self):
        self.assertIs(self._hit(5, 100), gestures.back_rect)
        self.assertIs(self._hit(5, 10), gestures.top_rect)

        gestures.set_system_gestures_enabled(False)

        self.assertFalse(gestures.back_rect.has_flag(lv.obj.FLAG.CLICKABLE))
        self.assertFalse(gestures.top_rect.has_flag(lv.obj.FLAG.CLICKABLE))
        self.assertTrue(gestures.back_rect.has_flag(lv.obj.FLAG.HIDDEN))
        self.assertTrue(gestures.top_rect.has_flag(lv.obj.FLAG.HIDDEN))
        self.assertIsNone(self._hit(5, 100))
        self.assertIsNone(self._hit(5, 10))

    def test_enabling_puts_them_back(self):
        gestures.set_system_gestures_enabled(False)
        gestures.set_system_gestures_enabled(True)

        self.assertTrue(gestures.back_rect.has_flag(lv.obj.FLAG.CLICKABLE))
        self.assertFalse(gestures.back_rect.has_flag(lv.obj.FLAG.HIDDEN))
        self.assertIs(self._hit(5, 100), gestures.back_rect)
        self.assertIs(self._hit(5, 10), gestures.top_rect)

    def test_strips_created_while_disabled_stay_out_of_the_hit_test(self):
        # The display switch path recreates them, so creation has to honor the
        # current state instead of assuming gestures are on.
        gestures.set_system_gestures_enabled(False)
        gestures.handle_back_swipe()
        gestures.handle_top_swipe()

        self.assertFalse(gestures.back_rect.has_flag(lv.obj.FLAG.CLICKABLE))
        self.assertTrue(gestures.top_rect.has_flag(lv.obj.FLAG.HIDDEN))
        self.assertIsNone(self._hit(5, 100))

    def test_the_foreground_activity_decides(self):
        class _Immersive:
            system_gestures_enabled = False

        class _Normal:
            pass

        saved_stack = view.screen_stack
        try:
            for activity, enabled in (
                    (_Immersive(), False),
                    (_Normal(), True),
                    (None, True)):
                view.screen_stack = [] if activity is None else [
                    (activity, None, None, None)]
                view._apply_system_gestures()
                self.assertEqual(
                    gestures.system_gestures_enabled, enabled,
                    "wrong state for %r" % (activity,))
        finally:
            view.screen_stack = saved_stack
