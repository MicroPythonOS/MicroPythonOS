#!/usr/bin/env python3
"""Tests for scripts/preload_fs.py (host-side, not run by test_runner.py).

Run with:
    python3 tests/cpython_preload_fs.py

The littlefs round-trip needs littlefs-python:
    python3 -m pip install littlefs-python==0.19.0
"""

import hashlib
import importlib.util
import os
import tempfile
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("preload_fs", REPO_ROOT / "scripts" / "preload_fs.py")
preload_fs = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preload_fs)


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class ParseAppsTest(unittest.TestCase):
    def test_comments_blank_lines_and_options(self):
        with tempfile.TemporaryDirectory() as temp:
            apps = Path(temp) / "apps.txt"
            _write(
                apps,
                "\n".join(
                    [
                        "# comment",
                        "",
                        "repo com.example.one",
                        "badgehub com.example.two",
                        "badgehub com.example.three version=1.2.3 sha256=abcd",
                    ]
                ),
            )
            entries = preload_fs.parse_apps(apps)
            self.assertEqual([entry["fullname"] for entry in entries],
                             ["com.example.one", "com.example.two", "com.example.three"])
            self.assertEqual(entries[2]["options"], {"version": "1.2.3", "sha256": "abcd"})

    def test_unknown_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            apps = Path(temp) / "apps.txt"
            _write(apps, "github com.example.one\n")
            with self.assertRaises(preload_fs.PreloadError):
                preload_fs.parse_apps(apps)


class BadgeHubCacheTest(unittest.TestCase):
    def test_offline_uses_cache_and_verifies_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)
            payload = b"mpk-bytes"
            cached = cache / "com.example.app_1.2.3.mpk"
            cached.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            path, version = preload_fs._badgehub_mpk(
                "com.example.app", {"sha256": digest}, cache, offline=True
            )
            self.assertEqual(path, cached)
            self.assertEqual(version, "1.2.3")

    def test_offline_without_cache_is_an_error(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(preload_fs.PreloadError):
                preload_fs._badgehub_mpk("com.example.app", {}, Path(temp), offline=True)

    def test_hash_mismatch_is_an_error(self):
        with tempfile.TemporaryDirectory() as temp:
            cache = Path(temp)
            (cache / "com.example.app_1.2.3.mpk").write_bytes(b"mpk-bytes")
            with self.assertRaises(preload_fs.PreloadError):
                preload_fs._badgehub_mpk(
                    "com.example.app", {"sha256": "0" * 64}, cache, offline=True
                )


class SafeExtractTest(unittest.TestCase):
    def test_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "bad.mpk"
            with zipfile.ZipFile(archive, "w") as zip_file:
                zip_file.writestr("../escape.txt", "nope")
            with self.assertRaises(preload_fs.PreloadError):
                preload_fs._safe_extract(archive, Path(temp) / "out")

    def test_mpk_top_level_directory_is_stripped(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "app.mpk"
            with zipfile.ZipFile(archive, "w") as zip_file:
                zip_file.writestr("com.example.app/MANIFEST.JSON", '{"name": "App"}')
                zip_file.writestr("com.example.app/assets/main.py", "print('hi')\n")
            destination = Path(temp) / "apps" / "com.example.app"
            preload_fs._unpack_mpk(archive, "com.example.app", destination)
            self.assertTrue((destination / "MANIFEST.JSON").is_file())
            self.assertTrue((destination / "assets" / "main.py").is_file())
            self.assertFalse((destination / "com.example.app").exists())


class StageTest(unittest.TestCase):
    def _fixture(self, root):
        repo_apps = root / "apps"
        _write(repo_apps / "com.example.app" / "MANIFEST.JSON", '{"name": "App"}')
        _write(repo_apps / "com.example.app" / "main.py", "print('hi')\n")
        data_dir = root / "data"
        _write(data_dir / "images" / "sample.txt", "sample")
        apps_file = root / "apps.txt"
        _write(apps_file, "repo com.example.app\n")
        return repo_apps, data_dir, apps_file

    def test_stage_copies_apps_and_data(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo_apps, data_dir, apps_file = self._fixture(root)
            out = root / "out"
            preload_fs.stage(out, apps_file=apps_file, repo_apps_dir=repo_apps, data_dir=data_dir)
            self.assertTrue((out / "apps" / "com.example.app" / "MANIFEST.JSON").is_file())
            self.assertTrue((out / "apps" / "com.example.app" / "main.py").is_file())
            self.assertTrue((out / "data" / "images" / "sample.txt").is_file())

    def test_missing_repo_app_is_an_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo_apps, data_dir, _ = self._fixture(root)
            apps_file = root / "apps.txt"
            _write(apps_file, "repo com.example.missing\n")
            with self.assertRaises(preload_fs.PreloadError):
                preload_fs.stage(root / "out", apps_file=apps_file,
                                 repo_apps_dir=repo_apps, data_dir=data_dir)


class PackTest(unittest.TestCase):
    def test_vfs_row(self):
        row = preload_fs._partition_row(REPO_ROOT / "partitions" / "esp32s3_16mb_badge.csv", "vfs")
        self.assertEqual(row["offset"], 0x900000)
        self.assertEqual(row["size"], 0x700000)

    def test_image_round_trip_and_padding(self):
        try:
            import littlefs
        except ImportError:
            self.skipTest("littlefs-python is not installed")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            _write(source / "apps" / "com.example.app" / "MANIFEST.JSON", '{"name": "App"}')
            _write(source / "data" / "hello.txt", "hello")
            partitions = root / "partitions.csv"
            _write(
                partitions,
                "# Name, Type, SubType, Offset, Size, Flags\n"
                "nvs,data,nvs,0x9000,0x6000,\n"
                "factory,app,factory,0x10000,0x20000,\n"
                "vfs,data,fat,0x30000,0x10000,\n",
            )
            image = root / "fs.img"
            vfs = preload_fs.pack(source, partitions, image)
            self.assertEqual(vfs["offset"], 0x30000)
            self.assertEqual(image.stat().st_size, 0x10000)

            fs = littlefs.LittleFS(
                context=littlefs.UserContextFile(str(image)),
                block_size=preload_fs.BLOCK_SIZE,
                block_count=0x10000 // preload_fs.BLOCK_SIZE,
                read_size=preload_fs.READ_SIZE,
                prog_size=preload_fs.PROG_SIZE,
                cache_size=preload_fs.CACHE_SIZE,
            )
            try:
                with fs.open("/data/hello.txt") as handle:
                    self.assertEqual(handle.read(), "hello")
            finally:
                fs.unmount()

    def test_too_large_tree_is_reported(self):
        try:
            import littlefs  # noqa: F401
        except ImportError:
            self.skipTest("littlefs-python is not installed")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "big.bin").write_bytes(os.urandom(0x20000))
            partitions = root / "partitions.csv"
            _write(
                partitions,
                "factory,app,factory,0x10000,0x10000,\n"
                "vfs,data,fat,0x20000,0x10000,\n",
            )
            with self.assertRaises(preload_fs.PreloadError):
                preload_fs.pack(source, partitions, root / "fs.img")


if __name__ == "__main__":
    unittest.main()
