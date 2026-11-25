"""Tests for the Duke3D activity's ownership of the screen edges and of back.

The engine is a flash-resident core that needs a GRP and a badge, so these
tests pin down the half the activity owns: the OS gesture strips must not take
the walking stick or the action pad, and a stray back must not close a game in
progress. The engine's own menu (START) is the way out.
"""

import sys
import unittest

import lvgl as lv

import mpos.ui.view as view
from mpos import InputManager

APP_DIR = "apps/com.micropythonos.duke3d"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import duke3d  # noqa: E402

from mpos.ui import topmenu  # noqa: E402


class TestDuke3DScreen(unittest.TestCase):

    def test_the_game_is_immersive(self):
        # The left strip is the walking stick and the top strip is where the
        # action pad's outer edge is; either one steals a touch if it stays in
        # the hit test. This is the same opt-out Doom uses.
        self.assertFalse(duke3d.Duke3D.system_gestures_enabled)

    def test_back_is_consumed_by_the_activity(self):
        activity = duke3d.Duke3D()
        self.assertTrue(activity.onBackPressed(None))

    def test_the_os_back_does_not_close_the_game(self):
        activity = duke3d.Duke3D()
        saved_stack = view.screen_stack
        saved_disabled = (InputManager._back_screen_disabled,
                          InputManager._back_screen_cb)
        saved_drawer = topmenu.drawer_open
        try:
            InputManager.set_back_screen_disabled(False)
            topmenu.drawer_open = False
            view.screen_stack = [("launcher", None, None, None),
                                 (activity, None, None, None)]
            # back_screen() is what the expander's back key (and the gesture)
            # call; the activity has to keep the stack as it is.
            self.assertTrue(view.back_screen())
            self.assertEqual(len(view.screen_stack), 2,
                             "back popped the game off the stack")
        finally:
            view.screen_stack = saved_stack
            (InputManager._back_screen_disabled,
             InputManager._back_screen_cb) = saved_disabled
            topmenu.drawer_open = saved_drawer


if __name__ == "__main__":
    unittest.main()
