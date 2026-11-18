"""Tests for the core-driven Doom activity.

The engine is a flash-resident blob that only exists on the device, so these
tests pin down the seam the activity is responsible for: the band copy into the
display surface, the flushing handshake that lets the panel transfer overlap the
next band's conversion, and the key/touch mapping (including the held-key
releases a keypad needs, because it only reports presses).
"""

import sys
import time
import unittest

import lvgl as lv

import mpos.ui
from mpos import InputManager

APP_DIR = "apps/com.micropythonos.doomcore"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# The portrait layout the app asks for on a 240x320 panel.
SURFACE_WIDTH = 200
SURFACE_HEIGHT = 320
DRAW_BUFFER_BYTES = 28800


class _FakeCore:
    """Records what the activity asks of mpos_core."""

    def __init__(self):
        self.started = None
        self.ticks = 0
        self.stops = 0

    def start(self, *args):
        self.started = args

    def tick(self, now):
        self.ticks += 1

    def stop(self):
        self.stops += 1

    def mapped(self):
        return 0x43000000

    def mapped_size(self):
        return 0x20000

    def abi_version(self):
        return 6

    def audio_mix(self, buffer):
        for index in range(len(buffer)):
            buffer[index] = 1


fake_core = _FakeCore()
_real_core = sys.modules.get("mpos_core")
sys.modules["mpos_core"] = fake_core
sys.modules.pop("doom_core", None)
import doom_core  # noqa: E402

# doom_core keeps the fake it was imported with; other tests keep the real one.
if _real_core is not None:
    sys.modules["mpos_core"] = _real_core


class _FakeDisplay:
    """Just the two calls the activity makes when it picks a surface."""

    def __init__(self, width, height):
        self._w = width
        self._h = height

    def get_horizontal_resolution(self):
        return self._w

    def get_vertical_resolution(self):
        return self._h


class _FakeSurface:
    """A display surface that records invalidations instead of drawing."""

    panel_width = 240
    panel_height = 320

    def __init__(self, screen=None, width=None, height=None, buffer=None):
        self.width = width or SURFACE_WIDTH
        self.height = height or SURFACE_HEIGHT
        # Same rule as NativeDisplay: a band is one draw buffer of rows.
        self.rows_per_band = DRAW_BUFFER_BYTES // (self.width * 2)
        self.band_count = ((self.height + self.rows_per_band - 1)
                           // self.rows_per_band)
        self.stride = self.width * 2
        self.buffer = bytearray(self.width * self.height * 2)
        self._image_x = (self.panel_width - self.width) // 2
        self._image_y = (self.panel_height - self.height) // 2
        self._active = True
        self.invalidated = []
        self.flushed = 0
        self.bands = 0
        self.frames = 0


    def begin(self):
        self._active = True

    def end(self):
        self._active = False

    def invalidate_band(self, band):
        self.invalidated.append(band)

    def flush(self):
        self.flushed += 1


class _Event:
    def __init__(self, code=None, key=None):
        self._code = code
        self._key = key

    def get_code(self):
        return self._code

    def get_key(self):
        return self._key


class TestDoomCoreActivity(unittest.TestCase):

    def setUp(self):
        fake_core.started = None
        fake_core.ticks = 0
        fake_core.stops = 0
        self._real_native_display = doom_core.NativeDisplay
        self._real_find_wad = doom_core.find_wad
        self._real_pointer_xy = InputManager.pointer_xy
        self._real_display = mpos.ui.main_display
        mpos.ui.main_display = _FakeDisplay(240, 320)
        doom_core.NativeDisplay = _FakeSurface
        self.activity = doom_core.DoomCore()
        self.activity.onCreate()
        self.activity._surface = _FakeSurface()
        self.activity._started = True
        self.activity._paused = False
        self.activity._wad = "doom1.wad"

    def tearDown(self):
        mpos.ui.task_handler.remove_event_cb(self.activity._drawframe)
        if self.activity.hint is not None:
            self.activity.hint.delete()
            self.activity.hint = None
        doom_core.NativeDisplay = self._real_native_display
        doom_core.find_wad = self._real_find_wad
        InputManager.pointer_xy = self._real_pointer_xy
        mpos.ui.main_display = self._real_display

    # -- start-up ---------------------------------------------------------

    def test_start_passes_the_surface_and_the_band_height(self):
        self.activity._started = False
        doom_core.find_wad = lambda intent=None: "doom1.wad"
        self.activity.onResume(None)

        self.assertIsNotNone(fake_core.started, "the core was not started")
        args = fake_core.started
        self.assertEqual(args[0], doom_core.CORE_PARTITION)
        self.assertEqual(args[10], SURFACE_WIDTH)
        self.assertEqual(args[11], SURFACE_HEIGHT)
        self.assertTrue(self.activity._rotated)
        # The core draws straight into the surface buffer, one display band at a
        # time: that is what overlaps the transfer with the next conversion.
        self.assertIs(args[12], self.activity._surface.buffer)
        self.assertEqual(args[13], self.activity._surface.rows_per_band)

    def test_a_landscape_panel_gets_dooms_frame_unrotated(self):
        # The fri3d 2026 ends up 320x240 after its rotation, so the core must
        # not transpose: a 320x200 surface is the request.
        class _LandscapeSurface(_FakeSurface):
            panel_width = 320
            panel_height = 240

        doom_core.NativeDisplay = _LandscapeSurface
        mpos.ui.main_display = _FakeDisplay(320, 240)
        self.activity._started = False
        doom_core.find_wad = lambda intent=None: "doom1.wad"
        self.activity.onResume(None)

        args = fake_core.started
        self.assertFalse(self.activity._rotated)
        self.assertEqual(args[10], 320)
        self.assertEqual(args[11], 200)
        self.assertEqual(args[12], self.activity._surface.buffer)

        # Identity mapping: Doom's x is the panel's x, its y the panel's y
        # (offset by the letterbox).
        self.assertEqual(self.activity._to_game(150, 70), (150, 50))

        # The left half is still the joystick, and the bands are Doom's rows.
        self._touch(lv.EVENT.PRESSED, 40, 70)
        self.assertEqual(self.activity._zone, "stick")
        self._touch(lv.EVENT.RELEASED, 40, 70)
        self._touch(lv.EVENT.PRESSED, 240, 150)
        self.assertEqual(self.activity._zone, "fire")

    # -- presenting -------------------------------------------------------

    def test_a_band_with_pixels_is_copied_and_flushed(self):
        surface = self.activity._surface
        self.activity._present_band(72, 2, b"\x01\x02\x03\x04")

        start = 72 * SURFACE_WIDTH * 2
        self.assertEqual(bytes(surface.buffer[start:start + 4]), b"\x01\x02\x03\x04")
        self.assertEqual(surface.invalidated, [1])  # row 72 is in band 1
        self.assertEqual(surface.flushed, 1)

    def test_a_band_without_pixels_is_only_flushed(self):
        surface = self.activity._surface
        before = bytes(surface.buffer[0:4])
        self.activity._present_band(0, 72, None)

        self.assertEqual(bytes(surface.buffer[0:4]), before)
        self.assertEqual(surface.invalidated, [0])
        self.assertEqual(surface.flushed, 1)

    # -- buttons ----------------------------------------------------------

    def test_enter_selects_and_uses(self):
        self.activity._on_key(_Event(key=lv.KEY.ENTER))
        # ENTER is event-driven (a menu acts on the keydown), so it taps. USE is
        # state-driven and stays held: the engine drains its whole queue in one
        # frame, so a release queued straight after the press would cancel it
        # before the tic is built and the door would never open.
        self.assertEqual(self.activity._keys, [
            (doom_core.KEY_ENTER, True), (doom_core.KEY_ENTER, False),
            (doom_core.KEY_USE, True),
        ])
        self.assertIn(doom_core.KEY_USE, self.activity._held)

    def test_fire_button_is_held_and_then_released(self):
        self.activity._on_key(_Event(key=ord("B")))
        self.assertEqual(self.activity._keys, [(doom_core.KEY_FIRE, True)])
        self.assertIn(doom_core.KEY_FIRE, self.activity._held)

        # A repeat within the hold window must not queue a second press.
        self.activity._on_key(_Event(key=ord("B")))
        self.assertEqual(self.activity._keys, [(doom_core.KEY_FIRE, True)])

    def test_arrow_keys_turn_into_doom_arrows(self):
        self.activity._on_key(_Event(key=lv.KEY.LEFT))
        self.activity._on_key(_Event(key=lv.KEY.RIGHT))
        self.assertEqual(self.activity._keys, [
            (doom_core.KEY_LEFTARROW, True),
            (doom_core.KEY_RIGHTARROW, True),
        ])

    def test_escape_opens_the_menu(self):
        self.activity._on_key(_Event(key=lv.KEY.ESC))
        self.assertEqual(self.activity._keys, [
            (doom_core.KEY_ESCAPE, True), (doom_core.KEY_ESCAPE, False),
        ])

    def test_y_opens_the_doom_menu(self):
        # X is the OS back key on the 2026 badge, so Y is Doom's own menu.
        self.activity._on_key(_Event(key=ord("Y")))
        self.assertEqual(self.activity._keys, [
            (doom_core.KEY_ESCAPE, True), (doom_core.KEY_ESCAPE, False),
        ])

    def test_held_key_is_released_on_the_next_frame(self):
        self.activity._on_key(_Event(key=lv.KEY.LEFT))
        self.activity._held[doom_core.KEY_LEFTARROW] = time.ticks_add(time.ticks_ms(), -1)
        self.activity._next_frame_ms = 0
        self.activity._drawframe()

        self.assertIn((doom_core.KEY_LEFTARROW, False), self.activity._keys)
        self.assertEqual(doom_core.KEY_LEFTARROW in self.activity._held, False)

    # -- touch ------------------------------------------------------------

    def _touch(self, code, x, y):
        InputManager.pointer_xy = staticmethod(lambda: (x, y))
        self.activity._on_touch(_Event(code=code))

    def _width(self):
        return mpos.ui.main_display.get_horizontal_resolution()

    def _panel(self, sx, sy):
        """Game point -> panel point: the inverse of the core's rotation."""
        return (self.activity._surface._image_x + (SURFACE_WIDTH - 1 - sy),
                self.activity._surface._image_y + sx)

    def _touch_game(self, code, sx, sy):
        x, y = self._panel(sx, sy)
        self._touch(code, x, y)

    def test_the_joystick_turns_and_walks_with_the_drag(self):
        self._touch_game(lv.EVENT.PRESSED, 80, 100)
        # Anchored, not a fixed pad: the press alone asks for no direction.
        self.assertEqual(self.activity._keys, [])

        self._touch_game(lv.EVENT.PRESSING, 40, 100)
        self.assertEqual(self.activity._keys, [(doom_core.KEY_LEFTARROW, True)])

        # Dragging towards Doom's top walks forward and drops the turn.
        self._touch_game(lv.EVENT.PRESSING, 80, 40)
        self.assertEqual(self.activity._keys, [
            (doom_core.KEY_LEFTARROW, True), (doom_core.KEY_LEFTARROW, False),
            (doom_core.KEY_UPARROW, True),
        ])

        self._touch_game(lv.EVENT.RELEASED, 80, 40)
        self.assertEqual(self.activity._keys[-1], (doom_core.KEY_UPARROW, False))
        self.assertEqual(self.activity._held, {})

    def test_the_joystick_ignores_a_drag_inside_the_deadzone(self):
        self._touch_game(lv.EVENT.PRESSED, 80, 100)
        self._touch_game(lv.EVENT.PRESSING, 90, 108)
        self.assertEqual(self.activity._keys, [])
        self.assertEqual(self.activity._held, {})

    def test_the_fire_band_holds_fire_while_pressed(self):
        self._touch_game(lv.EVENT.PRESSED, 240, 180)
        self.assertEqual(self.activity._keys, [(doom_core.KEY_FIRE, True)])
        self.assertIn(doom_core.KEY_FIRE, self.activity._held)

        self._touch_game(lv.EVENT.RELEASED, 240, 180)
        self.assertEqual(self.activity._keys[-1], (doom_core.KEY_FIRE, False))
        self.assertEqual(self.activity._held, {})

    def test_the_use_band_holds_use(self):
        self._touch_game(lv.EVENT.PRESSED, 240, 90)
        self.assertEqual(self.activity._keys, [(doom_core.KEY_USE, True)])
        self.assertIn(doom_core.KEY_USE, self.activity._held)

    def test_the_menu_band_taps_escape(self):
        self._touch_game(lv.EVENT.PRESSED, 240, 20)
        self.assertEqual(self.activity._keys, [
            (doom_core.KEY_ESCAPE, True), (doom_core.KEY_ESCAPE, False),
        ])

    def test_a_thumb_at_the_panel_bottom_is_the_button_side(self):
        # The rotation guard: the panel's bottom edge is Doom's *right*, so it
        # must land in a button band, not on the joystick.
        x = self.activity._surface._image_x + 100
        self._touch(lv.EVENT.PRESSED, x, SURFACE_HEIGHT - 10)
        self.assertEqual(self.activity._zone, "use")

    def test_a_thumb_at_the_panel_top_is_the_joystick(self):
        x = self.activity._surface._image_x + 100
        self._touch(lv.EVENT.PRESSED, x, 10)
        self.assertEqual(self.activity._zone, "stick")
        self.assertEqual(self.activity._keys, [])

    def _patch_pcm(self):
        """Stand in for AudioManager.open_pcm; returns (sink, restore)."""
        class _Sink:
            def __init__(self):
                self.writes = []
                self.closes = 0
                self.active = True

            def write(self, buffer):
                self.writes.append(bytes(buffer))
                return len(buffer)

            def close(self):
                self.closes += 1
                self.active = False

        sink = _Sink()
        real = doom_core.AudioManager

        class _Audio:
            @staticmethod
            def open_pcm(rate, channels=1, output=None):
                sink.rate = rate
                return sink

        doom_core.AudioManager = _Audio

        def restore():
            doom_core.AudioManager = real
            self.activity._close_audio()

        return sink, restore

    def test_the_app_asks_the_os_for_a_sink_and_feeds_it(self):
        # Which device that sink is (DAC, piezo) belongs to the framework: the
        # app only says "here are samples".
        sink, restore = self._patch_pcm()
        try:
            self.activity._open_audio()
            self.assertIs(self.activity._sink, sink)
            self.assertEqual(sink.rate, doom_core.SAMPLE_RATE)

            self.activity._audio_ms = time.ticks_ms() - 60
            self.activity._pump_audio(time.ticks_ms())
            self.assertTrue(any(any(chunk) for chunk in sink.writes),
                            "the sink got silence")

            self.activity._paused = False
            self.activity.onPause(None)
            self.assertTrue(sink.closes > 0, "the sink was not closed")
        finally:
            restore()

    def test_no_sink_means_no_audio_and_no_crash(self):
        real = doom_core.AudioManager

        class _Audio:
            @staticmethod
            def open_pcm(rate, channels=1, output=None):
                return None

        doom_core.AudioManager = _Audio
        try:
            self.activity._open_audio()
            self.assertIsNone(self.activity._sink)
            self.activity._pump_audio(time.ticks_ms())
        finally:
            doom_core.AudioManager = real

    # -- measurements -----------------------------------------------------

    def test_stats_count_the_keys_the_engine_took(self):
        self.activity.key(doom_core.KEY_ESCAPE)
        drained = []
        while True:
            code = self.activity._poll_key()
            if code < 0:
                break
            drained.append(code)
        self.assertEqual(drained, [doom_core.KEY_ESCAPE | 0x100,
                                   doom_core.KEY_ESCAPE])
        self.assertEqual(self.activity.get_stats()["keys"], 2)


if __name__ == "__main__":
    unittest.main()
