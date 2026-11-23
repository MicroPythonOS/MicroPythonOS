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
from mpos.ui.native_input import TouchMonitor

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


class _FakePanel:
    """A pointer device with get_touches(): the GT911/FT6x36 shape."""

    def __init__(self, touches=(), rotation=0, width=240, height=320):
        self.touches = list(touches)
        self.rotation = rotation
        self.width = width
        self.height = height

    def get_touches(self):
        return self.touches

    def get_rotation(self):
        return self.rotation

    def get_width(self):
        return self.width

    def get_height(self):
        return self.height


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

    def audio_mix(self, buffer):
        # A recognisable non-silent sample, like an engine's mixer.
        for index in range(len(buffer)):
            buffer[index] = 3
        return len(buffer) // 2

    def stop(self):
        self.stops += 1


class _Game(NativeActivity):
    target_fps = 50
    hint_text = "arrow keys"
    audio_rate = None

    def make_engine(self):
        return self.engine

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


class _MultiGame(_Game):
    """A game that asks for every finger of a multi-point panel."""

    touch_fingers = True

    def __init__(self):
        super().__init__()
        self.fingers = []

    def on_touch_finger(self, finger, event_code, x, y):
        self.fingers.append((finger, event_code, x, y))


class _RepeatDriver:
    """A keypad that can synthesize repeats; only some track held state."""

    def __init__(self, reports_state):
        self.repeats = True
        if reports_state:
            self.held_keys = lambda: ()

    def set_repeat_enabled(self, enabled):
        self.repeats = enabled


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
        # The harness stands in for a session whose engine already started.
        self.game._ready = True

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

    def test_key_state_switches_repeats_off_only_where_state_is_available(self):
        # A repeat is the only refresh a driver without held state provides, so
        # switching it off there would end every hold after HOLD_MS.
        capable = _RepeatDriver(reports_state=True)
        repeats_only = _RepeatDriver(reports_state=False)
        saved = list(InputManager._registered_indevs)
        try:
            InputManager._registered_indevs[:] = [capable, repeats_only]
            self.game.key_state = True
            self.game._keypad_state(True)
            self.assertFalse(capable.repeats)
            self.assertTrue(repeats_only.repeats)

            self.game._keypad_state(False)
            self.assertTrue(capable.repeats, "repeats were not restored")
        finally:
            InputManager._registered_indevs[:] = saved
            NativeActivity._keypad_state_users = 0
            self.game._keypad_state_active = False

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

    def test_an_engine_that_did_not_start_is_never_ticked(self):
        # The app has shown why it cannot run (a missing WAD, not enough RAM);
        # ticking the engine anyway raises on every frame.
        self.game.start_engine = lambda surface: False
        self.game._started = False
        self.game.onResume(None)
        self._frame()
        self.assertEqual(self.engine.ticks, 0)
        self.assertEqual(self.game._frames, 0)

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

    def test_a_refresh_event_is_not_a_touch(self):
        # The screen listens for EVENT.ALL, so LVGL also delivers draw and
        # refresh events there; none of them is input.
        self.game.pointer = []
        InputManager.pointer_xy = staticmethod(lambda: (120, 40))
        self.game._on_touch(_Event(code=lv.EVENT.DRAW_MAIN))
        self.game._on_touch(_Event(code=lv.EVENT.REFR_EXT_DRAW_SIZE))
        self.assertEqual(self.game.pointer, [])

    # -- multi-point panels ------------------------------------------------

    def _multi_game(self, touches):
        game = _MultiGame()
        game._started = True
        game.onCreate()
        game.engine = self.engine
        game._surface = _FakeSurface()
        game._paused = False
        game._ready = True
        panel = _FakePanel(list(touches))
        game.touch = TouchMonitor(panel)
        self.addCleanup(mpos.ui.task_handler.remove_event_cb, game._drawframe)
        self.addCleanup(game._clear_hint)
        return game, panel

    def _step(self, game):
        game._next_frame_ms = 0
        game._drawframe()

    def test_a_multi_point_panel_delivers_every_finger_to_the_app(self):
        game, panel = self._multi_game([(None, 30, 100), (None, 220, 180)])
        self._step(game)
        self.assertEqual(
            [(phase, x, y) for _, phase, x, y in game.fingers],
            [(lv.EVENT.PRESSED, 30, 100), (lv.EVENT.PRESSED, 220, 180)])
        self.assertNotEqual(game.fingers[0][0], game.fingers[1][0])

        panel.touches = [(None, 30, 100), (None, 220, 180)]
        self._step(game)
        self.assertEqual(len(game.fingers), 2, "a still finger sent an event")

    def test_a_multi_point_panel_does_not_also_send_lvgl_pointer_events(self):
        game, _ = self._multi_game([(None, 30, 100)])
        game.pointer = []
        InputManager.pointer_xy = staticmethod(lambda: (30, 100))
        game._on_touch(_Event(code=lv.EVENT.PRESSED))
        self.assertEqual(game.pointer, [], "the finger was handled twice")

    def test_a_single_point_panel_keeps_using_lvgl_events(self):
        self.game.touch = None
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

    def test_game_to_panel_is_the_inverse_of_to_game(self):
        for width, height, rotated in ((320, 200, False), (200, 320, True)):
            self.game._surface = _FakeSurface(width=width, height=height)
            self.game._rotated = rotated
            for point in ((0, 0), (37, 11), (width - 1, height - 1)):
                panel = self.game.game_to_panel(*point)
                self.assertEqual(self.game.to_game(*panel), point)

    def test_game_rect_to_panel_swaps_the_sides_when_rotated(self):
        self.game._surface = _FakeSurface(width=200, height=320)
        self.game._rotated = True
        x, y, width, height = self.game.game_rect_to_panel(10, 20, 30, 40)
        self.assertEqual((x, y), self.game.game_to_panel(10, 20 + 40 - 1))
        self.assertEqual(
            (x + width - 1, y + height - 1),
            self.game.game_to_panel(10 + 30 - 1, 20))

    def test_game_rect_to_panel_keeps_the_rect_when_not_rotated(self):
        self.game._surface = _FakeSurface(width=320, height=200)
        self.game._rotated = False
        x, y = self.game.game_to_panel(10, 20)
        self.assertEqual(
            self.game.game_rect_to_panel(10, 20, 30, 40),
            (x, y, 30, 40))

    def test_a_scaled_surface_maps_a_touch_into_the_engine_frame(self):
        # 240x150 shows the engine's 320x200 at three quarters, so a finger is
        # scaled up by 4/3 and the frame's edges land on the surface's edges.
        self.game._surface = _FakeSurface(width=240, height=150)
        self.game._rotated = False
        self.game._game_width, self.game._game_height = 320, 200
        surface = self.game._surface
        self.assertEqual(
            self.game.to_game(surface._image_x + 120, surface._image_y + 75),
            (160, 100))
        self.assertEqual(
            self.game.to_game(surface._image_x, surface._image_y), (0, 0))
        self.assertEqual(
            self.game.to_game(surface._image_x + 239, surface._image_y + 149),
            (319, 199))

    def test_a_scaled_surface_round_trips_panel_points(self):
        self.game._surface = _FakeSurface(width=240, height=150)
        self.game._rotated = False
        self.game._game_width, self.game._game_height = 320, 200
        surface = self.game._surface
        for x in (0, 1, 2, 3, 119, 120, 238, 239):
            for y in (0, 1, 74, 75, 148, 149):
                point = (surface._image_x + x, surface._image_y + y)
                self.assertEqual(
                    self.game.game_to_panel(*self.game.to_game(*point)), point)

    def test_a_scaled_surface_shrinks_a_game_rect(self):
        self.game._surface = _FakeSurface(width=240, height=150)
        self.game._rotated = False
        self.game._game_width, self.game._game_height = 320, 200
        surface = self.game._surface
        x, y, width, height = self.game.game_rect_to_panel(0, 0, 160, 200)
        self.assertEqual((x, y), (surface._image_x, surface._image_y))
        self.assertEqual((width, height), (120, 150))

    def test_an_engine_that_scales_reports_the_frame_it_draws(self):
        engine = _FakeEngine(size=(240, 150))
        engine.frame_size = (WIDTH, HEIGHT)
        self.game.engine = engine
        self.game._surface = None
        self.game._game_width = None
        self.game._game_height = None
        self.game._begin_session()
        self.assertIsNone(self.game.error)
        self.assertEqual(
            (self.game._game_width, self.game._game_height), (WIDTH, HEIGHT))
        self.assertFalse(self.game._rotated)
        self.assertEqual((self.game._surface.width, self.game._surface.height),
                         (240, 150))

    # -- audio ------------------------------------------------------------

    def _patch_pcm(self, chosen=None, outputs=()):
        """Stand in for AudioManager's PCM sink API."""
        class _Output:
            def __init__(self, name, kind):
                self.name = name
                self.kind = kind

        class _Sink:
            def __init__(self):
                self.writes = []
                self.closes = 0
                self.active = True
                self.output = None

            def write(self, buffer):
                self.writes.append(bytes(buffer))
                return len(buffer)

            def close(self):
                self.closes += 1
                self.active = False

        sink = _Sink()

        class _Audio:
            @staticmethod
            def get_default_output():
                return chosen

            @staticmethod
            def find_output_by_kind(kind):
                for output in outputs:
                    if output.kind == kind:
                        return output
                return None

            @staticmethod
            def open_pcm(rate, channels=1, output=None):
                sink.rate = rate
                sink.output = output
                sink.active = True
                return sink

        self._real_audio = mpos.AudioManager
        mpos.AudioManager = _Audio
        return sink

    def _restore_audio(self):
        mpos.AudioManager = self._real_audio

    def test_the_engine_feeds_the_sink_every_frame(self):
        dac = type("O", (), {"name": "Headset Output", "kind": "i2s"})()
        sink = self._patch_pcm(chosen=dac, outputs=(dac,))
        try:
            self.game.audio_rate = 11025
            self.game._open_audio()
            self.assertIs(self.game._sink, sink)
            self.assertIs(sink.output, dac)
            self.assertEqual(sink.rate, 11025)

            self.game._audio_ms = time.ticks_ms() - 60
            self.game._pump_audio(time.ticks_ms())
            self.assertTrue(any(any(chunk) for chunk in sink.writes),
                            "the sink got silence")
        finally:
            self.game._close_audio()
            self._restore_audio()

    def test_a_paused_activity_closes_the_sink_and_resume_reopens_it(self):
        dac = type("O", (), {"name": "Headset Output", "kind": "i2s"})()
        sink = self._patch_pcm(chosen=dac, outputs=(dac,))
        try:
            self.game.audio_rate = 11025
            self.game._open_audio()
            self.game.onPause(None)
            self.assertIsNone(self.game._sink)
            self.assertTrue(sink.closes > 0)

            self.game.onResume(None)
            self.assertIs(self.game._sink, sink)
        finally:
            self.game._close_audio()
            self._restore_audio()

    def test_an_app_that_wants_a_speaker_does_not_get_the_piezo(self):
        class _Output:
            def __init__(self, name, kind):
                self.name = name
                self.kind = kind

        buzzer = _Output("Badge Buzzer", "buzzer")
        dac = _Output("Headset Output", "i2s")
        sink = self._patch_pcm(chosen=buzzer, outputs=(buzzer, dac))
        try:
            self.game.audio_rate = 11025
            self.game.audio_output_kind = "i2s"
            self.game._open_audio()
            self.assertIs(sink.output, dac)
        finally:
            self.game._close_audio()
            self._restore_audio()

    def test_a_piezo_only_host_stays_silent(self):
        class _Output:
            name = "Badge Buzzer"
            kind = "buzzer"

        buzzer = _Output()
        self._patch_pcm(chosen=buzzer, outputs=(buzzer,))
        try:
            self.game.audio_rate = 11025
            self.game.audio_output_kind = "i2s"
            self.game._open_audio()
            self.assertIsNone(self.game._sink)
            self.game._pump_audio(time.ticks_ms())
        finally:
            self.game._close_audio()
            self._restore_audio()

    def test_an_app_without_a_mixer_opens_no_sink(self):
        dac = type("O", (), {"name": "Headset Output", "kind": "i2s"})()
        self._patch_pcm(chosen=dac, outputs=(dac,))
        try:
            self.game.audio_rate = None
            self.game._open_audio()
            self.assertIsNone(self.game._sink)
        finally:
            self._restore_audio()

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
