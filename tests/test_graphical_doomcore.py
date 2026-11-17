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

SURFACE_WIDTH = 200
SURFACE_HEIGHT = 320


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
        return 5


fake_core = _FakeCore()
_real_core = sys.modules.get("mpos_core")
sys.modules["mpos_core"] = fake_core
sys.modules.pop("doom_core", None)
import doom_core  # noqa: E402

# doom_core keeps the fake it was imported with; other tests keep the real one.
if _real_core is not None:
    sys.modules["mpos_core"] = _real_core


class _FakeSurface:
    """A display surface that records invalidations instead of drawing."""

    rows_per_band = 72
    band_count = 5

    def __init__(self, screen=None, width=None, height=None, buffer=None):
        self.buffer = bytearray(SURFACE_WIDTH * SURFACE_HEIGHT * 2)
        self._active = True
        self.invalidated = []
        self.flushed = 0

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
        # The core draws straight into the surface buffer, one display band at a
        # time: that is what overlaps the transfer with the next conversion.
        self.assertIs(args[12], self.activity._surface.buffer)
        self.assertEqual(args[13], _FakeSurface.rows_per_band)

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

    def test_left_third_turns_left(self):
        self._touch(lv.EVENT.PRESSED, self._width() // 6, SURFACE_HEIGHT // 2)
        self.assertEqual(self.activity._keys, [(doom_core.KEY_LEFTARROW, True)])

        self._touch(lv.EVENT.RELEASED, self._width() // 6, SURFACE_HEIGHT // 2)
        self.assertEqual(self.activity._keys, [
            (doom_core.KEY_LEFTARROW, True), (doom_core.KEY_LEFTARROW, False),
        ])

    def test_middle_tap_walks_and_fires(self):
        middle = self._width() // 2
        self._touch(lv.EVENT.PRESSED, middle, SURFACE_HEIGHT // 2)
        self._touch(lv.EVENT.RELEASED, middle, SURFACE_HEIGHT // 2)

        self.assertEqual(self.activity._keys, [
            (doom_core.KEY_UPARROW, True),
            (doom_core.KEY_UPARROW, False),
            (doom_core.KEY_FIRE, True),
        ])
        # Fired like a button, not tapped: see test_enter_selects_and_uses.
        self.assertIn(doom_core.KEY_FIRE, self.activity._held)

    def test_touch_on_the_top_edge_opens_the_menu(self):
        self._touch(lv.EVENT.PRESSED, self._width() // 2, 4)
        self.assertEqual(self.activity._keys, [
            (doom_core.KEY_ESCAPE, True), (doom_core.KEY_ESCAPE, False),
        ])
        self.assertEqual(self.activity._touch_key, 0)

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
