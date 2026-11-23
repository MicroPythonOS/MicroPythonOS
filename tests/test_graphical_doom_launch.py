"""The shipped Doom package: flat layout, engine selection and WAD unpacking.

The engine itself is C and is covered by the core and native-module builds; this
checks the Python side of the package that users get: which engine file this host
picks, and that the bundled WAD zip is inflated into RAM, not storage.
"""

import os
import sys
import unittest

APP_DIR = "apps/com.micropythonos.doom"
sys.path.insert(0, APP_DIR)

import doom


class TestDoomPackage(unittest.TestCase):

    def setUp(self):
        if sys.platform == "esp32":
            raise unittest.SkipTest("a desktop package test")

    def test_package_is_flat(self):
        names = sorted(os.listdir(APP_DIR))
        if "__pycache__" in names:
            names.remove("__pycache__")
        self.assertEqual(names, sorted([
            "MANIFEST.JSON",
            "doom.py",
            "doom1.wad.zip",
            "doom_legal.py",
            "doom_overlay.py",
            "esp32s3.xip",
            "icon_64x64.png",
            "module_x64.mpy",
        ]))
        for name in names:
            self.assertFalse(os.stat(APP_DIR + "/" + name)[0] & 0x4000,
                             "%s is a directory" % name)

    def test_engine_candidates_on_desktop(self):
        if not doom.engine_candidates():
            raise unittest.SkipTest("no Doom engine for this host")
        self.assertEqual(doom.engine_candidates(), ["module_x64.mpy"])

    def test_find_engine(self):
        if not doom.engine_candidates():
            raise unittest.SkipTest("no Doom engine for this host")
        path, name = doom.find_engine()
        self.assertEqual(name, "module_x64.mpy")
        self.assertTrue(path.endswith(APP_DIR + "/module_x64.mpy"))

    def test_manifest_selects_both_platforms(self):
        import json
        with open(APP_DIR + "/MANIFEST.JSON", "rb") as f:
            manifest = json.loads(f.read())
        native = manifest["native"]
        self.assertEqual(native["esp32s3"], ["esp32s3.xip"])
        self.assertEqual(native["x64"], ["module_x64.mpy"])
        for names in native.values():
            for name in names:
                self.assertTrue(os.stat(APP_DIR + "/" + name))
        self.assertTrue(isinstance(manifest["version"], str))
        self.assertTrue(all(part.isdigit()
                            for part in manifest["version"].split(".")))

    def test_the_wad_zip_inflates_into_ram_not_storage(self):
        # The desktop package also has a plain WAD for the native module, so
        # pretend there is none and make the launch take the zip path.
        real_find_wad = doom.find_wad
        doom.find_wad = lambda intent=None: None
        updates = []
        try:
            wad = doom.prepare_wad(
                None, lambda text, done=0, total=0:
                updates.append((text, done, total)))
        finally:
            doom.find_wad = real_find_wad
        self.assertIsNone(wad.path, "the WAD was written to a file")
        self.assertIsNotNone(wad.buffer)
        self.assertEqual(wad.name, "doom1.wad")
        self.assertEqual(wad.size, 1805391)
        self.assertEqual(bytes(wad.buffer[:4]), b"IWAD")
        self.assertTrue(updates)
        self.assertEqual(updates[-1][1], updates[-1][2])

        # The core reads it through the host callbacks: a chunk in the middle
        # has to come from the same buffer. The plain doom1.wad is a developer
        # artefact (gitignored), so compare against the buffer, and against the
        # file as well when a checkout happens to have it.
        chunk = bytearray(64)
        self.assertEqual(wad.read_into(1000, chunk), 64)
        self.assertEqual(bytes(chunk), bytes(wad.buffer[1000:1064]))
        if os.path.exists("doom1.wad"):
            with open("doom1.wad", "rb") as f:
                f.seek(1000)
                self.assertEqual(bytes(chunk), f.read(64))
        self.assertEqual(wad.read_into(wad.size - 10, chunk), 10)


if __name__ == "__main__":
    unittest.main()
