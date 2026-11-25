"""Tests for the Duke3D activity's ownership of the screen, back and buttons.

The engine is a flash-resident core that needs a GRP and a badge, so these
tests pin down the half the activity owns: the OS gesture strips must not take
the walking stick or the action pad, a stray back must not close a game in
progress, and the badge's joystick and buttons must send the action pad's own
engine keys. The engine's own menu (START) is the way out.
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
from mpos.ui.native_input import KeyHolds  # noqa: E402


class _FakeEngine:
    quit = False

    def __init__(self):
        self.keys = []

    def key(self, code, pressed=True):
        self.keys.append((code, pressed))


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


class TestDuke3DButtons(unittest.TestCase):
    """The badge's joystick and buttons must be the action pad's labels."""

    def setUp(self):
        self.activity = duke3d.Duke3D()
        self.engine = _FakeEngine()
        self.activity.engine = self.engine
        self.activity.holds = KeyHolds(self.activity.key)

    def _code_for(self, key):
        self.activity.holds.release_all()
        del self.engine.keys[:]
        self.activity.on_key_event(key)
        return self.engine.keys

    def test_held_state_comes_from_the_keypad(self):
        # Without this the joystick turns for 180 ms and then stalls until the
        # keypad's first repeat at 400 ms.
        self.assertTrue(duke3d.Duke3D.key_state)

    def test_the_joystick_walks_and_turns(self):
        for key, code in ((lv.KEY.LEFT, duke3d.KEY_LEFT),
                          (lv.KEY.RIGHT, duke3d.KEY_RIGHT),
                          (lv.KEY.UP, duke3d.KEY_UP),
                          (lv.KEY.DOWN, duke3d.KEY_DOWN)):
            self.assertEqual(self._code_for(key), [(code, True)],
                             "wrong engine key for %r" % (key,))

    def test_the_buttons_match_the_action_pad_labels(self):
        # A, B, X and Y are the pad's cells, so their physical buttons send the
        # same engine keys as tapping the cell with that label.
        for key, code in ((lv.KEY.ENTER, duke3d.KEY_FIRE),
                          (ord("B"), duke3d.KEY_JUMP),
                          (lv.KEY.ESC, duke3d.KEY_CROUCH),
                          (ord("Y"), duke3d.KEY_USE)):
            self.assertEqual(self._code_for(key), [(code, True)],
                             "wrong engine key for %r" % (key,))

    def test_start_is_the_menu_and_menu_is_next_weapon(self):
        # Both are event-driven, so they tap instead of holding: a held menu
        # key would open and close the engine's menu ten times a second.
        self.activity.on_key_event(lv.KEY.END)
        self.activity.on_key_event(lv.KEY.HOME)
        self.assertEqual(self.engine.keys, [
            (duke3d.KEY_MENU, True), (duke3d.KEY_MENU, False),
            (duke3d.KEY_WEAPON, True), (duke3d.KEY_WEAPON, False),
        ])

    def test_the_menu_button_does_not_open_the_os_drawer(self):
        activity = duke3d.Duke3D()
        activity._touch = duke3d.DukeTouch(activity.key)
        activity.holds = KeyHolds(activity.key)
        activity._started = True
        activity._selftest_down = ()
        activity.error = "no engine in this test"
        saved = (InputManager._drawer_open_disabled,
                 InputManager._drawer_open_cb)
        try:
            activity.onResume(None)
            self.assertTrue(InputManager.is_drawer_open_disabled(),
                            "MENU would open the drawer over the game")
            activity.onPause(None)
            self.assertFalse(InputManager.is_drawer_open_disabled(),
                             "the drawer stayed disabled after the game paused")
        finally:
            (InputManager._drawer_open_disabled,
             InputManager._drawer_open_cb) = saved


if __name__ == "__main__":
    unittest.main()
