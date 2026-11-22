"""Installing an app whose engine is an extent, on hardware.

This is the install path an App Store download takes, minus the network: a
`.mpk` is built in memory and fed through the same streaming extractor. The
filesystem is fragmented first, so the `.xip` entry cannot be reserved without
defragmenting, and the extent has to be 64 KiB aligned for XIP.

Runs with the usual device runner; desktop skips because the lfs2e module is
firmware-only.
"""

import binascii
import json
import os
import struct
import sys
import unittest

import mpos.extent as extent
from mpos.content.app_manager import AppManager

_APP = "com.example.xiptest"
_APP_DIR = "apps/" + _APP
_MPK = "/tmp_install_extent.mpk"
_ROOT = "/defrag-test"
_ALIGN = extent.XIP_ALIGN_BLOCKS
_PAYLOAD = 192 * 1024
_FILL_BLOCKS = 4


def _yield():
    import time
    time.sleep_ms(2)


def _rmtree(path):
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


def _pattern(size, seed):
    state = (seed + 1) * 2654435761 & 0xFFFFFFFF
    out = bytearray(size)
    for i in range(size):
        state = (state * 1103515245 + 12345) & 0xFFFFFFFF
        out[i] = (state >> 16) & 0xFF
        if (i & 0x1FFF) == 0x1FFF:
            _yield()
    return bytes(out)


def _zip(entries):
    out = bytearray()
    for name, data in entries:
        encoded = name.encode()
        crc = binascii.crc32(data, 0) & 0xFFFFFFFF
        out += struct.pack(
            "<4s2B4HL2L2H", b"PK\x03\x04",
            20, 0,
            0, 0, 0, 0,
            crc, len(data), len(data),
            len(encoded), 0)
        out += encoded
        out += data
    return bytes(out)


def _manifest():
    return json.dumps({
        "name": "Xip Test",
        "fullname": _APP,
        "version": "1.0.0",
        "native": {"esp32s3": ["core.xip"]},
    }).encode()


@unittest.skipUnless(
    sys.platform == "esp32" and extent.available(),
    "littlefs2e is only available on ESP32 firmware",
)
class InstallExtentTest(unittest.TestCase):

    def setUp(self):
        self.block_size, self.block_count, _ = extent.geometry()
        self.fillers = []
        _rmtree(_APP_DIR)
        _rmtree(_ROOT)
        try:
            os.remove(_MPK)
        except OSError:
            pass

    def tearDown(self):
        _rmtree(_APP_DIR)
        _rmtree(_ROOT)
        try:
            os.remove(_MPK)
        except OSError:
            pass

    def _free_blocks(self):
        used = extent.lfs2e.used_map()
        free = 0
        for block in range(self.block_count):
            if not (used[block >> 3] >> (block & 7)) & 1:
                free += 1
        return free

    def _fragment(self):
        os.mkdir(_ROOT)
        chunk = _pattern(_FILL_BLOCKS * self.block_size, 5)
        index = 0
        while True:
            directory = "%s/d%02d" % (_ROOT, index % 8)
            if index < 8:
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

    def _write_mpk(self, payload):
        app_dir = _APP + "/"
        data = _zip([
            (app_dir, b""),
            (app_dir + "MANIFEST.JSON", _manifest()),
            (app_dir + "core.xip", payload),
        ])
        with open(_MPK, "wb") as handle:
            handle.write(data)
        return data

    def _check_installed(self, payload):
        path = "/" + _APP_DIR + "/core.xip"
        found = extent.info(path)
        self.assertTrue(found is not None, "core.xip is not an extent")
        offset, length, crc = found
        self.assertEqual(length, len(payload))
        self.assertEqual(offset % (_ALIGN * self.block_size), 0)
        self.assertTrue(crc != 0)
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), payload)
        # The size is the extent's, and the tree still walks.
        self.assertEqual(os.stat(path)[6], len(payload))
        self.assertTrue("MANIFEST.JSON" in os.listdir(_APP_DIR))

    def test_install_mpk_defrags_for_the_xip(self):
        payload = _pattern(_PAYLOAD, 3)
        data = self._write_mpk(payload)
        self._fragment()
        self.assertTrue(extent.largest_run(_ALIGN) < _PAYLOAD // self.block_size,
                        "fixture did not fragment the filesystem")
        # The local .mpk install is synchronous: it drives the defrag steps
        # without yielding, so no progress callback is involved.
        AppManager.install_mpk(_MPK, _APP_DIR)
        self._check_installed(payload)
        for path in self.fillers[1::3]:
            self.assertEqual(os.stat(path)[6], _FILL_BLOCKS * self.block_size,
                             path)
        self.assertTrue(data)

    def test_install_mpk_without_fragmentation(self):
        # The reservation succeeds on the first try: the archive-close gate is
        # still exercised, just without a defrag.
        payload = _pattern(_PAYLOAD, 4)
        self._write_mpk(payload)
        AppManager.install_mpk(_MPK, _APP_DIR)
        self._check_installed(payload)


if __name__ == "__main__":
    unittest.main()
