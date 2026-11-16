"""Tests for the native Doom activity.

The engine itself is a port; these tests cover the seam with MicroPythonOS:
the module's API, the band blit that converts the paletted frame for the
``NativeDisplay`` surface, and the activity's frame loop.

Starting the engine needs a WAD, which is not part of the repository, so the
tests that boot it skip when none is installed. Put one at
``internal_filesystem/doom1.wad`` (or /doom1.wad on the device) to run them.
"""

import os
import sys
import time
import unittest

import lvgl as lv

import mpos.ui
from mpos import AppManager
from mpos.ui.view import remove_and_stop_current_activity, screen_stack

_APP_DIR = "apps/com.micropythonos.doom"
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

if sys.platform == "esp32":
    import doom_xtensawin as doom
else:
    import doom_x64 as doom

WIDTH = 320
HEIGHT = 200

WAD_PATHS = ("doom1.wad", "/doom1.wad", "/sdcard/doom1.wad")


def _find_wad():
    for path in WAD_PATHS:
        try:
            open(path, "rb").close()
            return path
        except Exception:
            continue
    return None


def _wait_ms(ms):
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < ms:
        lv.task_handler()
        time.sleep_ms(5)


class TestDoomModule(unittest.TestCase):

    def test_the_module_exposes_the_engine_api(self):
        for name in ("create", "tick", "frame", "palette", "blit_band",
                     "key", "width", "height"):
            self.assertTrue(hasattr(doom, name), "missing %s" % name)

    def test_the_engine_frame_is_paletted_320x200(self):
        self.assertEqual(doom.width(), WIDTH)
        self.assertEqual(doom.height(), HEIGHT)

    def test_key_codes_are_doom_keys(self):
        # Doom's internal key codes, not ASCII (KEY_UPARROW is 0xad).
        self.assertEqual(doom.KEY_UP, 0xad)
        self.assertEqual(doom.KEY_LEFT, 0xac)
        self.assertEqual(doom.KEY_ESCAPE, 27)
        self.assertEqual(doom.KEY_ENTER, 13)


class TestDoomActivity(unittest.TestCase):

    def setUp(self):
        self.wad = _find_wad()
        if self.wad is None:
            self.skipTest("no WAD installed (put one at doom1.wad)")
        self.assertTrue(AppManager.start_app("com.micropythonos.doom"))
        _wait_ms(1500)
        self.activity = None
        for entry in screen_stack:
            if type(entry[0]).__name__ == "Doom":
                self.activity = entry[0]
        self.assertIsNotNone(self.activity, "the Doom activity is not on the stack")

    def tearDown(self):
        while len(screen_stack) > 1:
            remove_and_stop_current_activity()

    def test_the_demo_renders_into_the_surface(self):
        stats = self.activity.get_stats()
        self.assertEqual(stats["wad"], self.wad)
        self.assertTrue(stats["frames"] > 0, "no frames were presented")
        surface = self.activity._surface
        # Doom's demo draws a level: the surface must not be one flat colour.
        colours = set()
        for i in range(0, len(surface.buffer), 997):
            colours.add(surface.buffer[i])
            if len(colours) > 4:
                break
        self.assertTrue(len(colours) > 4, "the surface looks blank")

    def test_a_band_blit_writes_that_band_only(self):
        surface = self.activity._surface
        surface.buffer[:] = bytes(len(surface.buffer))
        doom.blit_band(surface.buffer, 1, surface.rows_per_band)
        rows = surface.rows_per_band
        band_start = rows * WIDTH * 2
        band_end = band_start + rows * WIDTH * 2
        self.assertEqual(surface.buffer[:band_start], bytes(band_start),
                         "rows above the band were written")
        self.assertNotEqual(surface.buffer[band_start:band_end],
                            bytes(band_end - band_start),
                            "the band was not drawn")

    def test_pausing_stops_the_frame_loop(self):
        self.activity.onPause(None)
        frames = self.activity.get_stats()["frames"]
        _wait_ms(300)
        self.assertEqual(self.activity.get_stats()["frames"], frames)


class TestDoomOnTheRealDisplay(unittest.TestCase):

    def test_the_surface_is_letterboxed_on_the_panel(self):
        if mpos.ui.main_display is None:
            self.skipTest("no display")
        screen = lv.obj()
        lv.screen_load(screen)
        try:
            from mpos.ui.native_display import NativeDisplay
            surface = NativeDisplay(screen, width=WIDTH, height=HEIGHT)
        finally:
            lv.screen_load(lv.obj())
        self.assertEqual(surface.width, WIDTH)
        self.assertEqual(surface.height, HEIGHT)
        if surface.display.get_vertical_resolution() > HEIGHT:
            self.assertTrue(surface._image_y > 0, "the surface is not centred")
