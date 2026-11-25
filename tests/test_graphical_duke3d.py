"""Tests for the Duke3D activity's ownership of the screen, back and buttons.

The engine is a flash-resident core that needs a GRP and a badge, so these
tests pin down the half the activity owns: the OS gesture strips must not take
the walking stick or the action pad, a stray back must not close a game in
progress, and the badge's joystick and buttons must send the action pad's own
engine keys. The engine's own menu (START) is the way out.
"""

import os
import sys
import time
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
        # Both are sampled by the engine once a tic, so the press has to stay
        # down for at least one tic; the release comes from the frame loop.
        self.activity.on_key_event(lv.KEY.END)
        self.assertEqual(self.engine.keys, [(duke3d.KEY_MENU, True)])
        self.activity.holds.tick(
            time.ticks_add(time.ticks_ms(), duke3d.MENU_TAP_MS + 1))
        self.assertEqual(self.engine.keys, [
            (duke3d.KEY_MENU, True), (duke3d.KEY_MENU, False)])
        del self.engine.keys[:]

        self.activity.on_key_event(lv.KEY.HOME)
        self.assertEqual(self.engine.keys, [(duke3d.KEY_WEAPON, True)])
        self.activity.holds.tick(
            time.ticks_add(time.ticks_ms(), duke3d.MENU_TAP_MS + 1))
        self.assertEqual(self.engine.keys, [
            (duke3d.KEY_WEAPON, True), (duke3d.KEY_WEAPON, False)])

    def test_the_touch_pad_taps_a_menu_key_through_the_held_tap(self):
        # The pad's START/MENU cells have the same problem as the physical
        # buttons: press and release in one frame is invisible to the engine.
        tapped = []
        sent = []
        touch = duke3d.DukeTouch(
            lambda code, pressed: sent.append((code, pressed)),
            tap=lambda code: tapped.append(code))
        touch.pressed(0, 200, 180)  # the START cell: bottom row, left
        self.assertEqual(tapped, [duke3d.KEY_MENU])
        self.assertEqual(sent, [])

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


class _FakeCore:
    """Stands in for mpos_core's file_poll/file_reply handshake."""

    def __init__(self, requests):
        self.requests = list(requests)
        self.replies = []

    def file_poll(self):
        return self.requests.pop(0) if self.requests else None

    def file_reply(self, count):
        self.replies.append(count)


class _FakeDisplay:
    def __init__(self, width, height):
        self._width = width
        self._height = height

    def get_horizontal_resolution(self):
        return self._width

    def get_vertical_resolution(self):
        return self._height


class _SurfaceEngine(duke3d._CoreEngine):
    """The engine's surface rule without booting a core."""

    def __init__(self):
        pass


class TestDuke3DSurfaceSize(unittest.TestCase):
    """Which surface the core is given, and what a small panel gets."""

    def _size(self, width, height):
        return _SurfaceEngine().surface_size(_FakeDisplay(width, height))

    def test_a_panel_that_holds_the_frame_gets_it_unscaled(self):
        self.assertEqual(self._size(320, 240), (320, 200))
        self.assertEqual(self._size(240, 320), (200, 320))

    def test_a_narrower_panel_gets_the_middle_of_the_frame(self):
        # The fri3d 2024 is 296x240: the 320x200 frame does not fit either way
        # round, so the core keeps the full height and drops the outer 12
        # columns at each edge. Cropping keeps every remaining pixel sharp.
        engine = _SurfaceEngine()
        self.assertEqual(engine.surface_size(_FakeDisplay(296, 240)),
                         (296, 200))
        self.assertEqual(engine.frame_window, (12, 0, 296, 200))
        # The touch map still starts from the engine's own frame.
        self.assertEqual(duke3d._CoreEngine.frame_size,
                         (duke3d.GAME_WIDTH, duke3d.GAME_HEIGHT))

    def test_a_square_panel_keeps_the_height_and_crops_the_sides(self):
        engine = _SurfaceEngine()
        self.assertEqual(engine.surface_size(_FakeDisplay(240, 240)),
                         (240, 200))
        self.assertEqual(engine.frame_window, (40, 0, 240, 200))
        engine = _SurfaceEngine()
        self.assertEqual(engine.surface_size(_FakeDisplay(480, 180)),
                         (320, 180))
        self.assertEqual(engine.frame_window, (0, 10, 320, 180))

    def test_a_panel_too_small_to_show_the_game_says_so(self):
        with self.assertRaises(RuntimeError):
            self._size(128, 96)


class TestDuke3DHostFiles(unittest.TestCase):
    """The engine's saves and config live on the host's filesystem.

    The core runs on its own task and never enters MicroPython, so it hands a
    file operation over (ABI 10) and the frame loop answers it.
    """

    DIR = "duke_files_test"
    PREFS = DIR + "/com.micropythonos.duke3d"

    def setUp(self):
        try:
            os.mkdir(self.DIR)
        except OSError:
            pass
        try:
            os.mkdir(self.PREFS)
        except OSError:
            pass
        try:
            os.mkdir(self.PREFS + "/duke3d")
        except OSError:
            pass
        self.engine = _SurfaceEngine()
        self.engine._config_dir = self.PREFS

    def tearDown(self):
        for name in ("duke3d.cfg", "duke3d/game0.sav"):
            try:
                os.remove(self.PREFS + "/" + name)
            except OSError:
                pass
        try:
            os.rmdir(self.PREFS + "/duke3d")
        except OSError:
            pass
        try:
            os.rmdir(self.PREFS)
            os.rmdir(self.DIR)
        except OSError:
            pass

    def _serve(self, *requests):
        self.engine._core = _FakeCore(requests)
        self.engine.serve_files()
        return self.engine._core.replies[-1]

    def test_the_engines_paths_land_in_the_apps_prefs(self):
        self.assertEqual(self.engine._host_path("/config/duke3d.cfg"),
                         self.PREFS + "/duke3d.cfg")
        self.assertEqual(self.engine._host_path("/saves/duke3d/game0.sav"),
                         self.PREFS + "/duke3d/game0.sav")

    def test_a_save_is_written_and_read_back(self):
        # The engine writes the version word first, then the blocks. The buffer
        # is the core's own, so a read lands in it (readinto), no copy.
        self.assertEqual(self._serve((1, "/saves/duke3d/game0.sav", 0, 4, b"v119")), 4)
        self.assertEqual(self._serve((1, "/saves/duke3d/game0.sav", 4, 3, b"abc")), 3)
        buffer = bytearray(16)
        self.assertEqual(self._serve((0, "/saves/duke3d/game0.sav", 0, 16, buffer)), 7)
        self.assertEqual(bytes(buffer[:7]), b"v119abc")
        self.assertEqual(self._serve((2, "/saves/duke3d/game0.sav", 0, 0, None)), 7)

    def test_the_setup_file_is_written_too(self):
        self.assertEqual(self._serve((1, "/config/duke3d.cfg", 0, 5, b"hello")), 5)
        buffer = bytearray(3)
        self.assertEqual(self._serve((0, "/config/duke3d.cfg", 1, 3, buffer)), 3)
        self.assertEqual(bytes(buffer), b"ell")

    def test_a_missing_file_is_reported_as_an_error(self):
        buffer = bytearray(4)
        self.assertEqual(self._serve((0, "/saves/duke3d/game1.sav", 0, 4, buffer)), -1)

    def test_no_request_is_a_no_op(self):
        self.engine._core = _FakeCore([])
        self.engine.serve_files()
        self.assertEqual(self.engine._core.replies, [])


if __name__ == "__main__":
    unittest.main()
