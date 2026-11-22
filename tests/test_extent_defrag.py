"""littlefs2e defragmentation of a populated filesystem, on hardware.

Runs with the usual device runner; desktop skips because the lfs2e module is
firmware-only. The test fills the remaining space with small files, deletes
every third one to leave scattered holes, then converts a mid-sized file into a
64 KiB-aligned XIP extent and checks the payload, the neighbours and the tree.

Every loop yields: a blocking test starves the task watchdog and resets the
board (there is no traceback to learn from).
"""

import os
import sys
import time
import unittest

import mpos.extent as extent

_ROOT = "/defrag-test"
_TARGET = _ROOT + "/target.bin"
_ALIGN = extent.XIP_ALIGN_BLOCKS
_BLOCKS = 48  # 192 KiB of payload
_FILL_BLOCKS = 4  # 16 KiB per filler file


def _yield():
    time.sleep_ms(2)


def _pattern(size, seed):
    state = (seed + 1) * 2654435761 & 0xFFFFFFFF
    out = bytearray(size)
    for i in range(size):
        state = (state * 1103515245 + 12345) & 0xFFFFFFFF
        out[i] = (state >> 16) & 0xFF
        if (i & 0x1FFF) == 0x1FFF:
            _yield()
    return bytes(out)


def _rmtree(path):
    """shutil.rmtree cannot yield; delete files, then directories deepest first."""
    directories = []
    stack = [path]
    while stack:
        directory = stack.pop()
        directories.append(directory)
        try:
            names = os.listdir(directory)
        except OSError:
            continue
        for name in names:
            child = directory + "/" + name
            try:
                info = os.stat(child)
            except OSError:
                continue
            if info[0] & 0x4000:
                stack.append(child)
                continue
            try:
                os.remove(child)
            except OSError:
                pass
            _yield()
    for directory in reversed(directories):
        try:
            os.rmdir(directory)
        except OSError:
            pass


@unittest.skipUnless(
    sys.platform == "esp32" and extent.available(),
    "littlefs2e is only available on ESP32 firmware",
)
class ExtentDefragTest(unittest.TestCase):

    def setUp(self):
        self.block_size, self.block_count, _ = extent.geometry()
        self.fillers = []
        _rmtree(_ROOT)
        try:
            os.mkdir(_ROOT)
        except OSError:
            pass

    def tearDown(self):
        _rmtree(_ROOT)

    def _free_blocks(self):
        used = extent.lfs2e.used_map()
        free = 0
        for block in range(self.block_count):
            if not (used[block >> 3] >> (block & 7)) & 1:
                free += 1
        return free

    def _fragment(self):
        """Fill until full, then delete every third file to punch holes."""
        chunk = _pattern(_FILL_BLOCKS * self.block_size, 5)
        index = 0
        while True:
            directory = "%s/d%02d" % (_ROOT, index % 12)
            if index < 12:
                os.mkdir(directory)
            path = "%s/f%04d" % (directory, index)
            try:
                with open(path, "wb") as handle:
                    handle.write(chunk)
            except OSError:
                break
            self.fillers.append(path)
            index += 1
            _yield()
        removed = 0
        for path in self.fillers[::3]:
            os.remove(path)
            removed += 1
            if removed % 8 == 0:
                _yield()

    def _require_fragmented_fixture(self):
        self._fragment()
        free = self._free_blocks()
        largest = extent.largest_run(_ALIGN)
        if free < _BLOCKS + 32 or largest >= _BLOCKS:
            self.skipTest(
                "could not fragment this filesystem (free %d, largest %d)"
                % (free, largest))

    def test_defrag_makes_an_aligned_run(self):
        target_data = _pattern(_BLOCKS * self.block_size, 7)
        with open(_TARGET, "wb") as handle:
            handle.write(target_data)

        self._require_fragmented_fixture()
        self.assertTrue(extent.largest_run(_ALIGN) < _BLOCKS)
        print("fixture: %d fillers, free %d blocks, largest %d"
              % (len(self.fillers), self._free_blocks(),
                 extent.largest_run(_ALIGN)))

        updates = []

        def progress(phase, percent):
            updates.append((phase, percent))

        started = time.ticks_ms()
        offset, length, crc = extent.ensure(
            _TARGET, align=_ALIGN, defrag_first=True, progress=progress)
        print("defrag+reserve took %d ms (%d progress updates)"
              % (time.ticks_diff(time.ticks_ms(), started), len(updates)))
        self.assertTrue(updates)
        self.assertEqual(updates[-1][1], 100)
        for _, percent in updates:
            self.assertTrue(0 <= percent <= 100)
        self.assertEqual(length, len(target_data))
        self.assertEqual(offset % (_ALIGN * self.block_size), 0)
        self.assertTrue(crc != 0)

        # The run is contiguous, aligned and free of metadata.
        head = offset // self.block_size
        meta = extent.lfs2e.meta_map()
        for block in range(head, head + _BLOCKS):
            self.assertEqual((meta[block >> 3] >> (block & 7)) & 1, 0,
                             "metadata block %d inside the XIP run" % block)

        # Payload reads back byte for byte.
        with open(_TARGET, "rb") as handle:
            self.assertEqual(handle.read(), target_data)

        # Every surviving filler is still there and the right size.
        survivors = self.fillers[1::3]
        self.assertTrue(survivors)
        for path in survivors:
            self.assertEqual(os.stat(path)[6], _FILL_BLOCKS * self.block_size,
                             path)
            _yield()

        # The tree still walks: every filler directory is present.
        self.assertEqual(sorted(os.listdir(_ROOT))[:12],
                         sorted(["d%02d" % i for i in range(12)]))

        # Isolate what the defragmenter costs when it only has to scan and
        # reserve (a one-block run is free after the moves above).
        started = time.ticks_ms()
        extent.lfs2e.defrag(self.block_size, _ALIGN)
        scan_ms = time.ticks_diff(time.ticks_ms(), started)
        extent.lfs2e.abort()
        print("scan+reserve only: %d ms" % scan_ms)

    def test_step_driver_and_badge_sized_window(self):
        # The same driver the installer awaits, stepped by hand, and a window
        # the size of Doom's core (96 blocks, 64 KiB aligned).
        target = _pattern(_BLOCKS * self.block_size, 9)
        with open(_TARGET, "wb") as handle:
            handle.write(target)
        self._require_fragmented_fixture()

        extent.lfs2e.defrag_begin(96 * self.block_size, _ALIGN, 0)
        phases = []
        steps = 0
        try:
            while True:
                running, phase, percent = extent.lfs2e.defrag_step()
                steps += 1
                self.assertTrue(steps < 200000)
                self.assertTrue(0 <= percent <= 100)
                if phase not in phases:
                    phases.append(phase)
                if not running:
                    break
            head, count = extent.lfs2e.defrag_result()
        finally:
            extent.lfs2e.defrag_abort()
        print("step driver: %d steps, phases %s, head %d count %d"
              % (steps, phases, head, count))
        self.assertEqual(count, 96)
        self.assertEqual(head % _ALIGN, 0)
        self.assertEqual(phases[0], extent.PHASE_SPACE)
        self.assertIn(extent.PHASE_ERASE, phases)
        self.assertTrue(steps > 5)

        meta = extent.lfs2e.meta_map()
        for block in range(head, head + 96):
            self.assertEqual((meta[block >> 3] >> (block & 7)) & 1, 0,
                             "metadata block %d inside the run" % block)

        # The reservation is usable: write an extent into it and read it back.
        payload = _pattern(4096, 11)
        extent.lfs2e.write(0, payload)
        extent.lfs2e.commit(_TARGET, 0)
        extent.lfs2e.abort()
        with open(_TARGET, "rb") as handle:
            self.assertEqual(handle.read(4096), payload)

    def test_second_ensure_is_a_noop(self):
        data = _pattern(64 * 1024, 3)
        with open(_TARGET, "wb") as handle:
            handle.write(data)
        first = extent.ensure(_TARGET, align=_ALIGN, defrag_first=True)
        second = extent.ensure(_TARGET, align=_ALIGN, defrag_first=True)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
