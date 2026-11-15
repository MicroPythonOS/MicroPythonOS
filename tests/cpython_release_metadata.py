#!/usr/bin/env python3
"""CPython tests for the web part of scripts/release_metadata.py.

The updates and install repos need real release assets, so only the web
extraction (and the asset list that decides what to download) is covered here.

Run with:
    python3 tests/cpython_release_metadata.py
"""

import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from scripts import release_metadata  # noqa: E402


class NeededAssetsTests(unittest.TestCase):
    def test_every_repo_is_prepared_by_default(self):
        names = release_metadata.needed_assets("1.2.3")
        self.assertIn("MicroPythonOS_esp32s3_1.2.3.bin", names)
        self.assertIn("MicroPythonOS_esp32s3_1.2.3.ota", names)
        self.assertNotIn("MicroPythonOS_web_1.2.3.zip", names)

    def test_web_only_needs_only_the_web_zip(self):
        names = release_metadata.needed_assets(
            "1.2.3", include_install=False, include_updates=False, include_web=True)
        self.assertEqual(names, ["MicroPythonOS_web_1.2.3.zip"])


class UpdateWebRepoTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.web_dir = self.root / "web"
        self.assets_dir = self.root / "assets"
        self.web_dir.mkdir()
        self.assets_dir.mkdir()

    def _write_zip(self, files):
        asset = self.assets_dir / "MicroPythonOS_web_1.2.3.zip"
        with zipfile.ZipFile(asset, "w") as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        return asset

    def test_extracts_the_build_over_the_working_copy(self):
        self._write_zip({
            "index.html": "new index",
            "micropython.wasm": "new wasm",
        })
        (self.web_dir / "index.html").write_text("old index")

        release_metadata.update_web_repo(self.web_dir, "1.2.3", self.assets_dir)

        self.assertEqual((self.web_dir / "index.html").read_text(), "new index")
        self.assertEqual((self.web_dir / "micropython.wasm").read_text(), "new wasm")

    def test_rejects_a_nested_path(self):
        self._write_zip({"sub/index.html": "nested"})
        with self.assertRaises(release_metadata.ReleaseError):
            release_metadata.update_web_repo(self.web_dir, "1.2.3", self.assets_dir)

    def test_reports_a_missing_asset(self):
        with self.assertRaises(release_metadata.ReleaseError):
            release_metadata.update_web_repo(self.web_dir, "1.2.3", self.assets_dir)


if __name__ == "__main__":
    unittest.main()
