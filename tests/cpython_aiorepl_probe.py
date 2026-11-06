#!/usr/bin/env python3
"""CPython regression test for #297: a probing host must not wedge the console.

A host program that opens the USB-CDC port and writes bytes which are not a
REPL session (device-detection probes send CBOR such as 0xA6 and then hold the
port open) used to leave the console in a blocking text-mode read waiting for
UTF-8 continuation bytes. The console task runs on the OS asyncio loop, so every
app task on the device froze until the host closed the port (~28 s per probe).

Writes a lone UTF-8 lead byte into the console and checks that it still answers
immediately instead of stalling.

Usage:
    python3 tests/cpython_aiorepl_probe.py                     # desktop build
    python3 tests/cpython_aiorepl_probe.py --serial /dev/ttyACM0
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

DESKTOP_ANSWER_TIMEOUT_S = 2.0
DEVICE_ANSWER_TIMEOUT_S = 5.0


def _serial_port_from_argv():
    if "--serial" in sys.argv:
        index = sys.argv.index("--serial")
        port = sys.argv[index + 1]
        del sys.argv[index:index + 2]
        return port
    return os.environ.get("MPOS_TEST_PORT")


class TestConsoleProbeDoesNotStallConsole(unittest.TestCase):

    def setUp(self):
        port = _serial_port_from_argv()
        if port:
            self.mpos = MPOSController(backend="serial", port=port)
            self.answer_timeout = DEVICE_ANSWER_TIMEOUT_S
        else:
            self.mpos = MPOSController(backend="process")
            self.answer_timeout = DESKTOP_ANSWER_TIMEOUT_S
        self.mpos.start()
        self.mpos.exec("print('READY')", timeout=30)

    def tearDown(self):
        self.mpos.stop()

    def _write_probe(self, data):
        backend = self.mpos._backend
        if hasattr(backend, "ser"):
            backend.ser.write(data)
        else:
            os.write(backend.master_fd, data)

    def _timed_exec(self, code, timeout=30):
        t0 = time.monotonic()
        out = self.mpos.exec(code, timeout=timeout)
        return out, time.monotonic() - t0

    def test_partial_utf8_probe_does_not_stall_the_console(self):
        self._write_probe(PROBE)
        time.sleep(1.5)

        out, elapsed = self._timed_exec("print('ALIVE')")
        self.assertTrue(b"ALIVE" in out, "console did not run the command: %r" % (out,))
        self.assertTrue(
            elapsed < self.answer_timeout,
            "console took %.1fs to answer after a probe" % elapsed,
        )

    def test_console_keeps_answering_after_repeated_probes(self):
        for _ in range(3):
            self._write_probe(PROBE)
            time.sleep(0.3)

        out, elapsed = self._timed_exec("print('ALIVE')")
        self.assertTrue(b"ALIVE" in out, "console did not run the command: %r" % (out,))
        self.assertTrue(
            elapsed < self.answer_timeout,
            "console took %.1fs to answer after three probes" % elapsed,
        )


if __name__ == "__main__":
    unittest.main()
