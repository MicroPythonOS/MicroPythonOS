"""Desktop Duke3D: the native module booted for real, plus save/load.

The badge runs the same engine as a flash-resident core and is not what these
tests exercise; the desktop path was added because there is no MMU window to
map a core into. Booting the module with the bundled compacted GRP is a few
seconds of C work, so this test runs a short session, checks that bands reach
the surface, and round-trips the engine's own save/load functions through the
app's prefs directory.

The engine needs ``module_x64.mpy`` in the app directory and the bundled
``*.grp.zip``; both are released with the app, so a checkout with the app
installed runs this. A host without the native module skips.
"""

import os
import sys
import time
import unittest

import lvgl as lv  # noqa: F401 - the graphical test runner boots LVGL

import mpos.ui  # noqa: F401

APP_DIR = "apps/com.micropythonos.duke3d"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import duke3d  # noqa: E402

try:
    import zipasset  # noqa: F401
except ImportError:
    zipasset = None

try:
    import module_x64  # noqa: F401
except ImportError:
    module_x64 = None


class _FakeDisplay:
    def __init__(self, width, height):
        self._width = width
        self._height = height

    def get_horizontal_resolution(self):
        return self._width

    def get_vertical_resolution(self):
        return self._height


class _FakeSurface:
    """Records bands instead of drawing: the engine's frame path without LVGL."""

    def __init__(self, width, height, rows):
        self.width = width
        self.height = height
        self.rows_per_band = rows
        self.band_count = (height + rows - 1) // rows
        self.buffer = bytearray(width * height * 2)
        self._active = True
        self.invalidated = []
        self.flushed = 0

    def invalidate_band(self, band):
        self.invalidated.append(band)

    def flush(self):
        self.flushed += 1
        return True


class TestDuke3DDesktop(unittest.TestCase):

    def setUp(self):
        self.prefs = duke3d._absolute(duke3d.PREFS_DIR)
        self.save = self.prefs + "/duke3d/game0.sav"
        try:
            os.remove(self.save)
        except OSError:
            pass

    def tearDown(self):
        try:
            os.remove(self.save)
        except OSError:
            pass

    def test_desktop_selects_the_native_module(self):
        if sys.platform == "esp32":
            self.skipTest("the badge runs the flash-resident core")
        if module_x64 is None:
            self.skipTest("no native Duke3D module for this host")
        engine = duke3d._NatmodEngine()
        self.assertIsInstance(engine, duke3d._NatmodEngine)
        self.assertEqual(engine.surface_size(_FakeDisplay(320, 240)),
                         (duke3d.GAME_WIDTH, duke3d.GAME_HEIGHT))

    def test_the_engine_draws_and_saves(self):
        if sys.platform == "esp32":
            self.skipTest("the badge runs the flash-resident core")
        if module_x64 is None:
            self.skipTest("no native Duke3D module for this host")
        if zipasset is None:
            self.skipTest("this firmware has no zipasset support")

        loading = lambda text, done=0, total=0: None
        grp = duke3d.prepare_grp(loading)
        engine = duke3d._NatmodEngine()
        surface = _FakeSurface(duke3d.GAME_WIDTH, duke3d.GAME_HEIGHT,
                               rows=72)
        try:
            engine.start(grp, surface)
            now = time.ticks_ms()
            for _ in range(120):
                now = time.ticks_add(now, 20)
                engine.tick(now)
            self.assertFalse(engine.quit, "the engine asked to quit")
            self.assertTrue(surface.invalidated,
                            "no band reached the surface")
            self.assertTrue(surface.flushed, "no band was flushed")

            self.assertEqual(engine._duke.save_slot(0), 0)
            self.assertTrue(os.stat(self.save)[6] > 0,
                            "save file is empty")
            self.assertEqual(engine._duke.load_slot(0), 0)
        finally:
            engine.stop()
            buffer, _size = grp
            if not isinstance(buffer, str):
                duke3d._free_asset_buffer(buffer)
