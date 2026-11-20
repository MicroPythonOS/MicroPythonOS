"""The installed Doom engine, started from its extent, on a badge.

No display: the test hands the core its own 320x200 surface and ticks it, which
is what the activity does once the panel is out of the way. That makes it
runnable on a board whose panel is smaller than Doom's frame, and it pins the
three things only hardware can answer:

* the App Store installed the engine as a littlefs2e extent whose CRC matches;
* ``mpos_core`` (ABI 8) maps it and the engine initializes, reads the WAD through
  the host callbacks and presents bands;
* a wrong CRC is refused before anything is mapped executable.

The app must be installed (``/apps/com.micropythonos.doom``); the test skips
otherwise.
"""

import sys
import unittest

import mpos.extent as extent
import mpos.zipasset as zipasset

APP = "/apps/com.micropythonos.doom"
XIP = APP + "/esp32s3.xip"
WAD_ZIP = APP + "/doom1.wad.zip"
WAD_NAME = "doom1.wad"
WIDTH = 320
HEIGHT = 200
BAND_ROWS = 45


@unittest.skipUnless(sys.platform == "esp32" and extent.available(),
                     "littlefs2e is only available on ESP32 firmware")
class DoomCoreOnDevice(unittest.TestCase):

    def setUp(self):
        import os
        for path in (XIP, WAD_ZIP):
            try:
                os.stat(path)
            except OSError:
                self.skipTest("the Doom app is not installed")

    def _start(self, expected_crc, state):
        import mpos_core
        offset, length, crc = extent.info(XIP)
        if expected_crc is None:
            expected_crc = crc
        wad, size = zipasset.load(WAD_ZIP)
        state["wad"] = wad
        state["size"] = size

        def present(y, rows, data):
            state["bands"].append((y, rows))

        def palette(entries):
            return bytes(entries * 2)

        def poll():
            return -1

        def read_file(path, at, into):
            if path != WAD_NAME:
                return -1
            if at >= size:
                return 0
            count = size - at
            if count > len(into):
                count = len(into)
            into[:count] = wad[at:at + count]
            return count

        def file_size(path):
            return size if path == WAD_NAME else -1

        def log(line):
            state["log"].append(line)

        surface = bytearray(WIDTH * HEIGHT * 2)
        state["surface"] = surface
        mpos_core.start(
            "vfs", offset, length,
            present, palette, poll, read_file, file_size, log,
            WAD_NAME, WIDTH, HEIGHT, surface, BAND_ROWS,
            expected_crc, "/prefs/com.micropythonos.doom")
        return mpos_core

    def _state(self):
        return {"bands": [], "log": [], "wad": None, "size": 0, "surface": None}

    def tearDown(self):
        try:
            import mpos_core
            mpos_core.stop()
        except Exception:
            pass

    def test_the_installed_extent_maps_and_the_engine_draws(self):
        state = self._state()
        core = self._start(None, state)
        # A dozen frames, not hundreds: this runs inside one paste-mode exec, so
        # nothing else on the device gets to run until it returns, and a long
        # tight loop trips the task watchdog. The activity ticks once per frame
        # loop pass, which yields in between.
        for step in range(12):
            core.tick(1000 + step * 35)

        self.assertTrue(state["bands"], "the engine presented no bands")
        for y, rows in state["bands"]:
            self.assertEqual(y % BAND_ROWS, 0, "band not on the band grid")
            self.assertTrue(rows <= BAND_ROWS)
        self.assertEqual(core.mapped(), 0x43000000)
        self.assertTrue(core.mapped_size() > 0)
        # The engine ran, not just the loader: its banner came back through the
        # log callback and the frame is more than one colour.
        joined = "\n".join(state["log"])
        self.assertTrue("I_InitGraphics" in joined or "sound:" in joined,
                        "no engine output: %s" % joined[:200])
        colours = set(state["surface"][i] for i in range(0, len(state["surface"]), 997))
        self.assertTrue(len(colours) > 4, "the surface looks blank")
        self.assertEqual(state["size"], len(state["wad"]))

        # The mixer is part of the engine, so it has to answer even when the
        # host has no sink open.
        samples = bytearray(2048)
        core.audio_mix(samples)

    def test_a_wrong_crc_is_refused_before_mapping(self):
        offset, length, crc = extent.info(XIP)
        state = self._state()
        with self.assertRaises(OSError) as ctx:
            self._start(crc ^ 0xFFFFFFFF, state)
        self.assertIn("CRC", str(ctx.exception))
        self.assertEqual(state["bands"], [])


if __name__ == "__main__":
    unittest.main()
