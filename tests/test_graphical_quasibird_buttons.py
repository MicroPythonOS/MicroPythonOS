import unittest

import lvgl as lv

import mpos.ui
from mpos import AppManager, wait_for_text


class TestGraphicalQuasibirdButtons(unittest.TestCase):
    """B/Y reach quasibird as ord letters on every board.

    On the Fri3d 2026 badge that happens via Fri3d2026Expander dual
    delivery: the button generates lv.KEY.NEXT/PREV (which LVGL consumes
    for focus tabbing) AND the driver sends ord("B")/ord("Y") to the
    focused object. These tests drive the app the same way the driver
    does - group.send_data(ord(...)) to the focused screen - then run the
    focus-repair step update_frame() performs on the next frame.
    """

    def tearDown(self):
        try:
            mpos.ui.back_screen()
        except Exception:
            pass

    def _start_quasibird(self):
        self.assertTrue(
            AppManager.start_app("com.quasikili.quasibird"),
            "Failed to start quasibird",
        )
        self.assertTrue(
            wait_for_text("to start!", timeout=10),
            "Quasibird start screen did not load",
        )
        activity, _, _, _ = mpos.ui.screen_stack[-1]
        self.assertEqual(type(activity).__name__, "QuasiBird")
        activity.show_fps = 0
        activity.fps_bg.add_flag(lv.obj.FLAG.HIDDEN)
        activity.game_started = False
        activity.game_over = False
        activity.game_paused = False
        activity._need_refocus = False
        if activity.popup_modal is not None:
            activity.close_popup()
        lv.group_focus_obj(activity.screen)
        return activity

    def _press(self, letter):
        """Deliver an ord-letter KEY to the focused object, like the driver."""
        lv.group_get_default().send_data(ord(letter))

    def _tick(self, activity):
        """Run the frame step that performs focus repair (no timer object)."""
        activity.update_frame(None)

    def test_b_cycles_fps_display(self):
        activity = self._start_quasibird()

        self._press("B")
        self.assertEqual(activity.show_fps, 1)
        self.assertTrue(not activity.fps_bg.has_flag(lv.obj.FLAG.HIDDEN))
        self.assertTrue(activity._need_refocus)

        self._tick(activity)
        self.assertTrue(not activity._need_refocus)
        self.assertEqual(lv.group_get_default().get_focused(), activity.screen)

        self._press("B")
        self.assertEqual(activity.show_fps, 2)
        self._tick(activity)

        self._press("B")
        self.assertEqual(activity.show_fps, 0)
        self.assertTrue(activity.fps_bg.has_flag(lv.obj.FLAG.HIDDEN))

    def test_b_lowercase_also_toggles(self):
        activity = self._start_quasibird()
        self._press("b")
        self.assertEqual(activity.show_fps, 1)

    def test_y_opens_highscore_popup(self):
        activity = self._start_quasibird()

        self._press("Y")
        self.assertTrue(activity.popup_modal is not None)
        self.assertTrue(activity._popup_default_btn is not None)
        popup = activity.popup_modal

        # Focus repair while the popup is open targets the No button, not
        # the screen, so the popup stays keypad-operable.
        self._tick(activity)
        self.assertEqual(
            lv.group_get_default().get_focused(), activity._popup_default_btn
        )

        # A second Y while the popup is open must not stack another popup.
        self._press("Y")
        self.assertTrue(activity.popup_modal is popup)

        activity.on_delete_no(None)
        self.assertTrue(activity.popup_modal is None)
        self.assertTrue(activity._popup_default_btn is None)
        self.assertTrue(not activity.game_paused)

    def test_highscore_tap_ignores_reentry_while_popup_open(self):
        activity = self._start_quasibird()
        activity.on_highscore_tap(None)
        self.assertTrue(activity.popup_modal is not None)
        popup = activity.popup_modal
        activity.on_highscore_tap(None)
        self.assertTrue(activity.popup_modal is popup)
        activity.on_delete_no(None)
        self.assertTrue(activity.popup_modal is None)


if __name__ == "__main__":
    unittest.main()
