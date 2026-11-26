"""The engine's own picture, run as a desktop native module.

The tilt view (Duke's death screen) is drawn into a 320x320 tile and turned
back onto the screen. Everything drawn after it - the status bar and the menus -
belongs to the screen, so the two must not be confused: when the renderer's
view offset was left pointing into the tile, the frame froze at the moment of
death and the pause menu came out as fragmentary red blocks.

A badge runs the same engine as a flash-resident core; only a desktop can load
it as a module, which is what these tests use.
"""

import sys
import time
import unittest

import lvgl as lv  # noqa: F401  (graphical test: the runner boots LVGL)

APP_DIR = "apps/com.micropythonos.duke3d"
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import duke3d  # noqa: E402
import duke_controls  # noqa: E402


class _Surface:
    """What the engine adapter asks of a surface.

    The present path itself (bands through LVGL) has its own test; here the
    engine writes into a buffer the test can read, so a band is a no-op.
    """

    _active = True

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.rows_per_band = 45
        self.buffer = bytearray(width * height * 2)

    def invalidate_band(self, band):
        pass

    def flush(self):
        pass


def _red_fraction(buffer):
    """How much of the frame is the death view's red tint.

    Every 16th pixel: the tint covers the whole picture, so sampling keeps the
    loop cheap on a desktop bytearray.
    """
    sampled = 0
    red = 0
    for offset in range(0, len(buffer) - 1, 32):
        value = buffer[offset] | (buffer[offset + 1] << 8)
        r = (value >> 11) & 0x1F
        g = (value >> 5) & 0x3F
        b = value & 0x1F
        sampled += 1
        if r > 8 and r > 2 * g and r > 2 * b:
            red += 1
    return red / sampled


class TestDuke3DDeathScreen(unittest.TestCase):

    def setUp(self):
        if sys.platform == "esp32":
            self.skipTest("the engine runs as a core on a badge, not a module")
        try:
            self.engine = duke3d._NatmodEngine()
        except Exception as error:
            self.skipTest("no native engine module: %s" % (error,))
        self.surface = _Surface(duke3d.GAME_WIDTH, duke3d.GAME_HEIGHT)
        # The engine's timer starts from the clock the host passes, so the
        # ticks must continue on that timeline: starting from zero makes the
        # first tick look like a wrap and the game stops counting tics.
        self.now = time.ticks_ms()

    def _tick(self, count=1):
        for _ in range(count):
            self.now += 33
            self.engine.tick(self.now)

    def _start_level(self):
        grp, size = duke3d.prepare_grp(lambda *args: None)
        self.now = time.ticks_ms()
        self.engine.start((grp, size), self.surface, self.now)
        self._tick(20)
        self.engine._duke.debug_newgame()
        self._tick(60)

    def _press(self, code, count=4):
        self.engine.key(code, True)
        self._tick(count)
        self.engine.key(code, False)
        self._tick(count)

    def test_the_death_screen_and_its_menu_reach_the_screen(self):
        self._start_level()
        alive = self.engine._duke.debug_state()
        self.assertEqual(alive[0], 100, "the level did not start")
        self.assertTrue(_red_fraction(self.surface.buffer) < 0.2)

        self.engine._duke.debug_kill()
        self._tick(20)
        dead = self.engine._duke.debug_state()
        self.assertEqual(dead[0], 0, "the player is still alive: %r" % (dead,))
        self.assertTrue(dead[2] != 0,
                        "the death view is not tilted: %r" % (dead,))
        # The renderer must draw into the buffer the host presents, and every
        # span it asked for must fit there.
        self.assertTrue(dead[4], "the view offset does not follow the screen")
        self.assertEqual(dead[5], 0, "the renderer dropped part of the picture")
        self.assertTrue(_red_fraction(self.surface.buffer) > 0.6,
                        "the death view did not reach the screen")

        dying = bytes(self.surface.buffer)
        self._press(duke_controls.KEY_MENU, 6)
        menu = self.engine._duke.debug_state()
        self.assertEqual(menu[5], 0, "the renderer dropped part of the menu")
        self.assertTrue(bytes(self.surface.buffer) != dying,
                        "the menu did not draw over the death view")
        self.assertTrue(_red_fraction(self.surface.buffer) > 0.5,
                        "the menu replaced the death view instead of joining it")
