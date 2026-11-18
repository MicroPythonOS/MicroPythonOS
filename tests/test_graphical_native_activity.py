"""Tests for mpos.ui.native_activity.NativeActivity.

The base class owns what every native-game activity repeats: the screen and its
event handlers, the surface lifecycle, frame pacing, the labels and the one
"close the app" path. An app is left with its engine and its controls, so these
tests use a fake engine and check the plumbing, not a game.
"""

import time
import unittest

import lvgl as lv

import mpos.ui
import mpos.ui.native_activity as native_activity
from mpos import InputManager
from mpos.ui.native_activity import NativeActivity

WIDTH = 320
HEIGHT = 200


class _FakeDisplay:
    def get_horizontal_resolution(self):
        return 320

    def get_vertical_resolution(self):
        return 240


class _FakeSurface:
    panel_width = 240
    panel_height = 320

    def __init__(self, screen=None, width=None, height=None, buffer=None):
        self.width = width or WIDTH
        self.height = height or HEIGHT
        self.rows_per_band = 45
        self.band_count = 5
        self.buffer = bytearray(self.width * self.height * 2)
        self._image_x = (self.panel_width - self.width) // 2
        self._image_y = (self.panel_height - self.height) // 2
        self._active = False
        self.invalidated = []
        self.flushed = 0
        self.begins = 0
        self.ends = 0

    def begin(self):
        self._active = True
        self.begins += 1

    def end(self):
        self._active = False
        self.ends += 1

    def invalidate_band(self, band):
        self.invalidated.append(band)

    def invalidate_all(self):
        pass

    def flush(self):
        self.flushed += 1

    def present(self, bands, render, flush=True):
        for band in bands:
            render(band)


class _FakeEngine:
    name = "fake"
    quit = False

    def __init__(self, size=(WIDTH, HEIGHT)):
        self.size = size
        self.started = []
        self.ticks = 0
        self.keys = []
        self.resumes = 0
        self.pauses = 0
        self.stops = 0

    def surface_size(self, display):
        return self.size

    def start(self, surface):
        self.started.append(surface)

    def resume(self):
        self.resumes += 1

    def pause(self):
        self.pauses += 1

    def tick(self, now):
        self.ticks += 1

    def key(self, code, pressed):
        self.keys.append((code, pressed))

    def stop(self):
        self.stops += 1


class _Game(NativeActivity):
    target_fps = 50
    hint_text = "arrow keys"

    def __init__(self):
        self.frames = 0
        self.pointer = []
        self.hooks = []

    def start_engine(self, surface):
        self.engine.start(surface)
        return True

    def on_frame(self, now):
        self.frames += 1
        self.engine.tick(now)

    def on_pointer(self, event_code, x, y):
        self.pointer.append((event_code, x, y))

    def on_resumed(self):
        self.hooks.append("resumed")

    def on_paused(self):
        self.hooks.append("paused")


class TestNativeActivity(unittest.TestCase):

    def setUp(self):
        self._real_display = mpos.ui.main_display
        self._real_native_display = native_activity.NativeDisplay
        self._real_pointer_xy = InputManager.pointer_xy
        mpos.ui.main_display = _FakeDisplay()
        native_activity.NativeDisplay = _FakeSurface
        self.game = _Game()
        # onCreate ends in setContentView, which resumes the activity.
        self.game._started = True
        self.game.onCreate()
        self.engine = _FakeEngine()
        self.game.engine = self.engine
        self.game._surface = _FakeSurface()
        self.game._rotated = True
        self.game._started = True
        self.game._paused = False

    def tearDown(self):
        mpos.ui.task_handler.remove_event_cb(self.game._drawframe)
        self.game._clear_hint()
        native_activity.NativeDisplay = self._real_native_display
        mpos.ui.main_display = self._real_display
        InputManager.pointer_xy = self._real_pointer_xy

    def _frame(self):
        self.game._next_frame_ms = 0
        self.game._drawframe()

    # -- lifecycle --------------------------------------------------------

    def test_the_engine_starts_once_and_resumes_after_that(self):
        self.game._started = False
        self.game.onResume(None)
        self.assertEqual(len(self.engine.started), 1)
        self.assertEqual(self.engine.surface_size(self._real_display),
                         (WIDTH, HEIGHT))
        self.assertTrue(self.game._surface._active)
        self.assertEqual(self.game.hooks, ["resumed"])

        self.game.onPause(None)
        self.assertEqual(self.engine.pauses, 1)
        self.assertFalse(self.game._surface._active)
        self.assertEqual(self.game.hooks, ["resumed", "paused"])

        self.game.onResume(None)
        self.assertEqual(len(self.engine.started), 1, "the engine restarted")
        self.assertEqual(self.engine.resumes, 2)

    def test_pausing_releases_every_held_key(self):
        self.game.holds.press(7)
        self.game.onPause(None)
        self.assertEqual(self.engine.keys, [(7, True), (7, False)])

    def test_stopping_hands_the_engine_back(self):
        self.game.onStop(None)
        self.assertEqual(self.engine.stops, 1)
        self.assertIsNone(self.game.engine)
        self.assertFalse(self.game._started)

    # -- frames -----------------------------------------------------------

    def test_a_frame_ticks_the_engine_and_counts(self):
        self._frame()
        self.assertEqual(self.engine.ticks, 1)
        self.assertEqual(self.game._frames, 1)

    def test_a_frame_that_is_too_early_is_skipped(self):
        self._frame()
        self.game._next_frame_ms = time.ticks_add(time.ticks_ms(), 1000)
        self.game._drawframe()
        self.assertEqual(self.engine.ticks, 1)

    def test_the_engine_asking_to_quit_finishes_once(self):
        finished = []
        self.game.finish = lambda: finished.append(True)
        self.engine.quit = True
        self._frame()
        self._frame()

        self.assertEqual(finished, [True])
        self.assertTrue(self.game._paused)

    def test_a_failing_frame_is_reported_once_and_stops_the_loop(self):
        class _Broken(_FakeEngine):
            def tick(self, now):
                raise ValueError("engine gone")

        self.game.engine = _Broken()
        self._frame()
        self.assertIsNotNone(self.game.error)
        self.assertEqual(self.game._frames, 0)
        # The next frame does nothing at all.
        self._frame()

    # -- start-up ---------------------------------------------------------

    def test_a_host_without_an_engine_shows_the_reason(self):
        def unavailable():
            raise RuntimeError("no engine for this host")

        self.game.make_engine = unavailable
        self.game._started = False
        self.game.onResume(None)

        self.assertIsNotNone(self.game.error)
        self.assertIn("no engine", self.game.hint.get_text())
        self.assertEqual(self.game._hint_until, 0, "a message must not expire")
        self._frame()

    def test_an_app_with_nothing_to_run_shows_no_hint(self):
        self.game.start_engine = lambda surface: False
        self.game._started = False
        self.game.onResume(None)

        self.assertIsNone(self.game.hint)
        self.assertTrue(self.game._surface._active,
                        "the surface is still valid for the app's own message")

    def test_the_engine_decides_the_surface_shape(self):
        self.game.engine = _FakeEngine(size=(200, 320))
        self.game._started = False
        self.game.onResume(None)

        self.assertEqual(self.game._surface.width, 200)
        self.assertEqual(self.game._surface.height, 320)
        self.assertTrue(self.game._rotated)

    def test_a_plain_activity_uses_the_whole_display(self):
        self.game.engine = None
        self.game.start_engine = lambda surface: True
        self.game._started = False
        self.game.onResume(None)

        self.assertEqual(self.game._surface.width, 320)
        self.assertEqual(self.game._surface.height, 240)
        self.assertFalse(self.game._rotated)

    # -- input ------------------------------------------------------------

    def test_keys_are_forwarded_and_counted(self):
        self.game.key(0xAC, True)
        self.game.key(0xAC, False)
        self.assertEqual(self.engine.keys, [(0xAC, True), (0xAC, False)])
        self.assertEqual(self.game.get_stats()["keys"], 2)

    def test_pointer_events_carry_panel_coordinates(self):
        self.game.pointer = []
        InputManager.pointer_xy = staticmethod(lambda: (120, 40))
        self.game._on_touch(_Event(code=lv.EVENT.PRESSED))
        self.assertEqual(self.game.pointer, [(lv.EVENT.PRESSED, 120, 40)])

    def test_to_game_undoes_a_rotated_surface(self):
        # 200x320 surface: game x runs down the panel, game y right to left.
        self.game._surface = _FakeSurface(width=200, height=320)
        self.game._rotated = True
        x, y = self.game._surface._image_x + 10, self.game._surface._image_y + 50
        self.assertEqual(self.game.to_game(x, y), (50, 199 - 10))

    def test_to_game_is_the_offset_when_not_rotated(self):
        self.game._surface = _FakeSurface(width=320, height=200)
        self.game._rotated = False
        surface = self.game._surface
        self.assertEqual(
            self.game.to_game(100, 60),
            (100 - surface._image_x, 60 - surface._image_y))

    # -- labels -----------------------------------------------------------

    def test_the_hint_expires_and_a_message_does_not(self):
        self.game.show_hint("help", 50)
        self.assertIsNotNone(self.game.hint)
        later = time.ticks_add(time.ticks_ms(), 200)
        self.game._expire_hint(later)
        self.assertIsNone(self.game.hint)

        self.game.show_message("broken")
        self.game._expire_hint(time.ticks_add(later, 60000))
        self.assertIsNotNone(self.game.hint)

    # -- stats ------------------------------------------------------------

    def test_stats_describe_the_surface(self):
        stats = self.game.get_stats()
        self.assertEqual(stats["bands"], self.game._surface.band_count)
        self.assertEqual(stats["rows_per_band"], self.game._surface.rows_per_band)
        self.assertIsNone(stats["error"])


class _Event:
    def __init__(self, code=None):
        self._code = code

    def get_code(self):
        return self._code


if __name__ == "__main__":
    unittest.main()
