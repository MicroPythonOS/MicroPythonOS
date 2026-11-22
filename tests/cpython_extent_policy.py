"""mpos.extent policy: the rewrite from the Python defragmenter to lfs2e.

Run with CPython from the repository root:

    python3 tests/cpython_extent_policy.py

The C module is a firmware user module, so this loads extent.py by path with a
fake lfs2e, and checks only the policy layer: when reserve falls through to
defrag, that the run is not reserved twice, that errors propagate, and that the
CRC and offsets reach lfs2e unchanged.
"""

import asyncio
import binascii
import importlib.util
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXTENT_PY = os.path.join(
    _HERE, "..", "internal_filesystem", "lib", "mpos", "extent.py")

NOCONTIG = 129
NOSPC = 28


class FakeLfs2e:
    """Records the calls extent.py makes, with scripted failures."""

    def __init__(self):
        self.reserve_errors = []
        self.defrag_error = None
        self.begin_error = None
        self.step_results = []
        self.step_error = None
        self._begun = False
        self.calls = []
        self.written = bytearray()
        self.extent = (4096, 91, 0x12345678)

    def geometry(self):
        return (4096, 1792, 0x20001)

    def reserve(self, length, align):
        self.calls.append(("reserve", length, align))
        if self.reserve_errors:
            raise OSError(self.reserve_errors.pop(0))
        return (4096, 91)

    def defrag(self, length, align):
        self.calls.append(("defrag", length, align))
        if self.defrag_error is not None:
            raise OSError(self.defrag_error)
        return (4096, 91)

    def defrag_begin(self, length, align, budget=0):
        self.calls.append(("defrag_begin", length, align))
        if self.begin_error is not None:
            raise OSError(self.begin_error)
        if self._begun:
            raise OSError(NOSPC)   # a second begin: EINVAL on device
        self._begun = True

    def defrag_step(self):
        self.calls.append(("defrag_step",))
        if self.step_error is not None:
            raise OSError(self.step_error)
        if self.step_results:
            return self.step_results.pop(0)
        return (0, 2, 100)

    def defrag_result(self):
        self.calls.append(("defrag_result",))
        return (4096, 91)

    def defrag_abort(self):
        self.calls.append(("defrag_abort",))
        self._begun = False

    def write(self, offset, data):
        self.calls.append(("write", offset, len(data)))
        self.written[offset:offset + len(data)] = data

    def commit(self, path, crc):
        self.calls.append(("commit", path, crc))

    def abort(self):
        self.calls.append(("abort",))

    def info(self, path):
        self.calls.append(("info", path))
        return self.extent


def load_extent(fake):
    sys.modules["lfs2e"] = fake
    spec = importlib.util.spec_from_file_location("extent_under_test", _EXTENT_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ExtentStepDriverTest(unittest.TestCase):
    """open_writer(): the resumable defrag the installer awaits."""

    def _run(self, fake, progress=None, **kwargs):
        extent = load_extent(fake)
        return asyncio.run(extent.open_writer(370000, 16, progress=progress,
                                               **kwargs))

    def test_steps_run_to_completion_and_reserve(self):
        fake = FakeLfs2e()
        fake.reserve_errors = [NOCONTIG]
        fake.step_results = [(1, 1, 50), (1, 2, 100), (0, 2, 100)]
        seen = []

        async def progress(phase, percent):
            seen.append((phase, percent))

        writer = self._run(fake, progress=progress)
        kinds = [call[0] for call in fake.calls]
        self.assertEqual(kinds.count("reserve"), 1)   # no second reserve
        self.assertEqual(kinds.count("defrag_step"), 3)
        self.assertIn("defrag_result", kinds)
        # The driver must not stay marked active once the run is reserved.
        self.assertEqual(kinds.count("defrag_abort"), 1)
        self.assertEqual(seen[0], (1, 60))   # MOVE 50% -> 60% overall
        self.assertEqual(seen[-1], (2, 100))
        self.assertEqual(writer.length, 370000)
        self.assertEqual(writer.offset, 0)

    def test_progress_reaches_100(self):
        fake = FakeLfs2e()
        fake.reserve_errors = [NOCONTIG]
        fake.step_results = [(1, 2, 100), (0, 2, 100)]
        values = []

        async def progress(phase, percent):
            values.append(percent)

        self._run(fake, progress=progress)
        self.assertEqual(values[-1], 100)

    def test_failure_aborts_the_run(self):
        fake = FakeLfs2e()
        fake.reserve_errors = [NOCONTIG]
        fake.step_error = NOSPC
        with self.assertRaises(OSError):
            self._run(fake)
        self.assertIn("defrag_abort", [call[0] for call in fake.calls])

    def test_progress_exception_aborts_the_run(self):
        fake = FakeLfs2e()
        fake.reserve_errors = [NOCONTIG]
        fake.step_results = [(1, 1, 10), (1, 1, 20), (0, 1, 100)]

        async def progress(phase, percent):
            raise RuntimeError("ui died")

        with self.assertRaises(RuntimeError):
            self._run(fake, progress=progress)
        self.assertIn("defrag_abort", [call[0] for call in fake.calls])

    def test_a_second_run_after_success_is_allowed(self):
        fake = FakeLfs2e()
        fake.reserve_errors = [NOCONTIG]
        extent = load_extent(fake)
        asyncio.run(extent.open_writer(1000, 16))
        asyncio.run(extent.open_writer(1000, 16))

    def test_reserve_success_never_enters_the_driver(self):
        fake = FakeLfs2e()
        writer = self._run(fake)
        kinds = [call[0] for call in fake.calls]
        self.assertEqual(kinds, ["reserve"])
        self.assertEqual(writer.length, 370000)


class ExtentPolicyTest(unittest.TestCase):

    def test_reserve_success_does_not_defrag(self):
        fake = FakeLfs2e()
        extent = load_extent(fake)
        extent.Writer(370000, 16)
        self.assertEqual(fake.calls[0], ("reserve", 370000, 16))
        self.assertNotIn("defrag", [call[0] for call in fake.calls])

    def test_nocontig_defrags_once_and_keeps_the_reservation(self):
        fake = FakeLfs2e()
        fake.reserve_errors = [NOCONTIG]
        extent = load_extent(fake)
        extent.Writer(370000, 16)
        kinds = [call[0] for call in fake.calls]
        self.assertEqual(kinds, ["reserve", "defrag"])
        # defrag() reserves the run itself; a second reserve would let the
        # allocator choose a different one.
        self.assertEqual(fake.calls[1], ("defrag", 370000, 16))

    def test_defrag_first_false_does_not_defrag(self):
        fake = FakeLfs2e()
        fake.reserve_errors = [NOCONTIG]
        extent = load_extent(fake)
        with self.assertRaises(OSError) as caught:
            extent.Writer(1000, 16, defrag_first=False)
        self.assertEqual(caught.exception.args[0], NOCONTIG)
        self.assertEqual([call[0] for call in fake.calls], ["reserve"])

    def test_other_reserve_errors_are_not_retried(self):
        fake = FakeLfs2e()
        fake.reserve_errors = [NOSPC]
        extent = load_extent(fake)
        with self.assertRaises(OSError) as caught:
            extent.Writer(1000, 16)
        self.assertEqual(caught.exception.args[0], NOSPC)
        self.assertEqual([call[0] for call in fake.calls], ["reserve"])

    def test_defrag_failure_propagates(self):
        fake = FakeLfs2e()
        fake.reserve_errors = [NOCONTIG]
        fake.defrag_error = NOCONTIG
        extent = load_extent(fake)
        with self.assertRaises(OSError) as caught:
            extent.Writer(1000, 16)
        self.assertEqual(caught.exception.args[0], NOCONTIG)

    def test_degenerate_lengths(self):
        fake = FakeLfs2e()
        extent = load_extent(fake)
        for length in (0, -1):
            with self.assertRaises(OSError):
                extent.Writer(length)
        self.assertEqual(fake.calls, [])

    def test_write_and_commit_carry_offset_and_crc(self):
        fake = FakeLfs2e()
        extent = load_extent(fake)
        writer = extent.Writer(8, 1)
        writer.write(b"abcd")
        writer.write(b"efgh")
        expected = binascii.crc32(b"efgh", binascii.crc32(b"abcd", 0))
        found = writer.commit("data/app.xip")
        self.assertEqual(fake.calls[-2], ("commit", "/data/app.xip", expected))
        self.assertEqual(fake.calls[-1], ("info", "/data/app.xip"))
        self.assertEqual(found, fake.extent)
        self.assertEqual(bytes(fake.written), b"abcdefgh")

    def test_commit_before_full_write_is_refused(self):
        fake = FakeLfs2e()
        extent = load_extent(fake)
        writer = extent.Writer(8, 1)
        writer.write(b"abcd")
        with self.assertRaises(OSError):
            writer.commit("app.xip")
        self.assertNotIn("commit", [call[0] for call in fake.calls])
        writer.abort()
        self.assertEqual(fake.calls[-1], ("abort",))

    def test_write_past_length_is_refused(self):
        fake = FakeLfs2e()
        extent = load_extent(fake)
        writer = extent.Writer(4, 1)
        with self.assertRaises(OSError):
            writer.write(b"abcde")
        self.assertNotIn("write", [call[0] for call in fake.calls])


if __name__ == "__main__":
    unittest.main()
