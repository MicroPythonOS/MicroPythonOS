#!/usr/bin/env python3
"""CPython regression test for #297: a probing host must not wedge the console.

A host program that opens the USB-CDC port and writes bytes which are not a
REPL session (device-detection probes send CBOR such as 0xA6 and then hold the
port open) used to leave the console in a blocking text-mode read waiting for
UTF-8 continuation bytes. The console task runs on the OS asyncio loop, so every
app task on the device froze until the host closed the port (~28 s per probe).

This drives the real PTY of the desktop build: it writes a lone UTF-8 lead byte
and checks that the console still answers immediately instead of stalling.

Usage:
    python3 tests/cpython_aiorepl_probe.py
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from scripts.mpos_controller import MPOSController

# A CBOR map header: a valid UTF-8 lead byte with no continuation byte, which is
# what a device-detection probe sends before holding the port.
PROBE = b"\xa6"

ANSWER_TIMEOUT_S = 2.0


class TestConsoleProbeDoesNotStallConsole(unittest.TestCase):

    def setUp(self):
        self.mpos = MPOSController(backend="process")
        self.mpos.start()
        self.mpos.exec("print('READY')", timeout=15)

    def tearDown(self):
        self.mpos.stop()

    def _timed_exec(self, code, timeout=15):
        t0 = time.monotonic()
        out = self.mpos.exec(code, timeout=timeout)
        return out, time.monotonic() - t0

    def test_partial_utf8_probe_does_not_stall_the_console(self):
        os.write(self.mpos._backend.master_fd, PROBE)
        time.sleep(1.5)

        out, elapsed = self._timed_exec("print('ALIVE')")
        self.assertTrue(b"ALIVE" in out, "console did not run the command: %r" % (out,))
        self.assertTrue(
            elapsed < ANSWER_TIMEOUT_S,
            "console took %.1fs to answer after a probe" % elapsed,
        )

    def test_console_keeps_answering_after_repeated_probes(self):
        for _ in range(3):
            os.write(self.mpos._backend.master_fd, PROBE)
            time.sleep(0.3)

        out, elapsed = self._timed_exec("print('ALIVE')")
        self.assertTrue(b"ALIVE" in out, "console did not run the command: %r" % (out,))
        self.assertTrue(
            elapsed < ANSWER_TIMEOUT_S,
            "console took %.1fs to answer after three probes" % elapsed,
        )


if __name__ == "__main__":
    unittest.main()
