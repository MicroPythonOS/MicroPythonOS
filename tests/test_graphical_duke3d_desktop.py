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

    def test_the_jump_key_leaves_the_floor(self):
        """B is the pad's jump and the engine's own jump binding (A)."""
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
            for _ in range(60):
                now = time.ticks_add(now, 20)
                engine.tick(now)
            floor = module_x64.pos()[9]

            engine.key(duke3d.KEY_JUMP, True)
            peak = floor
            for _ in range(25):  # the key edge, then ~0.5 s of flight
                now = time.ticks_add(now, 20)
                engine.tick(now)
                height = module_x64.pos()[9]
                if height < peak:
                    peak = height
            engine.key(duke3d.KEY_JUMP, False)
            # z grows downward, so airborne is a smaller z.
            self.assertTrue(peak < floor - 2000,
                            "jump moved the player %d units" % (floor - peak))
        finally:
            engine.stop()
            buffer, _size = grp
            if not isinstance(buffer, str):
                duke3d._free_asset_buffer(buffer)

    def test_a_held_key_does_not_run_at_render_speed(self):
        """A held direction must advance the game at the engine's tic rate.

        The native module's clock is the host's, and the engine installs its
        timer during start-up. When start-up saw a zero clock, the first tick
        looked like the whole host uptime had elapsed: ``totalclock`` jumped
        far ahead of the engine's own ``ototalclock``, and every
        ``faketimerhandler()`` call inside the renderer then counted as a game
        tic, so one short press ran the player across the level.
        """
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
        # A host that has been up for days is where the runaway clock showed:
        # the first tick must continue from the clock start() was given, not
        # from zero.
        started_at = 900000000
        try:
            engine.start(grp, surface, now_ms=started_at)
            now = started_at
            for _ in range(60):
                now = time.ticks_add(now, 20)
                engine.tick(now)

            # pos() = (x, y, ang, totalclock, sector, ototalclock, fifo,
            #          key_down, velocity, z)
            start = module_x64.pos()
            self.assertTrue(start[3] - start[5] < 100,
                            "the engine clock ran away from its tic clock")
            self.assertTrue(start[3] < 1000,
                            "the engine clock did not start with the session")

            engine.key(duke3d.KEY_UP, True)
            for _ in range(50):  # one second of engine time
                now = time.ticks_add(now, 20)
                engine.tick(now)
            engine.key(duke3d.KEY_UP, False)
            for _ in range(25):
                now = time.ticks_add(now, 20)
                engine.tick(now)

            end = module_x64.pos()
            dx = end[0] - start[0]
            dy = end[1] - start[1]
            walked = int((dx * dx + dy * dy) ** 0.5)
            # A second of walking covers a few tiles; the runaway clock covered
            # the room in the first frame. The bound is loose on purpose: the
            # level and the spawn sector are the bundled episode's, not this
            # test's.
            self.assertTrue(walked < 6000,
                            "one second of holding a direction moved %d units"
                            % walked)
            self.assertTrue(end[3] - end[5] < 100,
                            "the engine clock ran away from its tic clock")
            self.assertEqual(end[7], 0, "the key is still down after release")
        finally:
            engine.stop()
            buffer, _size = grp
            if not isinstance(buffer, str):
                duke3d._free_asset_buffer(buffer)
