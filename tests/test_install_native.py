"""Install-time selection of native files, and the .xip extent sink.

The desktop has no littlefs2e, so the extent path is exercised with a fake
writer; the real extent is covered on a badge by tests/test_extent_filesystem.py
and the littlefs C suite.
"""

import binascii
import os
import shutil
import struct
import unittest

from mpos import extent as extent_files
from mpos.content.streaming_unzip import StreamingUnzip

APP = "com.micropythonos.example"
DEST = "tmp_install_native"


def _zip(entries):
    """A ZIP of stored local entries (the streaming parser needs no CD)."""
    out = bytearray()
    for name, data in entries:
        encoded = name.encode()
        crc = binascii.crc32(data, 0) & 0xFFFFFFFF
        out += struct.pack(
            "<4s2B4HL2L2H", b"PK\x03\x04",
            20, 0,              # version needed
            0, 0, 0, 0,         # flags, method, time, date
            crc, len(data), len(data),
            len(encoded), 0)
        out += encoded
        out += data
    return bytes(out)


def _manifest(native=None, extra=None):
    fields = {
        "name": "Example",
        "fullname": APP,
        "version": "1.0.0",
    }
    if native is not None:
        fields["native"] = native
    if extra:
        fields.update(extra)
    import json
    return json.dumps(fields).encode()


def _feed(extractor, data, chunk=512, space_handler=None):
    for i in range(0, len(data), chunk):
        extractor.feed_all(data[i:i + chunk], space_handler)
    extractor.finish()


class FakeWriter:
    instances = []

    def __init__(self, length, align=1, defrag_first=True):
        self.length = length
        self.align = align
        self.data = bytearray()
        self.offset = 0
        self.committed = None
        self.aborted = False
        FakeWriter.instances.append(self)

    def write(self, data):
        self.data += data
        self.offset += len(data)

    def commit(self, path, crc=None):
        self.committed = (path, crc)
        return (0, len(self.data), crc)

    def abort(self):
        self.aborted = True


class TestNativeInstall(unittest.TestCase):
    def setUp(self):
        self._rm(DEST)
        self._real = {
            "available": extent_files.available,
            "Writer": extent_files.Writer,
        }
        FakeWriter.instances = []

    def tearDown(self):
        extent_files.available = self._real["available"]
        extent_files.Writer = self._real["Writer"]
        self._rm(DEST)

    def _rm(self, path):
        try:
            st = os.stat(path)
        except OSError:
            return
        if st[0] & 0x4000:
            shutil.rmtree(path)
        else:
            os.remove(path)

    def _extract(self, entries, native_keys):
        extractor = StreamingUnzip(DEST, expected_app_name=APP, native_keys=native_keys)
        _feed(extractor, _zip(entries))
        return extractor

    def _exists(self, name):
        try:
            os.stat(DEST + "/" + name)
            return True
        except OSError:
            return False

    def _read(self, name):
        with open(DEST + "/" + name, "rb") as f:
            return f.read()

    def test_installs_only_the_selected_native_files(self):
        app_dir = APP + "/"
        self._extract([
            (app_dir, b""),
            (app_dir + "MANIFEST.JSON", _manifest({
                "x64": ["module_x64.mpy"],
                "esp32s3": ["esp32s3.xip"],
            })),
            (app_dir + "doom.py", b"print(1)\n"),
            (app_dir + "esp32s3.xip", b"X" * 300),
            (app_dir + "module_x64.mpy", b"M" * 50),
        ], native_keys=["x64"])

        self.assertTrue(self._exists("doom.py"))
        self.assertTrue(self._exists("MANIFEST.JSON"))
        self.assertEqual(self._read("module_x64.mpy"), b"M" * 50)
        self.assertFalse(self._exists("esp32s3.xip"))

    def test_board_installs_the_xip_into_an_extent(self):
        extent_files.available = lambda: True
        extent_files.Writer = FakeWriter
        payload = bytes((i * 3) & 0xFF for i in range(1000))
        app_dir = APP + "/"
        self._extract([
            (app_dir, b""),
            (app_dir + "MANIFEST.JSON", _manifest({
                "x64": ["module_x64.mpy"],
                "esp32s3": ["esp32s3.xip"],
            })),
            (app_dir + "esp32s3.xip", payload),
            (app_dir + "module_x64.mpy", b"M" * 50),
        ], native_keys=["esp32s3"])

        self.assertFalse(self._exists("esp32s3.xip"))
        self.assertFalse(self._exists("module_x64.mpy"))
        self.assertEqual(len(FakeWriter.instances), 1)
        writer = FakeWriter.instances[0]
        self.assertEqual(writer.length, len(payload))
        self.assertEqual(writer.align, extent_files.XIP_ALIGN_BLOCKS)
        self.assertEqual(bytes(writer.data), payload)
        self.assertEqual(writer.committed[0], DEST + "/esp32s3.xip")
        self.assertEqual(writer.committed[1],
                         binascii.crc32(payload, 0) & 0xFFFFFFFF)
        self.assertFalse(writer.aborted)

    def test_extent_writer_request_is_handed_to_the_caller(self):
        # Reserving an extent may defragment, which has to yield to the UI and
        # must not straddle an open archive, so the parser stops and lets the
        # caller build the writer.
        extent_files.available = lambda: True
        extent_files.Writer = FakeWriter
        requests = []

        def handler(length, align):
            requests.append((length, align))
            return extent_files.Writer(length, align)

        app_dir = APP + "/"
        extractor = StreamingUnzip(DEST, expected_app_name=APP,
                                   native_keys=["esp32s3"])
        _feed(extractor, _zip([
            (app_dir, b""),
            (app_dir + "MANIFEST.JSON", _manifest({"esp32s3": ["esp32s3.xip"]})),
            (app_dir + "esp32s3.xip", b"X" * 300),
        ]), space_handler=handler)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0], (300, extent_files.XIP_ALIGN_BLOCKS))
        self.assertEqual(len(FakeWriter.instances), 1)
        self.assertEqual(bytes(FakeWriter.instances[0].data), b"X" * 300)

    def test_board_falls_back_to_a_file_without_extents(self):
        extent_files.available = lambda: False
        payload = b"X" * 300
        app_dir = APP + "/"
        self._extract([
            (app_dir, b""),
            (app_dir + "MANIFEST.JSON", _manifest({"esp32s3": ["esp32s3.xip"]})),
            (app_dir + "esp32s3.xip", payload),
        ], native_keys=["esp32s3"])
        self.assertEqual(self._read("esp32s3.xip"), payload)

    def test_manifest_without_native_extracts_everything(self):
        app_dir = APP + "/"
        self._extract([
            (app_dir, b""),
            (app_dir + "MANIFEST.JSON", _manifest()),
            (app_dir + "doom.py", b"print(1)\n"),
            (app_dir + "module_x64.mpy", b"M" * 50),
        ], native_keys=["x64"])
        self.assertTrue(self._exists("module_x64.mpy"))

    def test_native_file_before_the_manifest_is_rejected(self):
        app_dir = APP + "/"
        extractor = StreamingUnzip(DEST, expected_app_name=APP, native_keys=["x64"])
        with self.assertRaises(RuntimeError) as ctx:
            _feed(extractor, _zip([
                (app_dir, b""),
                (app_dir + "module_x64.mpy", b"M" * 50),
                (app_dir + "MANIFEST.JSON", _manifest({"x64": ["module_x64.mpy"]})),
            ]))
        self.assertTrue("before" in str(ctx.exception))

    def test_a_truncated_xip_fails_the_install(self):
        extent_files.available = lambda: True
        extent_files.Writer = FakeWriter
        app_dir = APP + "/"
        archive = _zip([
            (app_dir, b""),
            (app_dir + "MANIFEST.JSON", _manifest({"esp32s3": ["esp32s3.xip"]})),
            (app_dir + "esp32s3.xip", b"X" * 400),
        ])
        extractor = StreamingUnzip(DEST, expected_app_name=APP, native_keys=["esp32s3"])
        with self.assertRaises(RuntimeError):
            _feed(extractor, archive[:-100])
        self.assertEqual(len(FakeWriter.instances), 1)
        self.assertTrue(FakeWriter.instances[0].aborted)

    def test_crc_mismatch_aborts_the_extent(self):
        extent_files.available = lambda: True
        extent_files.Writer = FakeWriter
        payload = b"abcdef"
        app_dir = APP + "/"
        archive = bytearray(_zip([
            (app_dir, b""),
            (app_dir + "MANIFEST.JSON", _manifest({"esp32s3": ["esp32s3.xip"]})),
            (app_dir + "esp32s3.xip", payload),
        ]))
        # Break the stored payload: the entry CRC no longer matches.
        index = archive.find(payload)
        archive[index] ^= 0xFF
        extractor = StreamingUnzip(DEST, expected_app_name=APP, native_keys=["esp32s3"])
        with self.assertRaises(RuntimeError):
            _feed(extractor, bytes(archive))
        self.assertEqual(len(FakeWriter.instances), 1)
        self.assertTrue(FakeWriter.instances[0].aborted)
        self.assertIsNone(FakeWriter.instances[0].committed)


if __name__ == "__main__":
    unittest.main()
